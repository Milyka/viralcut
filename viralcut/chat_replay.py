"""Потоковый парсер повтора чата (YouTube .live_chat.json / Twitch VOD JSON) и кривая хайпа."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HYPE_RE = re.compile(
    r"\b(lul|lulw|kekw|omegalul|pog|poggers|pogchamp|wtf|omg|clip it|w|gg|goat|insane|crazy|"
    r"хах+|ахах+|лол|ору|жесть|имба|шок|красава|афигеть|пипец|легенда)\b|[!?]{2,}",
    re.IGNORECASE,
)


def _extract_yt_line(obj: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    """Извлекает (время_в_сек, текст_сообщения) из одной строки YouTube live_chat.json."""
    action = obj.get("replayChatItemAction")
    if not isinstance(action, dict):
        return None
    raw_ms = action.get("videoOffsetTimeMsec")
    if raw_ms is None:
        return None
    try:
        sec = float(raw_ms) / 1000.0
    except (TypeError, ValueError):
        return None
    if sec < 0:
        return None

    text = ""
    for act in action.get("actions") or []:
        if not isinstance(act, dict):
            continue
        add = act.get("addChatItemAction")
        if not isinstance(add, dict):
            continue
        item = add.get("item") or {}
        if not isinstance(item, dict):
            continue
        renderer = (
            item.get("liveChatTextMessageRenderer")
            or item.get("liveChatPaidMessageRenderer")
            or item.get("liveChatMembershipItemRenderer")
        )
        if not isinstance(renderer, dict):
            continue
        msg = renderer.get("message") or {}
        runs = msg.get("runs") if isinstance(msg, dict) else None
        if isinstance(runs, list):
            chunks: List[str] = []
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if "text" in run:
                    chunks.append(str(run["text"]))
                elif "emoji" in run and isinstance(run["emoji"], dict):
                    shortcuts = run["emoji"].get("shortcuts") or []
                    if shortcuts:
                        chunks.append(str(shortcuts[0]))
                    else:
                        chunks.append(":emote:")
            text = " ".join("".join(chunks).split())[:120]
            break
    return sec, text


def _extract_twitch_entry(obj: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    """Извлекает (время_в_сек, текст) из записи Twitch VOD chat JSON."""
    offset = obj.get("content_offset_seconds")
    if offset is None:
        return None
    try:
        sec = float(offset)
    except (TypeError, ValueError):
        return None
    if sec < 0:
        return None
    msg = obj.get("message")
    body = ""
    if isinstance(msg, dict):
        body = str(msg.get("body") or "")
    elif isinstance(msg, str):
        body = msg
    return sec, " ".join(body.split())[:120]


def _iter_chat_messages(path: Path):
    """Итерируется по сообщениям потоково, не загружая огромные .live_chat.json в память."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first_non_ws = ""
        pos = fh.tell()
        while True:
            ch = fh.read(1)
            if not ch:
                return
            if not ch.isspace():
                first_non_ws = ch
                break
        fh.seek(pos)

        # Вариант 1: NDJSON (стандартный формат yt-dlp .live_chat.json — одна JSON-запись на строку)
        is_ndjson = False
        if first_non_ws == "{":
            first_line = fh.readline()
            fh.seek(pos)
            try:
                probe_obj = json.loads(first_line)
                if isinstance(probe_obj, dict) and (
                    "replayChatItemAction" in probe_obj or "content_offset_seconds" in probe_obj
                ):
                    is_ndjson = True
            except Exception:
                is_ndjson = False

        if is_ndjson:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                parsed = _extract_yt_line(obj) or _extract_twitch_entry(obj)
                if parsed is not None:
                    yield parsed
            return

        # Вариант 2: Twitch VOD JSON {"comments": [...]} или JSON-массив (ограничим чтение 64 МБ)
        if path.stat().st_size > 64 * 1024 * 1024:
            return
        try:
            data = json.loads(fh.read())
        except Exception:
            return
        items = data.get("comments") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return
        for obj in items:
            if not isinstance(obj, dict):
                continue
            parsed = _extract_twitch_entry(obj) or _extract_yt_line(obj)
            if parsed is not None:
                yield parsed


