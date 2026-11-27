"""Слой игры (Split-Screen): фоновые ролики для нижней части вертикальных клипов.

Пользователь может загрузить свои ролики (Minecraft паркур, Subway Surfers, GTA,
satisfying-видео) или использовать встроенные процедурные петли. Ролики хранятся
в `DATA_DIR/game_clips/` и используются как в живом предпросмотре редактора,
так и при финальном FFmpeg-рендере (`vstack`).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import utils
from .config import DATA_DIR, ffmpeg

GAME_DIR = DATA_DIR / "game_clips"
META_PATH = GAME_DIR / "clips.json"
MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 ГБ на фоновый ролик
ALLOWED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
SPLIT_PRESETS = ("50/50", "55/45", "60/40", "65/35", "70/30")
_LOCK = threading.Lock()

BUILTIN_LOOPS = [
    {
        "id": "builtin_neon_waves",
        "name": "Неоновые волны (встроенный)",
        "file": "builtin_neon_waves.mp4",
        "builtin": True,
        "lavfi": "gradients=s=720x540:r=30:d=8:speed=0.9:c0=0x7c3aed:c1=0xec4899:c2=0x06b6d4:c3=0x1e1b4b,format=yuv420p",
    },
    {
        "id": "builtin_plasma_pulse",
        "name": "Космический импульс (встроенный)",
        "file": "builtin_plasma_pulse.mp4",
        "builtin": True,
        "lavfi": "life=s=180x135:r=30:mold=10:death_color=#0f0c29:life_color=#c084fc:ratio=0.18,scale=720:540:flags=neighbor,gblur=sigma=1.2,format=yuv420p",
    },
]


def _load_meta() -> List[Dict[str, Any]]:
    try:
        data = json.loads(META_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict) and item.get("id")]
    except (OSError, ValueError):
        pass
    return []


def _save_meta(items: List[Dict[str, Any]]) -> None:
    GAME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(META_PATH)


def _ensure_builtin(spec: Dict[str, Any]) -> Optional[Path]:
    with _LOCK:
        GAME_DIR.mkdir(parents=True, exist_ok=True)
        path = GAME_DIR / spec["file"]
        if path.is_file() and path.stat().st_size > 8000:
            return path
        tmp = GAME_DIR / f".{spec['id']}.{os.urandom(3).hex()}.tmp.mp4"
        cmd = [
            ffmpeg(), "-y", "-v", "error",
            "-f", "lavfi", "-i", spec["lavfi"],
            "-t", "8", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp),
        ]
        proc = utils.run(cmd, timeout=45)
        if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 4000:
            # Запасной генератор, если в сборке ffmpeg нет gradients/life
            fallback_cmd = [
                ffmpeg(), "-y", "-v", "error",
                "-f", "lavfi", "-i", "mandelbrot=s=720x540:r=30",
                "-t", "8", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp),
            ]
            proc = utils.run(fallback_cmd, timeout=45)
        if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size >= 4000:
            os.replace(tmp, path)
            return path
        tmp.unlink(missing_ok=True)
        return None


def list_clips() -> List[Dict[str, Any]]:
    """Возвращает все доступные ролики слоя игры (загруженные + встроенные)."""
    out: List[Dict[str, Any]] = []
    with _LOCK:
        user_items = _load_meta()
    for item in user_items:
        path = GAME_DIR / str(item.get("file") or "")
        if not path.is_file():
            continue
        out.append({
            "id": item["id"],
            "name": item.get("name") or path.stem,
            "duration": round(float(item.get("duration") or 0), 1),
            "size": path.stat().st_size,
            "builtin": False,
            "url": f"/api/game-clips/{item['id']}/video",
        })
    for spec in BUILTIN_LOOPS:
        out.append({
            "id": spec["id"],
            "name": spec["name"],
            "duration": 8.0,
            "size": (GAME_DIR / spec["file"]).stat().st_size if (GAME_DIR / spec["file"]).is_file() else 0,
            "builtin": True,
            "url": f"/api/game-clips/{spec['id']}/video",
        })
    return out


def resolve_path(clip_id: Optional[str]) -> Optional[Path]:
    """Возвращает реальный путь на диске к файлу слоя игры (или None)."""
    cid = str(clip_id or "").strip()
    if not cid:
        return None
    for spec in BUILTIN_LOOPS:
        if spec["id"] == cid:
            return _ensure_builtin(spec)
    with _LOCK:
        for item in _load_meta():
            if item.get("id") == cid:
                path = GAME_DIR / str(item.get("file") or "")
                return path if path.is_file() else None
    return None


def add_clip(filename: str, data_path: Path) -> Dict[str, Any]:
    """Регистрирует загруженный пользователем ролик слоя игры."""
    suffix = Path(filename or "game.mp4").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Формат {suffix or '?'} не поддерживается для слоя игры")
    info = utils.probe(data_path)
    if not info.get("has_video") or not info.get("duration"):
        raise ValueError("Файл не похож на видео")
    clean_name = re.sub(r"[^\w\-. ()А-Яа-яЁё]+", " ", Path(filename or "clip").stem).strip()[:64] or "Игровой ролик"
    cid = "game_" + hashlib.sha1(f"{clean_name}:{time.time()}".encode("utf-8")).hexdigest()[:10]
    GAME_DIR.mkdir(parents=True, exist_ok=True)
    target = GAME_DIR / f"{cid}{suffix}"
    data_path.replace(target)
    entry = {
        "id": cid,
        "name": clean_name,
        "file": target.name,
        "duration": round(float(info["duration"]), 2),
        "width": int(info["width"]),
        "height": int(info["height"]),
        "created_at": round(time.time(), 2),
    }
    with _LOCK:
        items = _load_meta()
        items.insert(0, entry)
        _save_meta(items)
    return {
        "id": cid,
        "name": clean_name,
        "duration": entry["duration"],
        "size": target.stat().st_size,
        "builtin": False,
        "url": f"/api/game-clips/{cid}/video",
    }


def delete_clip(clip_id: str) -> bool:
    cid = str(clip_id or "").strip()
    if any(spec["id"] == cid for spec in BUILTIN_LOOPS):
        raise ValueError("Встроенный ролик нельзя удалить")
    with _LOCK:
        items = _load_meta()
        found = next((i for i in items if i.get("id") == cid), None)
        if not found:
            return False
        remaining = [i for i in items if i.get("id") != cid]
        _save_meta(remaining)
    path = GAME_DIR / str(found.get("file") or "")
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def normalize_config(raw: Any) -> Optional[Dict[str, Any]]:
    """Приводит настройки слоя игры к безопасному виду (или None, если выключен)."""
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    clip_id = str(raw.get("clip_id") or "").strip()
    if not clip_id:
        clip_id = BUILTIN_LOOPS[0]["id"]
    split = str(raw.get("split") or "60/40").strip()
    if split not in SPLIT_PRESETS:
        split = "60/40"
    raw_start = raw.get("start") if raw.get("start") is not None else raw.get("start_offset")
    try:
        start = max(0.0, float(raw_start or 0.0))
    except (TypeError, ValueError):
        start = 0.0
    try:
        top_zoom = max(1.0, min(2.5, float(raw.get("top_zoom") or 1.0)))
    except (TypeError, ValueError):
        top_zoom = 1.0
    try:
        game_zoom = max(1.0, min(2.5, float(raw.get("game_zoom") or 1.0)))
    except (TypeError, ValueError):
        game_zoom = 1.0

    def _pan(val: Any) -> List[float]:
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return [round(max(-1.0, min(1.0, float(val[0]))), 3),
                        round(max(-1.0, min(1.0, float(val[1]))), 3)]
            except (TypeError, ValueError):
                pass
        return [0.0, 0.0]

    return {
        "enabled": True,
        "clip_id": clip_id,
        "split": split,
        "start": round(start, 1),
        "top_zoom": round(top_zoom, 2),
        "game_zoom": round(game_zoom, 2),
        "top_pan": _pan(raw.get("top_pan")),
        "game_pan": _pan(raw.get("game_pan")),
        "audio": bool(raw.get("audio") or raw.get("game_audio")),
    }


def split_heights(total_h: int, split: str) -> tuple[int, int]:
    """Делит общую высоту кадра на верхнюю (видео) и нижнюю (игра) чётные части."""
    try:
        top_pct = int(str(split).split("/")[0])
    except Exception:
        top_pct = 60
    top_pct = max(45, min(75, top_pct))
    top_h = int(round(total_h * top_pct / 100.0))
    top_h -= top_h % 2
    bot_h = total_h - top_h
    bot_h -= bot_h % 2
    top_h = total_h - bot_h
    return top_h, bot_h
