"""Рендер вертикальных клипов: кадрирование, фон, субтитры, звук."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .config import ffmpeg
from . import custom_fonts, resources
from . import reframe as _reframe
from .reframe import crop_expressions
from .utils import MediaError, probe, run, subprocess_kwargs

ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080), "4:5": (1080, 1350)}


_FONTS_LOGGED: List[bool] = []


def _log_fonts_dir(fonts_dir: Path) -> None:
    """Один раз пишем в лог, откуда libass берёт шрифты.

    Если папка пустая или недоступна, libass молча подставит системный шрифт —
    текст станет шире и «мягче». По этой строке в app.log сразу видно причину.
    """
    if _FONTS_LOGGED:
        return
    _FONTS_LOGGED.append(True)
    try:
        count = len(list(Path(fonts_dir).glob("*.ttf")))
    except OSError:
        count = -1
    marker = "OK" if count > 0 else "ПРОБЛЕМА: шрифты не найдены"
    print(f"[render] шрифты libass: {fonts_dir} ({count} файлов) — {marker}",
          file=sys.stderr, flush=True)


def _esc(path: Path) -> str:
    # Экранирование для аргумента фильтра ffmpeg внутри одинарных кавычек:
    # в av_get_token обратный слэш внутри '...' не экранирует апостроф,
    # поэтому апостроф закрывает кавычку, экранируется как \' и снова открывает '...'.
    p = str(path).replace("\\", "/")
    p = p.replace(":", "\\:").replace("'", "'\\\\\\''")
    return p


def _bg_chain(w: int, h: int, focus_x: float = 0.5, sharpen: bool = False,
              src: str = "[0:v]") -> str:
    sharp = ",unsharp=5:5:0.7:5:5:0.0" if sharpen else ""
    return (
        f"{src}split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"gblur=sigma=26:steps=2,eq=saturation=0.95[bgb];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos{sharp}[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2:shortest=1[base]"
    )


def _crop_chain(w: int, h: int, focus_x: float = 0.5, focus_y: float = 0.45,
                sharpen: bool = False, src: str = "[0:v]") -> str:
    sharp = ",unsharp=5:5:0.7:5:5:0.0" if sharpen else ""
    return (
        f"{src}scale={w}:{h}:force_original_aspect_ratio=increase{sharp},"
        f"crop={w}:{h}:(iw-{w})*{focus_x:.3f}:(ih-{h})*{focus_y:.3f}[base]"
    )


def _auto_chain(w: int, h: int, crop_path: Dict[str, Any], sharpen: bool = False,
                src: str = "[0:v]") -> str:
    """Заливка кадра с плавающим окном по лицам."""
    x_expr, y_expr = crop_expressions(crop_path)
    cw = int(crop_path["crop_w"])
    ch = int(crop_path["crop_h"])
    sharp = ",unsharp=5:5:0.7:5:5:0.0" if sharpen else ""
    return (
        f"{src}crop={cw}:{ch}:x='{x_expr}':y='{y_expr}',"
        f"scale={w}:{h}:flags=lanczos,setsar=1{sharp},format=yuv420p[base]"
    )


def _cut_spans(spans: Optional[List[Dict[str, float]]], clip_start: float,
               clip_end: float) -> List[Dict[str, float]]:
    """Нормализует план склейки без пауз под конкретное окно клипа.

    Возвращает [] если резать нечего (одна сплошная дорожка): тогда рендер идёт
    обычным путём без trim+concat — так дешевле и без лишних швов.
    """
    if not spans:
        return []
    clean: List[List[float]] = []
    for span in sorted(spans, key=lambda s: float(s.get("start", 0.0))):
        start = max(float(clip_start), float(span.get("start", clip_start)))
        end = min(float(clip_end), float(span.get("end", clip_end)))
        if end - start < 0.05:
            continue
        if clean and start - clean[-1][1] < 0.03:
            clean[-1][1] = max(clean[-1][1], end)  # слипшиеся отрезки — без шва
        else:
            clean.append([start, end])
    if len(clean) < 2:
        return []
    covered = sum(end - start for start, end in clean)
    if covered < (clip_end - clip_start) * 0.3:
        # план «съел» почти весь клип — вероятно, ошибочный: не рискуем
        return []
    return [{"start": round(start, 3), "end": round(end, 3)} for start, end in clean]


def _video_spans_graph(segments: List[Dict[str, float]], base: float) -> str:
    """trim+setpts+concat: вход — исходник, выход — метка [vsrc]."""
    parts: List[str] = []
    labels: List[str] = []
    for i, seg in enumerate(segments):
        start = max(0.0, seg["start"] - base)
        end = max(start + 0.02, seg["end"] - base)
        parts.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    parts.append("".join(labels) + f"concat=n={len(segments)}:v=1:a=0[vsrc]")
    return ";".join(parts)


def _audio_spans_graph(segments: List[Dict[str, float]], base: float,
                       track: int = 0) -> str:
    """atrim+asetpts+concat для звука: выход — метка [aconc]."""
    src = f"[0:a:{max(0, int(track))}]"
    parts: List[str] = []
    labels: List[str] = []
    for i, seg in enumerate(segments):
        start = max(0.0, seg["start"] - base)
        end = max(start + 0.02, seg["end"] - base)
        parts.append(f"{src}atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[a{i}]")
    parts.append("".join(labels) + f"concat=n={len(segments)}:v=0:a=1[aconc]")
    return ";".join(parts)


_HW_CACHE: Dict[str, Any] = {}
_HW_LOCK = threading.Lock()
_FALLBACK_LOCK = threading.Lock()
_FALLBACK_NOTICE_SECONDS = 30
_fallback_notice: Optional[Dict[str, str]] = None
_last_fallback = 0.0


def _hw_args(encoder: str, crf: int, quality: str = "balanced") -> List[str]:
    """Аргументы аппаратного энкодера (у каждого свои понятия качества)."""
    if encoder == "h264_videotoolbox":
        qv = {"fast": "65", "high": "82"}.get(quality, "75")
        return ["-c:v", encoder, "-q:v", qv, "-profile:v", "high",
                "-pix_fmt", "yuv420p"]
    if encoder == "h264_nvenc":
        nv_preset, nv_cq = {
            "fast": ("p3", "24"),
            "high": ("p6", "17"),
        }.get(quality, ("p5", "20"))
        return ["-c:v", encoder, "-preset", nv_preset, "-rc", "vbr", "-cq", nv_cq,
                "-b:v", "0", "-pix_fmt", "yuv420p"]
    if encoder == "h264_amf":
        # AMD: постоянное качество вместо битрейта, иначе сцены «плывут»
        return ["-c:v", encoder, "-quality", "quality", "-rc", "cqp",
                "-qp_i", str(crf), "-qp_p", str(crf + 2), "-pix_fmt", "yuv420p"]

    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-global_quality", str(crf), "-pix_fmt", "nv12"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p"]


def _hw_works(encoder: str) -> bool:
    """Реально ли работает железо, а не только «энкодер есть в сборке ffmpeg».

    `-encoders` показывает скомпилированные кодеки: nvenc есть в списке даже на
    ноутбуке без NVIDIA, videotoolbox — не на каждом чипе. Поэтому пробуем
    закодировать несколько кадров и только потом доверяем энкодеру.
    """
    key = f"works:{encoder}"
    if key in _HW_CACHE:
        return bool(_HW_CACHE[key])
    cmd = [ffmpeg(), "-hide_banner", "-v", "error", "-f", "lavfi",
           "-i", "color=c=black:s=1080x1920:r=30:d=0.4", "-frames:v", "8",
           *_hw_args(encoder, 21), "-f", "null", "-"]
    ok = False
    try:
        proc = run(cmd, timeout=15)
        ok = proc.returncode == 0
        if not ok and sys.platform == "win32":
            detail = (proc.stderr or proc.stdout or "").strip()
            print(f"[render] проба {encoder}: {detail[-460:]}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 — таймаут/падение трактуем как «не работает»
        ok = False
    _HW_CACHE[key] = ok
    return ok


def _encoder_mode() -> str:
    try:
        from . import settings

        return settings.encoder_mode()
    except Exception:  # noqa: BLE001
        return "auto"


def hw_cached() -> Optional[str]:
    """Только из кэша: не запускает пробный кадр (для /api/health)."""
    return _HW_CACHE.get("value")


def _find_hw_encoder(excluded: Tuple[str, ...] = ()) -> Optional[str]:
    """Ищет рабочий кодировщик. Вызывается под _HW_LOCK."""
    preferred = {"darwin": ["h264_videotoolbox"],
                 "win32": ["h264_nvenc", "h264_amf", "h264_qsv"],
                 "linux": ["h264_nvenc", "h264_qsv"]}.get(sys.platform, [])
    # Выбор пользователя: дискретная карта (NVENC/AMF) или встроенная (Quick Sync)
    try:
        from . import gpu_pref

        preferred = gpu_pref.encoder_order(preferred)
    except Exception:  # noqa: BLE001 — предпочтение не критично
        pass
    if "encoders" not in _HW_CACHE:
        try:
            proc = run([ffmpeg(), "-hide_banner", "-encoders"])
            _HW_CACHE["encoders"] = (proc.stdout or "") + (proc.stderr or "")
        except Exception:
            _HW_CACHE["encoders"] = ""
    available = _HW_CACHE["encoders"]
    return next((name for name in preferred
                 if name not in excluded and name in available and _hw_works(name)), None)


def reset_hw_encoder() -> None:
    """Позволяет повторить пробу после сохранения настроек."""
    with _HW_LOCK:
        _HW_CACHE.clear()


def hw_encoder(mode: Optional[str] = None) -> Optional[str]:
    """Возвращает аппаратный энкодер после успешной пробы FFmpeg."""
    with _HW_LOCK:
        mode = mode or _encoder_mode()
        if mode == "cpu":
            return None
        if "value" not in _HW_CACHE:
            _HW_CACHE["value"] = _find_hw_encoder()
        return _HW_CACHE["value"]


def cpu_fallback_notice() -> Optional[Dict[str, str]]:
    """Последний переход на CPU для опроса интерфейса."""
    with _FALLBACK_LOCK:
        if _fallback_notice and time.monotonic() - _last_fallback < _FALLBACK_NOTICE_SECONDS:
            return dict(_fallback_notice)
    return None


def _announce_cpu_fallback(hw: Optional[str]) -> None:
    global _fallback_notice, _last_fallback
    reason = "gpu_failed" if hw else "gpu_unavailable"
    detail = f"{hw} и другие доступные GPU не отрендерили клип" if hw else "аппаратный энкодер недоступен"
    print(f"[render] {detail}. Рендер на процессоре (libx264)", file=sys.stderr, flush=True)
    with _FALLBACK_LOCK:
        now = time.monotonic()
        if (_fallback_notice is None or _fallback_notice["reason"] != reason
                or now - _last_fallback >= _FALLBACK_NOTICE_SECONDS):
            _fallback_notice = {"id": str(time.monotonic_ns()), "reason": reason}
        _last_fallback = now


def _encode_attempts(
    hw: Optional[str], crop_path: Optional[Dict[str, Any]], try_other_gpu: bool,
) -> Iterator[Tuple[Optional[str], Optional[Dict[str, Any]]]]:
    if hw:
        yield hw, crop_path
        if try_other_gpu:
            tried = [hw]
            while True:
                with _HW_LOCK:
                    alternative = _find_hw_encoder(tuple(tried))
                if alternative is None:
                    break
                tried.append(alternative)
                yield alternative, crop_path
    yield None, crop_path
    if crop_path:
        # Если длинное выражение кадрирования отвергнуто, пробуем упрощённое.
        yield None, _reframe._coarse_path(crop_path)
        yield None, None


def _video_args(encoder: Optional[str], crf: int, preset: str, quality: str = "balanced") -> List[str]:
    if encoder:
        return _hw_args(encoder, crf, quality=quality)
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p"]


def _run_encode(cmd: List[str], duration: float,
                on_progress: Optional[Callable[[float], None]]
                ) -> Tuple[int, List[str], Optional[str]]:
    """Запускает ffmpeg, качает прогресс и сторожит зависание."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            errors="replace", bufsize=1, **subprocess_kwargs())
    assert proc.stdout is not None and proc.stderr is not None
    tail: List[str] = []
    stopped: List[str] = []

    def _drain() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    limit = max(180.0, duration * 8.0)

    def _watchdog() -> None:
        if proc.poll() is not None:
            return
        stopped.append(f"нет прогресса больше {limit:.0f} с")
        try:
            proc.kill()
        except Exception:
            pass

    timer = threading.Timer(limit, _watchdog)
    timer.daemon = True
    timer.start()
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") and on_progress:
                try:
                    done = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                on_progress(round(max(0.0, min(0.99, done / duration)), 3))
        proc.wait()
    finally:
        timer.cancel()
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        reader.join(timeout=2)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
    return proc.returncode, tail, (stopped[0] if stopped else None)