def _median(vals: List[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def parse_chat_replay(path: Path, duration: float, bin_sec: float = 5.0) -> Optional[Dict[str, Any]]:
    """Строит 5-секундную кривую активности чата и пики хайпа без всплеска RAM."""
    if not path.is_file():
        return None
    bin_sec = max(1.0, float(bin_sec or 5.0))
    est_dur = max(bin_sec, float(duration or 0.0))
    n_bins = max(1, int(math.ceil(est_dur / bin_sec)))
    counts: List[int] = [0] * n_bins
    weighted: List[float] = [0.0] * n_bins
    samples: List[str] = [""] * n_bins
    sample_score: List[float] = [-1.0] * n_bins
    total_messages = 0

    for sec, text in _iter_chat_messages(path):
        idx = int(sec // bin_sec)
        if idx < 0:
            continue
        if idx >= len(counts):
            if duration > 0 and sec > duration + 60.0:
                continue
            # расширяем массив для записей без заранее известной длины
            grow = min(idx - len(counts) + 1, 20000)
            if grow <= 0:
                continue
            counts.extend([0] * grow)
            weighted.extend([0.0] * grow)
            samples.extend([""] * grow)
            sample_score.extend([-1.0] * grow)
            if idx >= len(counts):
                continue
        total_messages += 1
        counts[idx] += 1
        w = 1.0
        if text and _HYPE_RE.search(text):
            w = 1.65
        elif text and len(text) >= 4 and text.isupper():
            w = 1.35
        weighted[idx] += w
        if text and w > sample_score[idx]:
            sample_score[idx] = w
            samples[idx] = text

    if total_messages < 5:
        return None

    # Скользящая базовая линия (медиана + MAD в окне ±60 сек)
    half_win = max(3, int(round(60.0 / bin_sec)))
    n = len(weighted)
    zscores: List[float] = [0.0] * n
    curve: List[float] = [0.0] * n
    for i in range(n):
        lo = max(0, i - half_win)
        hi = min(n, i + half_win + 1)
        win = weighted[lo:hi]
        med = _median(win)
        mad = _median([abs(x - med) for x in win])
        scale = 1.4826 * mad
        if scale < 1e-3:
            mean = sum(win) / max(1, len(win))
            var = sum((x - mean) ** 2 for x in win) / max(1, len(win))
            scale = max(1.0, math.sqrt(var))
        z = (weighted[i] - med) / max(1.0, scale)
        zscores[i] = round(max(0.0, z), 3)
        # Нормализуем z-score в [0..1]: z >= 5.0 → 1.0, ниже 0.5 → 0.0
        curve[i] = round(max(0.0, min(1.0, (z - 0.5) / 4.5)), 4)

    # Топ-пики (не пересекающиеся ближе 15 сек)
    ranked = sorted(range(n), key=lambda i: (zscores[i], counts[i]), reverse=True)
    peaks: List[Dict[str, Any]] = []
    min_gap_bins = max(1, int(round(15.0 / bin_sec)))
    for idx in ranked:
        if zscores[idx] < 1.2 or counts[idx] < 2:
            break
        if any(abs(idx - int(p["_bin"])) < min_gap_bins for p in peaks):
            continue
        peaks.append({
            "_bin": idx,
            "start": round(idx * bin_sec, 1),
            "end": round((idx + 1) * bin_sec, 1),
            "rate": round(counts[idx] / bin_sec, 2),
            "zscore": round(zscores[idx], 2),
            "sample_msg": samples[idx],
        })
        if len(peaks) >= 25:
            break
    for p in peaks:
        p.pop("_bin", None)

    return {
        "bin_sec": bin_sec,
        "duration": round(n * bin_sec, 1),
        "total_messages": total_messages,
        "counts": counts,
        "curve": curve,
        "peaks": peaks,
    }


def window_score(chat_curve: Optional[Dict[str, Any]], start: float, end: float,
                 lag_sec: float = 4.0) -> float:
    """Оценка хайпа чата в окне [start+lag, end+lag] (чат реагирует на 3–5 с позже)."""
    if not chat_curve or not chat_curve.get("curve"):
        return 0.0
    curve = chat_curve["curve"]
    bin_sec = max(1.0, float(chat_curve.get("bin_sec") or 5.0))
    lo = max(0, int((start + lag_sec) // bin_sec))
    hi = min(len(curve), int(math.ceil((end + lag_sec) / bin_sec)))
    if hi <= lo:
        hi = min(len(curve), lo + 1)
    vals = [float(v) for v in curve[lo:hi]]
    if not vals:
        return 0.0
    peak = max(vals)
    mean = sum(vals) / len(vals)
    return round(max(0.0, min(1.0, 0.72 * peak + 0.28 * mean)), 4)


def load_or_build(workdir: Path, duration: float,
                  chat_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Загружает готовый chat_curve.json или строит его из файла чата в workdir."""
    summary_path = workdir / "chat_curve.json"
    if summary_path.is_file():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("curve"):
                return data
        except Exception:
            pass

    target = chat_path
    if target is None or not target.is_file():
        candidates = sorted(
            list(workdir.glob("*.live_chat.json"))
            + list(workdir.glob("*chat*.json"))
        )
        candidates = [p for p in candidates if p.name != "chat_curve.json"]
        target = candidates[0] if candidates else None
    if target is None or not target.is_file():
        return None

    result = parse_chat_replay(target, duration)
    if result:
        try:
            summary_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return result
