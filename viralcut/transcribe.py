"""Транскрипция: локальный faster-whisper с проверкой сомнительных мест.

Качество важнее скорости, но без больших моделей:

* аудио для распознавания чистится (high-pass, low-pass, шумоподавление,
  выравнивание громкости) — движку достаётся речь, а не гул и перепады уровня;
* декодирование идёт beam-search с подсказкой-промптом и запасными
  температурами, чтобы не «залипать» на одной гипотезе;
* сегменты с низкой уверенностью перепроверяются повторно: вырезаем окно,
  декодируем ещё раз с контекстом соседей и оставляем вариант, у которого
  выше вероятность модели.

Всё это не требует скачивать другую модель и работает на том же `small`.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import utils
from .config import (DATA_DIR, MODELS_DIR, WHISPER_COMPUTE, WHISPER_DEVICE,
                     WHISPER_LOCAL_DIR, WHISPER_MODEL, ffmpeg)
from .errors import Cancelled

# Всё, что качает HuggingFace, держим внутри папки проекта.
os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_MODEL = None
_MODEL_LONG = None
_MODEL_LOCK = threading.Lock()
ProgressCb = Optional[Callable[[float, str], None]]

# --- параметры распознавания -------------------------------------------------

# Beam-search вместо жадного декодирования: заметно меньше ошибок в словах.
BEAM_SIZE = max(1, int(os.environ.get("VIRALCUT_WHISPER_BEAM", "5")))
# Сколько сомнительных сегментов перепроверять (0 — выключить).
RECHECK_LIMIT = max(0, int(os.environ.get("VIRALCUT_WHISPER_RECHECK", "8")))
# Батчевое декодирование: на 6-минутной записи 2.6× быстрее и точнее, потому что
# faster-whisper режет аудио по VAD и подаёт пачки в модель вместо одного потока.
BATCH_SIZE = max(1, int(os.environ.get("VIRALCUT_WHISPER_BATCH_SIZE", "8")))
BATCH_MIN_SECONDS = float(os.environ.get("VIRALCUT_WHISPER_BATCH_MIN", "60"))
# Порог уверенности, ниже которого сегмент считаем сомнительным.
WEAK_LOGPROB = float(os.environ.get("VIRALCUT_WHISPER_WEAK_LOGP", "-0.62"))
# Языки с кириллицей: используются для выбора подсказки и проверки письменности.
_CYRILLIC_LANGS = ("ru", "uk", "be", "kk", "bg", "sr", "mk")
# Подсказка для декодера подбирается строго под язык речи, чтобы русский промпт
# никогда не смещал декодирование английской или автоопределяемой речи в кириллицу.
_ASR_PROMPT_ENV = os.environ.get("VIRALCUT_WHISPER_PROMPT")
ASR_PROMPT_RU = (
    "ViralCut, вертикальные клипы, субтитры, подкаст, интервью. "
    "Русская речь с пунктуацией; имена и термины пишутся так же, как в оригинале."
)
ASR_PROMPT_EN = (
    "Podcast, interview, educational video. "
    "Clear English speech with natural punctuation and capitalization."
)
ASR_PROMPT = _ASR_PROMPT_ENV if _ASR_PROMPT_ENV is not None else ASR_PROMPT_RU


def _prompt_for_language(language: Optional[str]) -> Optional[str]:
    if _ASR_PROMPT_ENV is not None:
        return _ASR_PROMPT_ENV or None
    code = (language or "").strip().lower().replace("_", "-").split("-", 1)[0]
    if not code or code == "auto":
        return None
    if code in _CYRILLIC_LANGS:
        return ASR_PROMPT_RU
    if code == "en":
        return ASR_PROMPT_EN
    return None


class TranscriptionError(Exception):
    pass


class NoSpeechError(TranscriptionError):
    pass


WHISPER_CATALOG: List[Dict[str, Any]] = [
    {
        "key": "small",
        "name": "Small",
        "repo": "Systran/faster-whisper-small",
        "size_label": "465 МБ",
        "params": "244 млн параметров",
        "desc": "Быстрая базовая точность. Подходит для CPU и видеокарт.",
        "speed": "Быстро",
        "accuracy": "Базовая",
        "bundled": True,
    },
    {
        "key": "medium",
        "name": "Medium",
        "repo": "Systran/faster-whisper-medium",
        "size_label": "1.5 ГБ",
        "params": "769 млн параметров",
        "desc": "Высокая точность и лучший разбор русской и английской речи. Требует ~3–4 ГБ RAM.",
        "speed": "Средне",
        "accuracy": "Высокая",
        "bundled": False,
    },
    {
        "key": "large-v3-turbo",
        "name": "Large v3 Turbo",
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_label": "1.6 ГБ",
        "params": "809 млн параметров",
        "desc": "Максимальное качество почти как Large v3 при скорости Medium. Рекомендуется для GPU (CUDA).",
        "speed": "Средне",
        "accuracy": "Максимальная",
        "bundled": False,
    },
]
_MODEL_DOWNLOADS: Dict[str, Dict[str, Any]] = {}
_DL_LOCK = threading.Lock()
_ACTIVE_TRANSCRIBES = 0
_ACTIVE_MODEL_KEY: Optional[str] = None


def active_model_key() -> str:
    try:
        from . import settings as app_settings

        chosen = str(app_settings.get().get("whisper_model") or "").strip()
        if any(m["key"] == chosen for m in WHISPER_CATALOG):
            return chosen
    except Exception:
        pass
    return WHISPER_MODEL if any(m["key"] == WHISPER_MODEL for m in WHISPER_CATALOG) else "small"


def _hf_cache_dir(repo: str) -> Path:
    return MODELS_DIR / ("models--" + repo.replace("/", "--"))


def is_model_downloaded(key: str) -> bool:
    spec = next((m for m in WHISPER_CATALOG if m["key"] == key), None)
    if not spec:
        return False
    if key == "small" and WHISPER_LOCAL_DIR and (Path(WHISPER_LOCAL_DIR) / "model.bin").is_file():
        return True
    try:
        cache_dir = _hf_cache_dir(spec["repo"])
        for path in cache_dir.glob("snapshots/*/model.bin"):
            if path.stat().st_size > 1024 * 1024:
                return True
    except Exception:
        pass
    return False


def models_status() -> Dict[str, Any]:
    """Статус всех моделей Whisper для менеджера в настройках."""
    active = active_model_key()
    cuda = _cuda_available()
    items: List[Dict[str, Any]] = []
    with _DL_LOCK:
        dl_snapshot = {k: dict(v) for k, v in _MODEL_DOWNLOADS.items()}
    for spec in WHISPER_CATALOG:
        key = spec["key"]
        dl = dl_snapshot.get(key) or {}
        ready = is_model_downloaded(key)
        items.append({
            **spec,
            "downloaded": ready,
            "active": key == active,
            "downloading": bool(dl.get("downloading")),
            "error": dl.get("error") or "",
            "can_delete": bool(ready and not (key == "small" and WHISPER_LOCAL_DIR and (Path(WHISPER_LOCAL_DIR) / "model.bin").is_file())),
        })
    return {"active": active, "cuda": cuda, "models": items}


def download_model_async(key: str) -> Dict[str, Any]:
    spec = next((m for m in WHISPER_CATALOG if m["key"] == key), None)
    if not spec:
        raise ValueError("Неизвестная модель Whisper")
    if is_model_downloaded(key):
        return {"ok": True, "already": True, "key": key}
    with _DL_LOCK:
        cur = _MODEL_DOWNLOADS.get(key)
        if cur and cur.get("downloading"):
            return {"ok": True, "downloading": True, "key": key}
        _MODEL_DOWNLOADS[key] = {"downloading": True, "error": ""}

    def _worker() -> None:
        try:
            from huggingface_hub import snapshot_download

            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            snapshot_download(
                repo_id=spec["repo"],
                cache_dir=str(MODELS_DIR),
                allow_patterns=["model.bin", "config.json", "tokenizer.json",
                                "vocabulary.txt", "vocabulary.json", "preprocessor_config.json"],
            )
            with _DL_LOCK:
                _MODEL_DOWNLOADS[key] = {"downloading": False, "error": ""}
        except Exception as exc:  # noqa: BLE001
            with _DL_LOCK:
                _MODEL_DOWNLOADS[key] = {"downloading": False, "error": str(exc)[:220]}

    threading.Thread(target=_worker, name=f"whisper-dl-{key}", daemon=True).start()
    return {"ok": True, "downloading": True, "key": key}


def select_model(key: str) -> Dict[str, Any]:
    global _MODEL, _MODEL_LONG, _ACTIVE_MODEL_KEY
    spec = next((m for m in WHISPER_CATALOG if m["key"] == key), None)
    if not spec:
        raise ValueError("Неизвестная модель Whisper")
    if not is_model_downloaded(key):
        raise ValueError("Сначала скачайте эту модель")
    from . import settings as app_settings

    app_settings.update({"whisper_model": key})
    with _MODEL_LOCK:
        _MODEL = None
        _MODEL_LONG = None
        _ACTIVE_MODEL_KEY = key
    return models_status()


def delete_model(key: str) -> Dict[str, Any]:
    global _MODEL, _MODEL_LONG, _ACTIVE_MODEL_KEY
    spec = next((m for m in WHISPER_CATALOG if m["key"] == key), None)
    if not spec:
        raise ValueError("Неизвестная модель Whisper")
    if key == "small" and WHISPER_LOCAL_DIR and (Path(WHISPER_LOCAL_DIR) / "model.bin").is_file():
        raise ValueError("Встроенную модель Small нельзя удалить")
    with _DL_LOCK:
        if (_MODEL_DOWNLOADS.get(key) or {}).get("downloading"):
            raise RuntimeError("Модель сейчас скачивается — дождитесь окончания загрузки")
    with _MODEL_LOCK:
        if _ACTIVE_TRANSCRIBES > 0 and (_ACTIVE_MODEL_KEY == key or active_model_key() == key):
            raise RuntimeError("Модель сейчас используется в активной задаче распознавания")
        cache_dir = _hf_cache_dir(spec["repo"])
        if active_model_key() == key:
            from . import settings as app_settings

            app_settings.update({"whisper_model": "small"})
            _MODEL = None
            _MODEL_LONG = None
            _ACTIVE_MODEL_KEY = "small"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
    return models_status()


def model_cached() -> bool:
    """Модель уже есть локально (внутри .app или в кэше — сеть не нужна)."""
    return is_model_downloaded(active_model_key())


def model_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _cuda_available() -> bool:
    """Проверяет, есть ли CUDA GPU для faster-whisper (ctranslate2) и не выключен ли GPU."""
    if os.environ.get("VIRALCUT_WHISPER_CUDA", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from . import settings as app_settings

        if app_settings.get().get("encoder") == "cpu":
            return False
    except Exception:
        pass
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def _reset_model(long_audio: bool = False) -> None:
    global _MODEL, _MODEL_LONG
    with _MODEL_LOCK:
        if long_audio:
            _MODEL_LONG = None
        else:
            _MODEL = None


def _get_model(long_audio: bool = False):
    global _MODEL, _MODEL_LONG, _ACTIVE_MODEL_KEY
    with _MODEL_LOCK:
        wanted_key = active_model_key()
        if _ACTIVE_MODEL_KEY != wanted_key:
            _MODEL = None
            _MODEL_LONG = None
            _ACTIVE_MODEL_KEY = wanted_key
        if long_audio and _MODEL_LONG is not None:
            return _MODEL_LONG
        if not long_audio and _MODEL is not None:
            return _MODEL
        from faster_whisper import WhisperModel

        local_dir = Path(WHISPER_LOCAL_DIR) if (wanted_key == "small" and WHISPER_LOCAL_DIR) else None
        model_ref = str(local_dir) if local_dir and (local_dir / "model.bin").is_file() else wanted_key
        # Для длинных аудио не используем экспериментальный MPS — на нём
        # ctranslate2 может «зависнуть» на середине многочасового файла.
        if WHISPER_DEVICE == "auto":
            if sys.platform == "darwin":
                candidates = [("cpu", WHISPER_COMPUTE)] if long_audio else [("mps", "float16"), ("cpu", WHISPER_COMPUTE)]
            elif _cuda_available():
                candidates = [("cuda", "float16"), ("cuda", "int8_float16"), ("cpu", WHISPER_COMPUTE)]
            else:
                candidates = [("cpu", WHISPER_COMPUTE)]
        else:
            candidates = [(WHISPER_DEVICE, WHISPER_COMPUTE)]
        last_exc = None
        model = None
        for device, compute in candidates:
            try:
                from . import resources

                model = WhisperModel(
                    model_ref,
                    device=device,
                    compute_type=compute,
                    download_root=str(MODELS_DIR),
                    cpu_threads=resources.whisper_threads(),
                    num_workers=1,
                )
                model._vc_device = device  # type: ignore[attr-defined]
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                model = None
                print(f"[whisper] {device}/{compute} недоступен: {str(exc)[:200]}",
                      file=sys.stderr, flush=True)
        if model is None:
            raise TranscriptionError(
                "Локальная модель распознавания речи недоступна. "
                f"Причина: {str(last_exc)[:200]}"
            )
        if long_audio:
            _MODEL_LONG = model
        else:
            _MODEL = model
        return model


def _decode(model, audio: Path, language: Optional[str], vad: bool,
            prompt: Optional[str] = None, beam: Optional[int] = None,
            temperature=None, condition: bool = True):
    """Один проход декодирования с настройками под качество."""
    effective_prompt = prompt if prompt is not None else _prompt_for_language(language)
    return model.transcribe(
        str(audio),
        language=language or None,
        task="transcribe",
        beam_size=beam or BEAM_SIZE,
        best_of=beam or BEAM_SIZE,
        temperature=[0.0, 0.2, 0.4, 0.6] if temperature is None else temperature,
        length_penalty=1.0,
        repetition_penalty=1.05,
        no_repeat_ngram_size=3,
        condition_on_previous_text=condition,
        prompt_reset_on_temperature=0.5,
        initial_prompt=effective_prompt,
        vad_filter=vad,
        vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200} if vad else None,
        word_timestamps=True,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        language_detection_threshold=0.5,
        language_detection_segments=1,
    )


def _decode_batched(model, audio: Path, language: Optional[str], vad: bool):
    """Пачечное декодирование (faster-whisper BatchedInferencePipeline)."""
    from faster_whisper import BatchedInferencePipeline

    pipe = BatchedInferencePipeline(model=model)
    effective_prompt = _prompt_for_language(language)
    kwargs = dict(
        language=language or None,
        task="transcribe",
        beam_size=BEAM_SIZE,
        condition_on_previous_text=True,
        vad_filter=vad,
        word_timestamps=True,
        batch_size=BATCH_SIZE,
    )
    if effective_prompt:
        kwargs["initial_prompt"] = effective_prompt
    try:
        return pipe.transcribe(str(audio), **kwargs)
    except TypeError:
        # в других версиях части аргументов нет — повторяем с минимумом
        for key in ("condition_on_previous_text", "initial_prompt"):
            kwargs.pop(key, None)
        return pipe.transcribe(str(audio), **kwargs)


def _segment_payload(seg, offset: float) -> Dict[str, Any]:
    text = (seg.text or "").strip()
    words = []
    for word in (seg.words or []):
        token = (word.word or "").strip()
        if not token:
            continue
        words.append({
            "word": token,
            "start": round(float(word.start) + offset, 3),
            "end": round(float(word.end) + offset, 3),
        })
    if not words and text:
        tokens = text.split()
        step = max(0.05, (seg.end - seg.start) / max(1, len(tokens)))
        words = [{
            "word": token,
            "start": round(seg.start + i * step + offset, 3),
            "end": round(seg.start + (i + 1) * step + offset, 3),
        } for i, token in enumerate(tokens)]
    return {
        "start": round(float(seg.start) + offset, 3),
        "end": round(float(seg.end) + offset, 3),
        "text": text,
        "words": words,
        "quality": {
            "avg_logprob": round(float(getattr(seg, "avg_logprob", 0.0) or 0.0), 3),
            "no_speech_prob": round(float(getattr(seg, "no_speech_prob", 0.0) or 0.0), 3),
        },
    }


def _consume(model, path: Path, language: Optional[str], use_vad: bool,
             offset: float, total_duration: float,
             on_progress: ProgressCb, batched: bool = False) -> Tuple[List[Dict[str, Any]], Any]:
    def _iterate(segments_iter) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for seg in segments_iter:
            payload = _segment_payload(seg, offset)
            if not payload["text"]:
                continue
            rows.append(payload)
            if on_progress and total_duration:
                on_progress(min(0.99, (offset + float(seg.end)) / total_duration),
                            "Распознавание речи")
        return rows

    if batched:
        try:
            segments, tinfo = _decode_batched(model, path, language, use_vad)
            return _iterate(segments), tinfo
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — пачечный режим не должен ломать распознавание
            print(f"[whisper] пачечный режим не сработал: {str(exc)[:160]}", file=sys.stderr, flush=True)
    segments, tinfo = _decode(model, path, language, use_vad)
    return _iterate(segments), tinfo


def _transcribe_span(model, path: Path, language: Optional[str], offset: float,
                     total_duration: float, on_progress: ProgressCb, batched: bool = False):
    """Пробует с VAD, при ошибке ONNX повторяет без VAD."""
    try:
        return _consume(model, path, language, True, offset, total_duration, on_progress, batched)
    except Exception as exc:  # noqa: BLE001
        low = str(exc).lower()
        if "onnxruntime" not in low and "vad" not in low and "fusedconv" not in low:
            raise
        traceback.print_exc()
        if on_progress:
            on_progress(min(0.99, offset / max(1.0, total_duration)),
                        "VAD недоступен · распознавание без фильтра тишины")
        return _consume(model, path, language, False, offset, total_duration, on_progress, batched)


_PROBE_SECONDS = 60.0
_PROBE_MIN_PROBABILITY = 0.55
_CYR_RE = re.compile(r"[А-Яа-яЁё]")
_LAT_RE = re.compile(r"[A-Za-z]")


def _probe_windows(duration: float) -> List[Tuple[float, float]]:
    """Окна для определения языка: начало и середина записи.

    Одно окно может попасть на музыку или тишину — поэтому берём два и
    складываем вероятности: так интро не перевешивает всю запись.
    """
    if duration <= _PROBE_SECONDS * 1.5:
        return [(0.0, duration)]
    first = min(60.0, duration * 0.15)
    second_start = min(max(0.0, duration * 0.55), duration - _PROBE_SECONDS)
    return [(first, first + _PROBE_SECONDS), (second_start, second_start + _PROBE_SECONDS)]


def _probe_language(model, wav: Path, duration: float,
                    workdir: Path) -> Optional[Tuple[str, float]]:
    """Определяет язык по фрагментам с речью, а не по первым 30 секундам.

    Whisper смотрит на начало записи: если там музыка, интро или тишина, язык
    может «уехать» в английский. Здесь язык голосуется по двум окнам, а
    основной проход потом идёт уже с явным языком.
    """
    if duration < 2.0 or not wav.exists():
        return None
    totals: Dict[str, float] = {}
    votes = 0
    for index, (start, end) in enumerate(_probe_windows(duration)):
        span = max(0.0, min(end, duration) - start)
        if span < 2.0:
            continue
        clip = workdir / f"probe_{index}_{int(start)}_{os.urandom(2).hex()}.wav"
        try:
            if not _cut_window(wav, clip, start, start + span):
                continue
            _segments, info = _decode(model, clip, None, True, beam=1,
                                      temperature=[0.0], condition=False)
            lang = getattr(info, "language", None)
            probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            if lang:
                totals[str(lang)] = totals.get(str(lang), 0.0) + probability
                votes += 1
        except Exception:  # noqa: BLE001 — проба не должна ломать распознавание
            continue
        finally:
            try:
                clip.unlink(missing_ok=True)
            except OSError:
                pass
    if not totals:
        return None
    best = max(totals.items(), key=lambda item: item[1])
    score = best[1] / votes
    if score < _PROBE_MIN_PROBABILITY:
        return None
    return best[0], round(score, 3)


def _script_counts(text: str) -> Tuple[int, int]:
    return len(_CYR_RE.findall(text or "")), len(_LAT_RE.findall(text or ""))


def _expected_script(language: str) -> str:
    code = (language or "").lower()[:2]
    if code in _CYRILLIC_LANGS:
        return "cyr"
    if code == "en":
        return "lat"
    return ""


def subtitle_script_mismatch(segments: List[Dict[str, Any]], language: str) -> bool:
    cyr, lat = _script_counts(" ".join(str(seg.get("text") or "") for seg in segments))
    total = cyr + lat
    expected = _expected_script(language)
    return total >= 20 and (
        (expected == "cyr" and cyr < 0.35 * total) or
        (expected == "lat" and lat < 0.35 * total)
    )


def _fix_language_mismatch(model, wav: Path, workdir: Path, segments: List[Dict[str, Any]],
                           detected: Optional[str], on_progress: ProgressCb,
                           probe: Optional[str] = None
                           ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """При несовпадении письменности повторяет расшифровку на языке аудио."""
    target = (probe or detected or "").strip()
    if not subtitle_script_mismatch(segments, target):
        return segments, detected
    if on_progress:
        on_progress(0.997, f"Проверка языка · повторно на «{target}»")
    print(f"[whisper] текст не на языке {target!r} — перераспознаю на {target!r}",
          file=sys.stderr, flush=True)
    duration = max(0.5, float(segments[-1].get("end") or 0.0))
    try:
        fresh, _info = _transcribe_span(model, wav, target, 0.0, duration, None, False)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return segments, detected
    if not fresh:
        return segments, detected
    new_text = " ".join(str(seg.get("text") or "") for seg in fresh)
    new_cyr, new_lat = _script_counts(new_text)
    new_total = new_cyr + new_lat
    if new_total < 20:
        return segments, detected
    good = (new_cyr if _expected_script(target) == "cyr" else new_lat) / new_total
    if good < 0.6:
        return segments, detected
    print(f"[whisper] язык исправлен: {detected!r} → {target!r} "
          f"(правильный алфавит {good:.0%})", file=sys.stderr, flush=True)
    return fresh, target


def _cut_window(src: Path, dst: Path, start: float, end: float) -> bool:
    """Вырезает фрагмент аудио для повторной проверки."""
    cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, start):.3f}",
           "-to", f"{max(start + 0.2, end):.3f}", "-i", str(src),
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]
    result = utils.run(cmd)
    return result.returncode == 0 and dst.exists() and dst.stat().st_size > 512


def _recheck(model, wav: Path, workdir: Path, segments: List[Dict[str, Any]],
             language: Optional[str], on_progress: ProgressCb, limit: int) -> int:
    """Перепроверяет сегменты с низкой уверенностью; возвращает число правок.

    Окно вокруг сегмента декодируется заново с контекстом соседних реплик.
    Замена принимается, только если модель стала увереннее и текст не «разъехался»
    по длине — так мы чиним отдельные слова, но не портим удачные сегменты.
    """
    if limit <= 0 or not segments:
        return 0
    weak = [s for s in segments
            if s.get("quality", {}).get("avg_logprob", 0.0) < WEAK_LOGPROB]
    if not weak:
        return 0
    weak.sort(key=lambda s: s["quality"]["avg_logprob"])
    fixed = 0
    for index, seg in enumerate(weak[:limit]):
        clip = workdir / f"recheck_{os.urandom(3).hex()}.wav"
        try:
            if not _cut_window(wav, clip, seg["start"] - 0.30, seg["end"] + 0.40):
                continue
            before = [s["text"] for s in segments if s["end"] <= seg["start"]][-2:]
            context = " ".join(before)[-220:]
            base_prompt = _prompt_for_language(language) or ""
            prompt = (context + (" " + base_prompt if base_prompt else "")).strip()[-400:] or None
            try:
                raw_parts, _ = _decode(model, clip, language, False, prompt=prompt,
                                       beam=BEAM_SIZE, temperature=[0.0], condition=False)
                parts = list(raw_parts)
                new_text = " ".join(p.text.strip() for p in parts).strip()
                payloads = [_segment_payload(p, max(0.0, seg["start"] - 0.30)) for p in parts]
            except Cancelled:
                raise
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                continue
            if not new_text or not payloads:
                continue
            new_logprob = sum(p["quality"]["avg_logprob"] for p in payloads) / len(payloads)
            old_logprob = seg["quality"]["avg_logprob"]
            ratio = len(new_text) / max(1, len(seg["text"]))
            if new_logprob <= old_logprob + 0.04 or not (0.45 <= ratio <= 2.2):
                continue
            seg["text"] = new_text
            seg["words"] = [w for p in payloads for w in p["words"]]
            seg["start"] = payloads[0]["start"]
            seg["end"] = payloads[-1]["end"]
            seg["quality"]["avg_logprob"] = round(new_logprob, 3)
            seg["quality"]["rechecked"] = True
            fixed += 1
            if on_progress:
                # Прогресс-колбэки снаружи ждут float, поэтому не None.
                on_progress(0.996, f"Проверка спорных фрагментов · {index + 1}")
        finally:
            try:
                clip.unlink(missing_ok=True)
            except OSError:
                pass
    return fixed


def _run_with_timeout(fn, timeout: float):
    """Запускает распознавание части в потоке; при зависании отдаёт None."""
    box = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _split_audio(wav: Path, workdir: Path, chunk_seconds: int) -> tuple[List[tuple[Path, float, float]], Path]:
    folder = workdir / f"whisper_chunks_{os.urandom(4).hex()}"
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", str(wav),
           "-f", "segment", "-segment_time", str(chunk_seconds), "-c", "copy",
           str(folder / "chunk_%03d.wav")]
    result = utils.run(cmd)
    files = sorted(folder.glob("chunk_*.wav"))
    if result.returncode or not files:
        shutil.rmtree(folder, ignore_errors=True)
        return [], folder
    spans = []
    offset = 0.0
    for path in files:
        length = utils.media_duration(path)
        if length <= 0:
            continue
        spans.append((path, offset, length))
        offset += length
    return spans, folder


def transcribe(media: Path, workdir: Path, language: Optional[str] = None,
               on_progress: ProgressCb = None, *, audio_track: Optional[int] = None,
               window: Optional[tuple[float, float]] = None) -> Dict[str, Any]:
    global _ACTIVE_TRANSCRIBES
    started = time.time()
    used_model = active_model_key()
    if on_progress:
        on_progress(0.005, "Подготовка звука для распознавания…")
    try:
        info = utils.probe(media)
    except utils.MediaError:
        info = {"duration": utils.media_duration(media), "has_audio": True,
                "width": 0, "height": 0}
    duration = window[1] - window[0] if window is not None else info["duration"]

    if not info["has_audio"]:
        raise TranscriptionError("В видео нет аудиодорожки — нарезки с субтитрами невозможны.")

    # Чистим звук: убираем низкочастотный гул и шипение, выравниваем громкость.
    wav = utils.extract_asr_audio(media, workdir / "audio16k.wav",
                                  audio_track=audio_track, window=window)
    chunks_folder: Optional[Path] = None
    with _MODEL_LOCK:
        _ACTIVE_TRANSCRIBES += 1
    try:
        chunk_seconds = max(120, int(os.environ.get("VIRALCUT_WHISPER_CHUNK", "600")))
        trigger = max(chunk_seconds, int(os.environ.get("VIRALCUT_WHISPER_CHUNK_MIN", "1800")))
        long_audio = duration > trigger
        batched = (duration >= BATCH_MIN_SECONDS
                   and os.environ.get("VIRALCUT_WHISPER_BATCH", "1").strip() not in ("0", "false", "no", "off"))
        model = _get_model(long_audio=long_audio)
        spans: List[tuple[Path, float, float]] = [(wav, 0.0, duration)]
        if duration > trigger:
            split, chunks_folder = _split_audio(wav, workdir, chunk_seconds)
            if split:
                spans = split

        out: List[Dict[str, Any]] = []
        detected_language = language
        language_probability = None
        probe_language: Optional[str] = None
        if language is None:
            # Сначала определяем язык по фрагменту с речью и дальше декодируем уже
            # с явным языком: так интро с музыкой не уводит субтитры в английский.
            probe = _probe_language(model, wav, duration, workdir)
            if probe and probe[1] >= _PROBE_MIN_PROBABILITY:
                detected_language, language_probability = probe
                probe_language = detected_language
                print(f"[whisper] язык: {detected_language} ({language_probability:.2f}) "
                      f"— по фрагментам с речью", file=sys.stderr, flush=True)
        last_span_error: Optional[Exception] = None
        for index, (path, offset, length) in enumerate(spans):
            if not path.exists():
                traceback.print_exc()
                continue
            timeout = max(240.0, length * 40)
            try:
                result = _run_with_timeout(
                    lambda: _transcribe_span(model, path, detected_language, offset,
                                             duration, on_progress, batched),
                    timeout,
                )
                if result is None:
                    # часть зависла (например, в драйвере Metal) — перезапускаем модель и идём дальше
                    print(f"whisper chunk {index} timed out; skipping", file=sys.stderr)
                    _reset_model(long_audio)
                    model = _get_model(long_audio=long_audio)
                    if on_progress:
                        on_progress(min(0.99, (offset + length) / max(1.0, duration)),
                                    f"Часть {index + 1} зависла · пропускаю")
                    continue
                part, tinfo = result
                out.extend(part)
                if not detected_language and getattr(tinfo, "language", None):
                    detected_language = tinfo.language
                    language_probability = round(float(getattr(tinfo, "language_probability", 0.0) or 0.0), 3)
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                last_span_error = exc
                traceback.print_exc()
                continue
            if len(spans) > 1 and on_progress:
                on_progress(min(0.99, (offset + length) / max(1.0, duration)),
                            f"Распознавание речи · часть {index + 1} из {len(spans)}")

        if not out:
            if last_span_error is not None:
                raise TranscriptionError(f"Ошибка распознавания речи: {str(last_span_error)[:220]}") from last_span_error
            raise NoSpeechError("Речь не распознана: возможно, в видео нет голоса.")

        # Второй проход по спорным местам — только когда аудио не разрезано на части.
        fixed = 0
        if len(spans) == 1 and RECHECK_LIMIT > 0:
            if on_progress:
                on_progress(0.995, "Проверка спорных фрагментов…")
            try:
                fixed = _recheck(model, wav, workdir, out, detected_language, on_progress, RECHECK_LIMIT)
            except Cancelled:
                raise
            except Exception:  # noqa: BLE001
                traceback.print_exc()

        expected_language = language or probe_language
        if not expected_language and (language_probability or 0.0) >= _PROBE_MIN_PROBABILITY:
            expected_language = detected_language
        if expected_language and subtitle_script_mismatch(out, expected_language):
            if len(spans) == 1:
                out, detected_language = _fix_language_mismatch(
                    model, wav, workdir, out, detected_language, on_progress, expected_language)
            if subtitle_script_mismatch(out, expected_language):
                if language:
                    raise TranscriptionError(
                        "Текст субтитров не совпал с языком речи. Проверьте выбранную аудиодорожку.")
                # В авто-режиме интро-проба могла ошибиться (например, английская песня в начале
                # русского видео): доверяем фактическому алфавиту расшифровки, а не падаем.
                cyr, lat = _script_counts(" ".join(str(seg.get("text") or "") for seg in out))
                detected_language = "ru" if cyr >= lat else "en"

        out.sort(key=lambda s: s["start"])
        print(f"[whisper] итоговый язык: {detected_language or '?'} "
              f"| сегментов: {len(out)}", file=sys.stderr, flush=True)
        logprobs = [s.get("quality", {}).get("avg_logprob", 0.0) for s in out]
        weak = sum(1 for value in logprobs if value < WEAK_LOGPROB)
        confidence = round(sum(logprobs) / len(logprobs), 3) if logprobs else 0.0

        return {
            "language": (detected_language or language or "ru"),
            "duration": duration,
            "segments": out,
            "engine": f"whisper-{used_model}",
            "took": round(time.time() - started, 1),
            "quality": {
                "confidence": confidence,
                "weak_segments": weak,
                "rechecked": fixed,
                "language_probability": language_probability,
            },
        }
    finally:
        with _MODEL_LOCK:
            _ACTIVE_TRANSCRIBES = max(0, _ACTIVE_TRANSCRIBES - 1)
        if chunks_folder is not None:
            shutil.rmtree(chunks_folder, ignore_errors=True)
        try:
            wav.unlink(missing_ok=True)
        except OSError:
            pass
