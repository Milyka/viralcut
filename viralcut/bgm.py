"""Библиотека фоновой музыки (BGM) для авто-приглушения под речью (sidechain)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import utils
from .config import DATA_DIR

BGM_DIR = DATA_DIR / "bgm"
META_PATH = BGM_DIR / "tracks.json"
ALLOWED_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MAX_BYTES = 100 * 1024 * 1024  # 100 МБ

_LOCK = threading.Lock()


def _load_meta() -> List[Dict[str, Any]]:
    if not META_PATH.is_file():
        return []
    try:
        data = json.loads(META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_meta(items: List[Dict[str, Any]]) -> None:
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(META_PATH)


def list_tracks() -> List[Dict[str, Any]]:
    """Возвращает список загруженных треков фоновой музыки."""
    with _LOCK:
        items = _load_meta()
    out: List[Dict[str, Any]] = []
    for item in items:
        path = BGM_DIR / str(item.get("file") or "")
        if not path.is_file():
            continue
        out.append({
            "id": item["id"],
            "name": item.get("name") or path.stem,
            "duration": round(float(item.get("duration") or 0), 1),
            "size": path.stat().st_size,
            "url": f"/api/bgm/{item['id']}/audio",
            "created_at": item.get("created_at") or 0,
        })
    return out


def resolve_path(track_id: Optional[str]) -> Optional[Path]:
    """Возвращает реальный путь на диске к файлу трека (или None)."""
    tid = str(track_id or "").strip()
    if not tid:
        return None
    with _LOCK:
        items = _load_meta()
    for item in items:
        if item.get("id") == tid:
            path = BGM_DIR / str(item.get("file") or "")
            return path if path.is_file() else None
    return None


def add_track(filename: str, data_path: Path, name: Optional[str] = None) -> Dict[str, Any]:
    """Проверяет и сохраняет аудиофайл в библиотеку BGM."""
    suffix = Path(filename or "track.mp3").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Формат {suffix or '?'} не поддерживается для фоновой музыки")
    try:
        size = data_path.stat().st_size
    except OSError as exc:
        raise ValueError("Не удалось прочитать аудиофайл") from exc
    if size <= 0 or size > MAX_BYTES:
        raise ValueError("Размер аудиофайла должен быть от 1 байта до 100 МБ")

    info = utils.probe(data_path)
    if not info.get("has_audio") or float(info.get("duration") or 0) < 0.5:
        raise ValueError("Файл не похож на аудиодорожку")

    raw_name = name or Path(filename or "bgm").stem
    clean_name = re.sub(r"[^\w\-. ()А-Яа-яЁё]+", " ", str(raw_name)).strip()[:72] or "Фоновая музыка"
    tid = "bgm_" + hashlib.sha1(f"{clean_name}:{time.time()}".encode("utf-8")).hexdigest()[:10]
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    target = BGM_DIR / f"{tid}{suffix}"
    shutil.move(str(data_path), str(target))
    entry = {
        "id": tid,
        "name": clean_name,
        "file": target.name,
        "duration": round(float(info["duration"]), 2),
        "created_at": round(time.time(), 2),
    }
    with _LOCK:
        items = _load_meta()
        items.insert(0, entry)
        _save_meta(items)
    return {
        "id": tid,
        "name": clean_name,
        "duration": entry["duration"],
        "size": target.stat().st_size,
        "url": f"/api/bgm/{tid}/audio",
    }


def delete_track(track_id: str) -> bool:
    tid = str(track_id or "").strip()
    if not tid:
        return False
    removed = False
    with _LOCK:
        items = _load_meta()
        keep = []
        for item in items:
            if item.get("id") == tid:
                removed = True
                path = BGM_DIR / str(item.get("file") or "")
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                keep.append(item)
        if removed:
            _save_meta(keep)
    return removed


def normalize_config(raw: Any) -> Optional[Dict[str, Any]]:
    """Приводит настройки BGM клипа/профиля к безопасной схеме (или None, если выключено)."""
    if not isinstance(raw, dict):
        return None
    if not raw.get("enabled"):
        return None
    track_id = str(raw.get("track_id") or "").strip()
    if not track_id:
        return None
    try:
        vol_db = float(raw.get("volume_db", -14.0))
    except (TypeError, ValueError):
        vol_db = -14.0
    vol_db = round(max(-30.0, min(-6.0, vol_db)), 1)
    try:
        duck_db = float(raw.get("duck_db", -22.0))
    except (TypeError, ValueError):
        duck_db = -22.0
    duck_db = round(max(-28.0, min(-12.0, duck_db)), 1)
    return {
        "enabled": True,
        "track_id": track_id,
        "volume_db": vol_db,
        "ducking": bool(raw.get("ducking", True)),
        "duck_db": duck_db,
    }
