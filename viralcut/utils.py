"""Мелкие утилиты: запуск ffmpeg, зондирование медиа, работа с временем."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import ffmpeg

# На Windows дочерние ffmpeg/yt-dlp не должны открывать чёрные консольные окна.
NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


def subprocess_kwargs() -> Dict[str, Any]:
    """Флаги запуска дочерних процессов (без окна на Windows + низкий приоритет)."""
    from . import resources

    kwargs = resources.subprocess_kwargs()
    if NO_WINDOW and "creationflags" not in kwargs:
        kwargs["creationflags"] = NO_WINDOW
    return kwargs


class MediaError(Exception):
    pass


def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    from . import resources

    return subprocess.run(resources.wrap_nice(cmd), capture_output=True, text=True,
                          timeout=timeout, errors="replace", **subprocess_kwargs())


_TIME_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM_RE = re.compile(
    r"Stream #0:(\d+)(?:\[[^\]]+\])?(?:\(([A-Za-z0-9_-]{2,15})\))?: Audio: ([^,]+)"
)


def _to_seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def probe(path: Path) -> Dict[str, Any]:
    """Достаёт длительность, размеры, fps и наличие звука из вывода ffmpeg."""
    proc = run([ffmpeg(), "-hide_banner", "-i", str(path)])
    text = proc.stderr or ""
    info: Dict[str, Any] = {
        "duration": 0.0, "width": 0, "height": 0, "fps": 30.0,
        "has_audio": False, "has_video": False,
    }
    m = _TIME_RE.search(text)
    if m:
        info["duration"] = _to_seconds(*m.groups())

    vm = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if vm:
        info["width"], info["height"] = int(vm.group(1)), int(vm.group(2))
        info["has_video"] = info["width"] > 0 and info["height"] > 0
    fm = re.search(r"(\d+(?:\.\d+)?)\s+fps", text)
    if fm:
        info["fps"] = float(fm.group(1))
    info["has_audio"] = "Audio:" in text
    info["audio_tracks"] = len(_AUDIO_STREAM_RE.findall(text))

    # Поворот из метаданных (вертикальные видео с телефона: ±90° и ±270°)
    rm = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", text)
    if rm and info["has_video"]:
        angle = abs(float(rm.group(1))) % 360
        if (75 <= angle <= 105) or (255 <= angle <= 285):
            info["width"], info["height"] = info["height"], info["width"]
            info["rotation"] = 90 if angle <= 105 else 270
    if not info["has_video"] and not (info["has_audio"] and info["duration"] > 0):
        raise MediaError("Не удалось прочитать медиафайл (повреждён или неподдерживаемый формат).")
    return info


def audio_tracks(path: Path) -> List[Dict[str, Any]]:
    """Звуковые дорожки файла: порядок, язык, каналы — по выводу ffmpeg."""
    try:
        proc = run([ffmpeg(), "-hide_banner", "-i", str(path)], timeout=30)
        text = (proc.stderr or "") + (proc.stdout or "")
    except Exception:  # noqa: BLE001
        return []
    tracks: List[Dict[str, Any]] = []
    lines = text.splitlines()
    order = 0
    for idx, line in enumerate(lines):
        m = _AUDIO_STREAM_RE.search(line)
        if not m:
            continue
        title = ""
        mt = re.search(r"\(title: ([^)]+)\)", line)
        if mt:
            title = mt.group(1).strip()
        else:
            # FFmpeg печатает метаданные дорожки на следующих строках (Metadata: / title : ...)
            for follow in lines[idx + 1: idx + 8]:
                if re.match(r"^\s*Stream #", follow):
                    break
                mt2 = re.match(r"^\s*title\s*:\s*(.+)$", follow, re.I)
                if mt2:
                    title = mt2.group(1).strip()
                    break
        channels: Any = 2
        if re.search(r"\bmono\b", line, re.I):
            channels = 1
        elif re.search(r"\bstereo\b", line, re.I):
            channels = 2
        else:
            mch = re.search(r",\s*(\d+(?:\.\d+)?)\s*(?:ch|channels|\()", line, re.I)
            if mch:
                val = float(mch.group(1))
                channels = int(val) if val.is_integer() else val
        tracks.append({"index": order, "stream": int(m.group(1)),
                       "language": (m.group(2) or "").lower(),
                       "title": title, "channels": channels})
        order += 1
    return tracks


def media_duration(path: Path) -> float:
    """Длительность любого медиа, включая аудио без видеодорожки."""
    proc = run([ffmpeg(), "-hide_banner", "-i", str(path)])
    m = _TIME_RE.search(proc.stderr or "")
    return _to_seconds(*m.groups()) if m else 0.0


def extract_audio(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", str(src), "-vn",
           "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)]
    proc = run(cmd)
    if proc.returncode != 0 or not dst.exists():
        raise MediaError(f"Не удалось извлечь аудиодорожку: {(proc.stderr or '')[-300:]}")
    return dst


def extract_asr_audio(src: Path, dst: Path, sample_rate: int = 16000, *,
                      audio_track: Optional[int] = None,
                      window: Optional[Tuple[float, float]] = None) -> Path:
    """Аудио для распознавания речи: без гула, шипения и перепадов громкости.

    Распознавание ошибается в первую очередь на «грязном» звуке: низкочастотный
    гул, шипение и тихие реплики. Поэтому перед Whisper прогоняем:
    срез ниже 70 Гц и выше 7.8 кГц (речь живёт между ними), мягкое
    шумоподавление и выравнивание громкости по фразам.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    base = [ffmpeg(), "-y", "-v", "error"]
    if window is not None:
        start, end = window
        base += ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"]
    base += ["-i", str(src), "-vn", "-ac", "1", "-ar", str(sample_rate)]
    if audio_track is not None:
        base += ["-map", f"0:a:{audio_track}"]
    filters = "highpass=f=70,lowpass=f=7800,afftdn=nr=10:nf=-40,dynaudnorm=f=200:g=10"
    proc = run(base + ["-af", filters, "-c:a", "pcm_s16le", str(dst)])
    if proc.returncode != 0 or not dst.exists():
        # старые сборки ffmpeg без afftdn/dynaudnorm — хотя бы срезы и моно
        proc = run(base + ["-af", "highpass=f=70,lowpass=f=7800",
                           "-c:a", "pcm_s16le", str(dst)])
    if proc.returncode != 0 or not dst.exists():
        proc = run(base + ["-c:a", "pcm_s16le", str(dst)])
    if proc.returncode != 0 or not dst.exists():
        raise MediaError(f"Не удалось извлечь аудиодорожку: {(proc.stderr or '')[-300:]}")
    return dst