def _measure_loudness(source: Path, start: float, duration: float,
                      audio_track: int = 0,
                      segments: Optional[List[Dict[str, float]]] = None
                      ) -> Optional[Dict[str, Any]]:
    """Первый проход loudnorm: измеряем громкость фрагмента.

    С вырезанием пауз измеряем уже склеенную дорожку (trim+concat): иначе
    loudnorm получил бы громкость вместе с выброшенной тишиной и занизил бы
    итоговый уровень.
    """
    try:
        if segments:
            graph = _audio_spans_graph(segments, start, audio_track) + (
                ";[aconc]loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json[out]")
            cmd = [ffmpeg(), "-hide_banner", "-nostats",
                   "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
                   "-filter_complex", graph, "-map", "[out]", "-f", "null", "-"]
        else:
            cmd = [ffmpeg(), "-hide_banner", "-nostats", "-ss", f"{start:.3f}",
                   "-t", f"{duration:.3f}", "-i", str(source),
                   "-map", f"0:a:{max(0, int(audio_track))}?", "-af",
                   "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=max(30.0, duration * 2.5), **subprocess_kwargs())
        text = proc.stderr or ""
        start_idx = text.rfind("{")
        end_idx = text.rfind("}")
        if start_idx == -1 or end_idx <= start_idx:
            return None
        data = json.loads(text[start_idx:end_idx + 1])
        keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        if not all(k in data for k in keys):
            return None
        values = []
        for key in keys:
            try:
                value = float(data[key])
            except (TypeError, ValueError):
                return None
            if value in (float("inf"), float("-inf")) or not math.isfinite(value):
                return None
            values.append(value)
        if not (-99.0 <= values[0] <= 0.0):
            return None
        return data
    except Exception:
        return None


def render_clip(source: Path, clip_start: float, clip_end: float, out_path: Path,
                ass_path: Optional[Path] = None, aspect: str = "9:16",
                mode: str = "blur", focus_x: float = 0.5,
                on_progress: Optional[Callable[[float], None]] = None,
                crf: int = 21, preset: str = "veryfast",
                crop_path: Optional[Dict[str, Any]] = None,
                pip: Optional[Dict[str, Any]] = None,
                audio_track: int = 0,
                spans: Optional[List[Dict[str, float]]] = None,
                game_layer: Optional[Dict[str, Any]] = None,
                watermark: Optional[Dict[str, Any]] = None,
                intro_asset_id: Optional[str] = None,
                outro_asset_id: Optional[str] = None,
                bgm: Optional[Dict[str, Any]] = None,
                punch_in_zoom: bool = False) -> Dict[str, Any]:
    """Рендерит вертикальный/горизонтальный клип из окна исходника.

    Поддерживает: вырезание пауз (spans), 2-speaker dual_split, Split-Screen (game_layer),
    хук punch-in зум, водяной знак (watermark), BGM с sidechain авто-приглушением и
    видео-бамперы интро/аутро.
    """
    w, h = ASPECTS.get(aspect, ASPECTS["9:16"])
    segments = _cut_spans(spans, clip_start, clip_end)
    if segments:
        duration = max(0.4, round(sum(seg["end"] - seg["start"] for seg in segments), 3))
        base = segments[0]["start"]            # самый ранний отрезок — точка входа
        input_len = max(duration, segments[-1]["end"] - base)
    else:
        duration = max(0.4, clip_end - clip_start)
        base = clip_start
        input_len = duration
    info = probe(source)
    try:
        from . import settings as app_settings

        rq = str(app_settings.get().get("render_quality") or "balanced")
    except Exception:
        rq = "balanced"
    if rq == "high":
        crf = min(crf, 16)
        preset = "fast"
    elif rq == "fast":
        crf = max(crf, 23)
        preset = "ultrafast"
    elif info["height"] >= 1000:
        crf = min(crf, 19)
        preset = "veryfast"

    # Слой игры (Split-Screen)
    from . import bgm as _bgm, game_layer as _gl, profiles as _profiles

    game_cfg = _gl.normalize_config(game_layer)
    game_path: Optional[Path] = _gl.resolve_path(game_cfg["clip_id"]) if game_cfg else None
    if not game_path:
        game_cfg = None
    top_h, bot_h = _gl.split_heights(h, game_cfg["split"]) if game_cfg else (h, 0)

    # Водяной знак (Brand Kit)
    wm_cfg = _profiles.normalize_watermark(watermark)
    wm_path: Optional[Path] = _profiles.resolve_asset(wm_cfg["asset_id"], "watermark") if wm_cfg else None
    if not wm_path:
        wm_cfg = None

    # Фоновая музыка (BGM auto-ducking)
    bgm_cfg = _bgm.normalize_config(bgm)
    bgm_path: Optional[Path] = _bgm.resolve_path(bgm_cfg["track_id"]) if bgm_cfg else None
    if not bgm_path:
        bgm_cfg = None

    # Интро / аутро бамперы
    intro_path: Optional[Path] = _profiles.resolve_asset(intro_asset_id, "intro") if intro_asset_id else None
    outro_path: Optional[Path] = _profiles.resolve_asset(outro_asset_id, "outro") if outro_asset_id else None
    intro_info: Dict[str, Any] = {}
    outro_info: Dict[str, Any] = {}
    if intro_path:
        try:
            intro_info = probe(intro_path)
            if not intro_info.get("has_video") or float(intro_info.get("duration") or 0) <= 0.1:
                intro_path = None
        except Exception:
            intro_path = None
    if outro_path:
        try:
            outro_info = probe(outro_path)
            if not outro_info.get("has_video") or float(outro_info.get("duration") or 0) <= 0.1:
                outro_path = None
        except Exception:
            outro_path = None
    has_bumpers = bool(intro_path or outro_path)
    total_duration = duration + (float(intro_info.get("duration") or 0.0) if intro_path else 0.0) + (
        float(outro_info.get("duration") or 0.0) if outro_path else 0.0
    )

    sharpen_base = info["width"] < w * 0.75
    audio_only = not info.get("has_video", bool(info["width"] and info["height"]))

    pip_cam = (pip or {}).get("cam") if (pip and pip.get("enabled", True) and not game_cfg and not audio_only) else None
    corner = (pip or {}).get("cam_corner")
    if pip_cam is None and corner and pip and pip.get("enabled", True) and not game_cfg and not audio_only:
        share = float((pip or {}).get("cam_share", 0.3))
        side = max(64, int(round(min(info["width"], info["height"]) * share)))
        margin = int(round(min(info["width"], info["height"]) * 0.02))
        cx = margin if "left" in corner else info["width"] - side - margin
        cy = margin if "top" in corner else info["height"] - side - margin
        pip_cam = {"x": cx, "y": cy, "w": side, "h": side}
    pip_size = int(round(min(w, h) * float((pip or {}).get("size", 0.28))))
    pip_size -= pip_size % 2
    pip_mask = None
    if not audio_only and pip_cam and pip_size >= 64:
        from . import pip as _pip

        pip_mask = _pip.ensure_mask(pip_size, int((pip or {}).get("radius", 20)))

    # Предвычисляем индексы входов FFmpeg (совпадают между _build_filters и _compose)
    next_idx = 1
    pip_idx = next_idx if pip_mask is not None else -1
    if pip_mask is not None:
        next_idx += 1
    game_idx = next_idx if (game_cfg and game_path is not None) else -1
    if game_idx >= 0:
        next_idx += 1
    wm_idx = next_idx if (wm_cfg and wm_path is not None) else -1
    if wm_idx >= 0:
        next_idx += 1
    bgm_idx = next_idx if (bgm_cfg and bgm_path is not None) else -1
    if bgm_idx >= 0:
        next_idx += 1
    intro_idx = next_idx if intro_path is not None else -1
    if intro_idx >= 0:
        next_idx += 1
    outro_idx = next_idx if outro_path is not None else -1
    if outro_idx >= 0:
        next_idx += 1

    def _zoom_pan_crop(in_lbl: str, out_lbl: str, tw: int, th: int,
                       zoom: float, pan: List[float], sharp_flag: bool = False) -> str:
        z = max(1.0, min(2.5, float(zoom or 1.0)))
        px = max(0.0, min(1.0, 0.5 + float(pan[0]) * 0.5))
        py = max(0.0, min(1.0, 0.5 + float(pan[1]) * 0.5))
        sw = int(round(tw * z))
        sh = int(round(th * z))
        sw += sw % 2
        sh += sh % 2
        sh_f = ",unsharp=5:5:0.7:5:5:0.0" if sharp_flag else ""
        return (
            f"{in_lbl}scale={sw}:{sh}:force_original_aspect_ratio=increase{sh_f},"
            f"crop={tw}:{th}:(iw-{tw})*{px:.3f}:(ih-{th})*{py:.3f},setsar=1{out_lbl}"
        )

    def _build_filters(path_used: Optional[Dict[str, Any]]) -> str:
        target_h = top_h if game_cfg else h
        is_dual_split = bool(
            not audio_only and mode == "auto" and not game_cfg
            and isinstance(path_used, dict) and path_used.get("layout") == "dual_split"
            and path_used.get("top") and path_used.get("bottom")
        )
        if audio_only:
            parts = [f"color=c=#0f0e16:s={w}x{target_h}:r=30:d={duration:.3f}[base]"]
            prefix = ""
        else:
            sharp = sharpen_base
            src = "[vsrc]" if segments else "[0:v]"
            prefix = _video_spans_graph(segments, base) + ";" if segments else ""
            if is_dual_split:
                half_h = h // 2
                half_h -= half_h % 2
                bot_half_h = h - half_h
                tbox = path_used["top"]
                bbox = path_used["bottom"]
                parts = [
                    f"{src}split=2[_ds_in1][_ds_in2]",
                    (
                        f"[_ds_in1]crop={int(tbox['w'])}:{int(tbox['h'])}:{int(tbox['x'])}:{int(tbox['y'])},"
                        f"scale={w}:{half_h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{half_h},fps=30,setsar=1,setpts=PTS-STARTPTS[_topn]"
                    ),
                    (
                        f"[_ds_in2]crop={int(bbox['w'])}:{int(bbox['h'])}:{int(bbox['x'])}:{int(bbox['y'])},"
                        f"scale={w}:{bot_half_h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{bot_half_h},fps=30,setsar=1,setpts=PTS-STARTPTS[_botn]"
                    ),
                    "[_topn][_botn]vstack=inputs=2[base]",
                ]
            elif game_cfg and (game_cfg["top_zoom"] > 1.01 or game_cfg["top_pan"] != [0.0, 0.0]):
                parts = [_zoom_pan_crop(src, "[base]", w, target_h,
                                        game_cfg["top_zoom"], game_cfg["top_pan"], sharp)]
            elif game_cfg and mode != "blur":
                # В Split-Screen заполняем верхний слой без размытых полос, сохраняя фокус по лицу.
                fx = focus_x
                if (
                    isinstance(path_used, dict)
                    and path_used.get("layout") != "dual_split"
                    and path_used.get("crop_w")
                    and info["width"]
                ):
                    xs = path_used.get("x") or []
                    if xs:
                        avg_x = sum(float(v) for v in xs) / len(xs)
                        fx = max(0.0, min(1.0, (avg_x + float(path_used["crop_w"]) * 0.5) / info["width"]))
                parts = [_crop_chain(w, target_h, fx, sharpen=sharp, src=src)]
            elif mode == "auto" and path_used and not game_cfg:
                sharp = float(path_used.get("crop_w", info["width"])) < w * 1.15
                parts = [_auto_chain(w, target_h, path_used, sharp, src)]
            elif mode == "blur" or (mode == "auto" and not path_used):
                parts = [_bg_chain(w, target_h, focus_x, sharp, src)]
            else:
                parts = [_crop_chain(w, target_h, focus_x, sharpen=sharp, src=src)]
            if pip_mask is not None and not is_dual_split and parts[0].rstrip().endswith("[base]"):
                from . import pip as _pip

                pos = (pip or {}).get("pos") or [0.72, 0.78]
                px = int(round(min(1.0, max(0.0, float(pos[0]))) * (w - pip_size)))
                py = int(round(min(1.0, max(0.0, float(pos[1]))) * (h - pip_size)))
                main_step = parts[0].rstrip()[:-len("[base]")] + "[_basem]"
                parts = [_pip.build_filters(pip_cam, pip_size, px, py, pip_mask, main_step, src)]

        if game_cfg and game_path is not None and game_idx >= 0:
            parts[0] = parts[0].rstrip()[:-len("[base]")] + "[_topv]"
            parts.append(
                _zoom_pan_crop(f"[{game_idx}:v]", "[_botv]", w, bot_h,
                               game_cfg["game_zoom"], game_cfg["game_pan"], False)
            )
            parts.append(
                "[_topv]fps=30,setsar=1,setpts=PTS-STARTPTS[_topn];"
                "[_botv]fps=30,setsar=1,setpts=PTS-STARTPTS[_botn];"
                "[_topn][_botn]vstack=inputs=2[base]"
            )

        cur_v = "[base]"

        # Плавный хук punch-in zoom (1.0 -> 1.08 за первые 3 сек) до субтитров
        if punch_in_zoom and not audio_only and not game_cfg and not is_dual_split:
            parts.append(
                f"{cur_v}fps=30,zoompan="
                f"z='if(lte(on,90),1+0.08*(on/90),max(1,1.08-0.08*((on-90)/45)))':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30,setsar=1[_pz]"
            )
            cur_v = "[_pz]"

        # Водяной знак (Brand Kit)
        if wm_cfg and wm_idx >= 0:
            wm_w = max(16, int(round(w * float(wm_cfg["scale"]))))
            wm_w -= wm_w % 2
            alpha = float(wm_cfg["opacity"])
            m = int(wm_cfg["margin"])
            pos_map = {
                "top-left": f"{m}:{m}",
                "top-right": f"W-w-{m}:{m}",
                "bottom-left": f"{m}:H-h-{m}",
                "bottom-right": f"W-w-{m}:H-h-{m}",
            }
            xy = pos_map.get(wm_cfg["position"], f"W-w-{m}:{m}")
            parts.append(
                f"[{wm_idx}:v]scale={wm_w}:-2,format=rgba,colorchannelmixer=aa={alpha:.2f}[_wm];"
                f"{cur_v}[_wm]overlay={xy}:format=auto[_wmed]"
            )
            cur_v = "[_wmed]"

        main_out_lbl = "[vmain]" if has_bumpers else "[v]"
        if ass_path is not None:
            fonts_dir = custom_fonts.libass_dir()
            _log_fonts_dir(fonts_dir)
            extra = ",fps=30,setsar=1,setpts=PTS-STARTPTS" if has_bumpers else ""
            parts.append(
                f"{cur_v}ass=filename='{_esc(ass_path)}':fontsdir='{_esc(fonts_dir)}':alpha=1"
                f"{extra},format=yuv420p{main_out_lbl}"
            )
        else:
            extra = ",fps=30,setsar=1,setpts=PTS-STARTPTS" if has_bumpers else ""
            parts.append(f"{cur_v}scale=in_range=auto:out_range=tv{extra},format=yuv420p{main_out_lbl}")
        return prefix + ";".join(parts)

    vlabel = "[v]"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    measured = (_measure_loudness(source, base, input_len, audio_track, segments or None)
                if info["has_audio"] else None)

    def _audio_filter() -> str:
        if measured:
            text = (
                "loudnorm=I=-14:TP=-1.5:LRA=11"
                f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
                f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
                f":offset={measured['target_offset']}:linear=true"
            )
        else:
            text = "loudnorm=I=-14:TP=-1.5:LRA=11"
        fade_out = max(0.0, duration - 0.06)
        return text + f",afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out:.3f}:d=0.05"

    _AFMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

    def _compose(video_args: List[str], filters: str, output: Path) -> List[str]:
        """Собирает команду целиком: так откат на другой энкодер — это пересборка."""
        threads = str(resources.ffmpeg_threads())
        built = resources.wrap_nice([ffmpeg(), "-y", "-hide_banner", "-v", "error", "-nostats",
                 "-progress", "pipe:1",
                 # декодер и фильтры тоже ограничиваем, иначе ffmpeg забирает все ядра
                 "-threads", threads, "-filter_threads", threads,
                 "-ss", f"{base:.3f}", "-t", f"{input_len:.3f}", "-i", str(source)])
        if pip_mask is not None:
            built += ["-loop", "1", "-framerate", "30", "-i", str(pip_mask)]
        game_has_audio = False
        if game_cfg and game_path is not None:
            raw_game_start = float(game_cfg.get("start") or 0.0)
            eff_game_start = raw_game_start
            g_info: Dict[str, Any] = {}
            try:
                g_info = probe(game_path)
                g_dur = float(g_info.get("duration") or 0.0)
                if g_dur > 0.5:
                    eff_game_start = raw_game_start % g_dur
                else:
                    eff_game_start = 0.0
            except Exception:
                eff_game_start = 0.0
            built += ["-stream_loop", "-1", "-ss", f"{eff_game_start:.2f}",
                      "-t", f"{duration + 1.0:.3f}", "-i", str(game_path)]
            if game_cfg.get("audio"):
                game_has_audio = bool(g_info.get("has_audio"))
        if wm_cfg and wm_path is not None:
            built += ["-i", str(wm_path)]
        if bgm_cfg and bgm_path is not None:
            built += ["-stream_loop", "-1", "-t", f"{duration + 1.0:.3f}", "-i", str(bgm_path)]
        if intro_path is not None:
            built += ["-i", str(intro_path)]
        if outro_path is not None:
            built += ["-i", str(outro_path)]

        graph = filters
        has_bgm = bool(bgm_cfg and bgm_idx >= 0)
        needs_audio_graph = bool(segments or game_has_audio or has_bgm or has_bumpers)
        audio_map = f"0:a:{max(0, int(audio_track))}?"
        use_graph_audio = False
        has_any_audio = bool(info["has_audio"] or game_has_audio or has_bgm or has_bumpers)

        if needs_audio_graph and has_any_audio:
            use_graph_audio = True
            if info["has_audio"]:
                if segments:
                    graph += f";{_audio_spans_graph(segments, base, audio_track)};[aconc]{_audio_filter()},{_AFMT}[amain]"
                else:
                    graph += f";[0:a:{max(0, int(audio_track))}]{_audio_filter()},{_AFMT}[amain]"
            if game_has_audio and game_idx >= 0:
                g_vol = "0.22" if info["has_audio"] else "0.5"
                graph += f";[{game_idx}:a]{_AFMT},volume={g_vol}[agame]"

            if has_bgm:
                vol_db = float(bgm_cfg["volume_db"])
                bgm_fo = max(0.0, duration - 1.0)
                graph += (
                    f";[{bgm_idx}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,{_AFMT},"
                    f"volume={vol_db:.1f}dB,afade=t=in:st=0:d=0.6,afade=t=out:st={bgm_fo:.3f}:d=1.0[bgm_pre]"
                )
                drop_db = max(0.0, vol_db - float(bgm_cfg.get("duck_db", -22.0)))
                if info["has_audio"] and bgm_cfg.get("ducking", True) and drop_db >= 1.0:
                    threshold = round(max(0.015, min(0.08, 0.06 - drop_db * 0.0025)), 4)
                    ratio = max(2, min(20, int(round(drop_db))))
                    graph += (
                        f";[amain]asplit=2[voice][voicemix];"
                        f"[bgm_pre][voice]sidechaincompress=threshold={threshold}:ratio={ratio}:attack=15:release=350:makeup=1[bgm_ducked]"
                    )
                    mix_inputs = ["[voicemix]", "[bgm_ducked]"]
                    if game_has_audio:
                        mix_inputs.append("[agame]")
                    graph += (
                        f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:"
                        f"dropout_transition=2:normalize=0,alimiter=limit=0.95[amain_mix]"
                    )
                    audio_map = "[amain_mix]"
                elif info["has_audio"]:
                    mix_inputs = ["[amain]", "[bgm_pre]"]
                    if game_has_audio:
                        mix_inputs.append("[agame]")
                    graph += (
                        f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:"
                        f"dropout_transition=2:normalize=0,alimiter=limit=0.95[amain_mix]"
                    )
                    audio_map = "[amain_mix]"
                else:
                    if game_has_audio:
                        graph += (
                            ";[bgm_pre][agame]amix=inputs=2:duration=first:"
                            "dropout_transition=2:normalize=0,alimiter=limit=0.95[amain_mix]"
                        )
                        audio_map = "[amain_mix]"
                    else:
                        audio_map = "[bgm_pre]"
            elif info["has_audio"] and game_has_audio:
                graph += ";[amain][agame]amix=inputs=2:duration=first:dropout_transition=2[amain_mix]"
                audio_map = "[amain_mix]"
            elif info["has_audio"]:
                audio_map = "[amain]"
            elif game_has_audio:
                audio_map = "[agame]"
            else:
                graph += f";anullsrc=r=48000:cl=stereo:d={duration:.3f}[asilent]"
                audio_map = "[asilent]"

        # Склейка интро/аутро вокруг основного клипа (после прожига ASS на основном клипе)
        if has_bumpers:
            concat_pairs: List[str] = []
            if intro_path is not None and intro_idx >= 0:
                i_dur = max(0.2, float(intro_info.get("duration") or 1.0))
                graph += (
                    f";[{intro_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h},fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v_intro]"
                )
                if intro_info.get("has_audio"):
                    graph += f";[{intro_idx}:a]{_AFMT},asetpts=PTS-STARTPTS[a_intro]"
                else:
                    graph += f";anullsrc=r=48000:cl=stereo:d={i_dur:.3f}[a_intro]"
                concat_pairs.append("[v_intro][a_intro]")

            graph += f";{audio_map}{_AFMT},asetpts=PTS-STARTPTS[a_main_c]"
            concat_pairs.append("[vmain][a_main_c]")

            if outro_path is not None and outro_idx >= 0:
                o_dur = max(0.2, float(outro_info.get("duration") or 1.0))
                graph += (
                    f";[{outro_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h},fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v_outro]"
                )
                if outro_info.get("has_audio"):
                    graph += f";[{outro_idx}:a]{_AFMT},asetpts=PTS-STARTPTS[a_outro]"
                else:
                    graph += f";anullsrc=r=48000:cl=stereo:d={o_dur:.3f}[a_outro]"
                concat_pairs.append("[v_outro][a_outro]")

            graph += f";{''.join(concat_pairs)}concat=n={len(concat_pairs)}:v=1:a=1[v][aout]"
            audio_map = "[aout]"

        built += ["-filter_complex", graph, "-map", vlabel]
        if has_any_audio:
            built += ["-map", audio_map]
            if not use_graph_audio:
                built += ["-af", _audio_filter()]
            built += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
        else:
            built += ["-an"]
        out_t = total_duration if has_bumpers else duration
        built += ["-threads", str(resources.ffmpeg_threads())] + video_args + [
            "-r", "30", "-t", f"{out_t:.3f}", "-movflags", "+faststart"]
        if not has_bumpers:
            built += ["-shortest"]
        built += [str(output)]
        return built

    encoder_mode = _encoder_mode()
    hw = hw_encoder(encoder_mode)
    try_other_gpu = sys.platform == "win32" and bool(hw)
    notify_gpu_fallback = sys.platform == "win32" and encoder_mode == "gpu"
    attempts = _encode_attempts(hw, crop_path, try_other_gpu)
    tried_cpu = False
    tail_text = ""
    stop_reason: Optional[str] = None
    code = 1
    # Все попытки пишут рядом с готовым файлом. При сбое старый MP4 остаётся доступен.
    with tempfile.TemporaryDirectory(prefix=".render-", dir=out_path.parent) as scratch:
        staged = Path(scratch) / out_path.name
        for attempt, (encoder, path_used) in enumerate(attempts):
            if encoder is None and not tried_cpu:
                if notify_gpu_fallback:
                    _announce_cpu_fallback(hw)
                elif hw:
                    print(f"[render] {hw} не сработал, повтор на libx264", file=sys.stderr, flush=True)
                tried_cpu = True
            staged.unlink(missing_ok=True)
            filters = _build_filters(path_used if mode == "auto" else None)
            cmd = _compose(_video_args(encoder, crf, preset, rq), filters, staged)
            if os.environ.get("VIRALCUT_DEBUG_RENDER"):
                print("[render] cmd:", " ".join(cmd), file=sys.stderr, flush=True)
            encode_dur = total_duration if has_bumpers else duration
            code, tail, stop_reason = _run_encode(cmd, encode_dur, on_progress if attempt == 0 else None)
            tail_text = "".join(tail)
            if stop_reason and not ((try_other_gpu or notify_gpu_fallback) and encoder):
                break
            if not stop_reason and code == 0 and staged.is_file() and staged.stat().st_size >= 10000:
                if on_progress:
                    on_progress(1.0)
                staged.replace(out_path)
                break
            if encoder is not None and (try_other_gpu or notify_gpu_fallback):
                detail = stop_reason or tail_text.strip() or f"код {code}, выходной MP4 неполный"
                print(f"[render] {encoder}: {detail[-460:]}", file=sys.stderr, flush=True)
            elif encoder is None and path_used is not None:
                print("[render] выражение кадрирования отвергнуто, повторю с упрощённым путём",
                      file=sys.stderr, flush=True)
        else:
            hint = ""
            if hw and "libx264" not in tail_text:
                hint = " Попробуйте отключить аппаратный энкодер: VIRALCUT_HW_ENCODE=0."
            raise MediaError("Не удалось отрендерить клип: " + tail_text[-600:] + hint)
        if stop_reason:
            raise MediaError(f"Рендер остановлен: {stop_reason}. Попробуйте ещё раз.")
    return {"path": out_path, "duration": round(duration, 2), "width": w, "height": h}


def snapshot(source: Path, out: Path, t: float = 0.0, width: int = 900) -> Path:
    """Один кадр исходника в JPEG — для выбора окна камеры в интерфейсе."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(source),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)]
    proc = run(cmd, timeout=90)
    if proc.returncode != 0 or not out.exists():
        raise MediaError("Не удалось получить кадр: " + (proc.stderr or "")[-200:])
    return out


def make_preview(clip_path: Path, out_path: Path, width: int = 540) -> Optional[Path]:
    """Лёгкая копия для быстрого предпросмотра в интерфейсе."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", str(clip_path),
           "-vf", f"scale={width}:-2", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "30", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
           str(out_path)]
    proc = run(cmd)
    return out_path if proc.returncode == 0 and out_path.exists() else None