def iter_audio_mono(src: Path, sample_rate: int = 16000, *,
                    audio_track: Optional[int] = None,
                    block_seconds: float = 30.0) -> Any:
    """Отдаёт аудио кусками по block_seconds секунд (float32 [-1, 1]).

    Часовое видео целиком — это ~230 МБ float32 в памяти, а трёхчасовое уже
    ~700 МБ: на машинах с 8 ГБ приложение вылетало на анализе. Потоковое
    чтение держит в памяти один блок (~2 МБ) и не зависит от длины файла.
    """
    import numpy as np

    cmd = [ffmpeg(), "-v", "error", "-i", str(src), "-vn", "-ac", "1",
           "-ar", str(sample_rate), "-f", "s16le"]
    if audio_track is not None:
        cmd += ["-map", f"0:a:{audio_track}"]
    cmd += ["-"]
    block_bytes = max(2, int(block_seconds * sample_rate) * 2)
    # выравниваем по кадру, чтобы блоки стыковались без «щелчка» на границе
    block_bytes -= block_bytes % 4
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            **subprocess_kwargs())
    try:
        carry = b""
        while True:
            chunk = proc.stdout.read(block_bytes) if proc.stdout else b""
            if not chunk:
                break
            if carry:
                chunk = carry + chunk
                carry = b""
            if len(chunk) % 2:
                carry = chunk[-1:]
                chunk = chunk[:-1]
            if chunk:
                yield np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        try:
            if proc.stdout:
                proc.stdout.close()
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass


def read_audio_mono(src: Path, sample_rate: int = 16000, *,
                    audio_track: Optional[int] = None) -> Any:
    """Возвращает numpy-массив float32 [-1, 1] с аудио."""
    import numpy as np

    cmd = [ffmpeg(), "-v", "error", "-i", str(src), "-vn", "-ac", "1",
           "-ar", str(sample_rate), "-f", "s16le"]
    if audio_track is not None:
        cmd += ["-map", f"0:a:{audio_track}"]
    cmd += ["-"]
    proc = subprocess.run(cmd, capture_output=True, **subprocess_kwargs())
    if proc.returncode != 0 or not proc.stdout:
        raise MediaError("Не удалось прочитать аудио.")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def fmt_ts(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    if h:
        return f"{h}:{m:02d}:{s:04.1f}"
    return f"{m}:{s:04.1f}"


def ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def parse_vtt(path: Path) -> List[Dict[str, Any]]:
    """Парсер WebVTT (HH:MM:SS.mmm и MM:SS.mmm) со склейкой плывущих строк YouTube."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    segs: List[Dict[str, Any]] = []
    ts = re.compile(
        r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})"
    )
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() and not ln.startswith(("WEBVTT", "NOTE", "Kind:", "Language:"))]
        stamp = None
        text_lines = []
        for ln in lines:
            m = ts.search(ln)
            if m:
                g = [int(v or 0) for v in m.groups()]
                stamp = (g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                         g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000)
            elif stamp:
                clean = re.sub(r"<[^>]+>", "", ln).strip()
                if clean:
                    text_lines.append(clean)
        if not stamp or not text_lines:
            continue
        text = re.sub(r"\s+", " ", " ".join(text_lines)).strip()
        if not text:
            continue
        segs.append({"start": stamp[0], "end": stamp[1], "text": text})
    # склейка дублей и плывущих автосубтитров YouTube (где строка 2 повторяет конец строки 1)
    out: List[Dict[str, Any]] = []
    for s in segs:
        text = s["text"]
        if out:
            prev = out[-1]["text"]
            if text == prev:
                out[-1]["end"] = max(out[-1]["end"], s["end"])
                continue
            if text.startswith(prev + " "):
                text = text[len(prev):].strip()
            else:
                prev_words = prev.split()
                cur_words = text.split()
                overlap = 0
                for k in range(min(len(prev_words), len(cur_words)), 0, -1):
                    if prev_words[-k:] == cur_words[:k]:
                        overlap = k
                        break
                if overlap:
                    text = " ".join(cur_words[overlap:]).strip()
            if not text:
                out[-1]["end"] = max(out[-1]["end"], s["end"])
                continue
        words_raw = text.split()
        span = max(0.05, s["end"] - s["start"])
        step = span / len(words_raw)
        words = [{"word": w, "start": s["start"] + i * step, "end": s["start"] + (i + 1) * step}
                 for i, w in enumerate(words_raw)]
        out.append({"start": s["start"], "end": s["end"], "text": text, "words": words})
    return out