def make_thumb(clip_path: Path, out_path: Path, at: float = 0.6) -> Optional[Path]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(clip_path),
           "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3", str(out_path)]
    proc = run(cmd)
    return out_path if proc.returncode == 0 and out_path.exists() else None


def make_filmstrip(source: Path, out_path: Path, start: float, end: float,
                   frames: int = 10, thumb_w: int = 96, thumb_h: int = 58) -> Path:
    """Горизонтальная лента кадров (filmstrip) для визуального таймлайна в редакторе."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.5, float(end) - float(start))
    fps = max(0.05, frames / dur)
    vf = (
        f"fps={fps:.4f},scale={thumb_w}:{thumb_h}:force_original_aspect_ratio=increase,"
        f"crop={thumb_w}:{thumb_h},tile={frames}x1"
    )
    tmp = out_path.with_name(f".strip_{os.urandom(3).hex()}.jpg")
    cmd = [
        ffmpeg(), "-y", "-v", "error",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", str(source),
        "-frames:v", "1", "-vf", vf, "-q:v", "4", str(tmp),
    ]
    proc = run(cmd, timeout=45)
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 500:
        tmp.unlink(missing_ok=True)
        raise MediaError("Не удалось собрать ленту кадров")
    tmp.replace(out_path)
    return out_path


