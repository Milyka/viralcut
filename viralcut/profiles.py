"""Brand Kits (профили каналов) и библиотека брендовых ассетов (водяные знаки, интро, аутро)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import bgm, db, subtitles, utils
from .config import DATA_DIR

BRAND_ASSETS_DIR = DATA_DIR / "brand_assets"
ASSETS_META_PATH = BRAND_ASSETS_DIR / "assets.json"

WATERMARK_SUFFIXES = {".png", ".webp"}
BUMPER_SUFFIXES = {".mp4", ".mov", ".webm"}
WATERMARK_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
MAX_WATERMARK_BYTES = 15 * 1024 * 1024
MAX_BUMPER_BYTES = 120 * 1024 * 1024
MAX_BUMPER_DURATION = 15.5

_LOCK = threading.Lock()


def _load_assets_meta() -> List[Dict[str, Any]]:
    if not ASSETS_META_PATH.is_file():
        return []
    try:
        data = json.loads(ASSETS_META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_assets_meta(items: List[Dict[str, Any]]) -> None:
    BRAND_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ASSETS_META_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ASSETS_META_PATH)


def list_assets(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    with _LOCK:
        items = _load_assets_meta()
    out: List[Dict[str, Any]] = []
    for item in items:
        if kind and item.get("kind") != kind:
            continue
        path = BRAND_ASSETS_DIR / str(item.get("file") or "")
        if not path.is_file():
            continue
        out.append({
            "id": item["id"],
            "kind": item.get("kind") or "watermark",
            "name": item.get("name") or path.stem,
            "width": int(item.get("width") or 0),
            "height": int(item.get("height") or 0),
            "duration": round(float(item.get("duration") or 0), 2),
            "size": path.stat().st_size,
            "url": f"/api/brand-assets/{item['id']}/file",
            "created_at": item.get("created_at") or 0,
        })
    return out


def resolve_asset(asset_id: Optional[str], expected_kind: Optional[str] = None) -> Optional[Path]:
    aid = str(asset_id or "").strip()
    if not aid:
        return None
    with _LOCK:
        items = _load_assets_meta()
    for item in items:
        if item.get("id") != aid:
            continue
        if expected_kind and item.get("kind") != expected_kind:
            # intro и outro взаимозаменяемы как видео-бамперы
            if not (expected_kind in ("intro", "outro") and item.get("kind") in ("intro", "outro")):
                return None
        path = BRAND_ASSETS_DIR / str(item.get("file") or "")
        return path if path.is_file() else None
    return None


def add_asset(kind: str, filename: str, data_path: Path, name: Optional[str] = None) -> Dict[str, Any]:
    """Проверяет и сохраняет логотип (PNG/WebP) или интро/аутро (MP4/MOV/WebM <= 15s)."""
    k = str(kind or "").strip().lower()
    if k not in ("watermark", "intro", "outro"):
        raise ValueError("Тип ассета должен быть watermark, intro или outro")
    suffix = Path(filename or "").suffix.lower()
    try:
        size = data_path.stat().st_size
    except OSError as exc:
        raise ValueError("Не удалось прочитать загруженный файл") from exc

    width = height = 0
    duration = 0.0
    if k == "watermark":
        if suffix not in WATERMARK_SUFFIXES:
            raise ValueError("Для водяного знака поддерживаются только PNG и WebP")
        if size <= 0 or size > MAX_WATERMARK_BYTES:
            raise ValueError("Размер логотипа должен быть до 15 МБ")
        try:
            from PIL import Image

            with Image.open(data_path) as img:
                width, height = img.size
        except Exception as exc:
            raise ValueError("Файл не является корректным изображением PNG/WebP") from exc
        if width < 8 or height < 8:
            raise ValueError("Слишком маленькое изображение для водяного знака")
    else:
        if suffix not in BUMPER_SUFFIXES:
            raise ValueError("Для интро/аутро поддерживаются MP4, MOV и WebM")
        if size <= 0 or size > MAX_BUMPER_BYTES:
            raise ValueError("Размер видео-бампера должен быть до 120 МБ")
        info = utils.probe(data_path)
        if not info.get("has_video") or not info.get("width") or not info.get("height"):
            raise ValueError("Файл интро/аутро не содержит видеопотока")
        duration = float(info.get("duration") or 0.0)
        if duration < 0.2 or duration > MAX_BUMPER_DURATION:
            raise ValueError("Длительность интро/аутро должна быть от 0.2 до 15 секунд")
        width, height = int(info["width"]), int(info["height"])

    raw_name = name or Path(filename or k).stem
    clean_name = re.sub(r"[^\w\-. ()А-Яа-яЁё]+", " ", str(raw_name)).strip()[:72] or k
    aid = f"{k[:2]}_{hashlib.sha1(f'{k}:{clean_name}:{time.time()}'.encode('utf-8')).hexdigest()[:10]}"
    BRAND_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    target = BRAND_ASSETS_DIR / f"{aid}{suffix}"
    shutil.move(str(data_path), str(target))
    entry = {
        "id": aid,
        "kind": k,
        "name": clean_name,
        "file": target.name,
        "width": width,
        "height": height,
        "duration": round(duration, 2),
        "created_at": round(time.time(), 2),
    }
    with _LOCK:
        items = _load_assets_meta()
        items.insert(0, entry)
        _save_assets_meta(items)
    return {
        "id": aid,
        "kind": k,
        "name": clean_name,
        "width": width,
        "height": height,
        "duration": entry["duration"],
        "size": target.stat().st_size,
        "url": f"/api/brand-assets/{aid}/file",
    }


def delete_asset(asset_id: str) -> bool:
    aid = str(asset_id or "").strip()
    if not aid:
        return False
    removed = False
    with _LOCK:
        items = _load_assets_meta()
        keep = []
        for item in items:
            if item.get("id") == aid:
                removed = True
                path = BRAND_ASSETS_DIR / str(item.get("file") or "")
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                keep.append(item)
        if removed:
            _save_assets_meta(keep)
    return removed


def normalize_watermark(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    if not raw.get("enabled"):
        return None
    asset_id = str(raw.get("asset_id") or "").strip()
    if not asset_id:
        return None
    pos = str(raw.get("position") or "top-right").strip().lower()
    if pos not in WATERMARK_POSITIONS:
        pos = "top-right"
    try:
        scale = float(raw.get("scale", 0.16))
    except (TypeError, ValueError):
        scale = 0.16
    scale = round(max(0.08, min(0.35, scale)), 3)
    try:
        opacity = float(raw.get("opacity", 0.85))
    except (TypeError, ValueError):
        opacity = 0.85
    opacity = round(max(0.1, min(1.0, opacity)), 2)
    try:
        margin = int(raw.get("margin", 36))
    except (TypeError, ValueError):
        margin = 36
    margin = max(0, min(160, margin))
    return {
        "enabled": True,
        "asset_id": asset_id,
        "position": pos,
        "scale": scale,
        "opacity": opacity,
        "margin": margin,
    }


def normalize_profile_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Приводит конфиг Brand Kit к валидному словарю настроек проекта/клипа."""
    from . import game_layer as _gl

    src = dict(raw or {})
    aspect = str(src.get("aspect") or "9:16")
    if aspect not in ("9:16", "1:1", "16:9", "4:5"):
        aspect = "9:16"
    mode = str(src.get("mode") or "auto")
    if mode not in ("auto", "blur", "crop"):
        mode = "auto"
    cut_mode = str(src.get("cut_mode") or "ai")
    if cut_mode not in ("ai", "even", "stream"):
        cut_mode = "ai"
    try:
        count = max(0, min(200, int(src.get("count", 10))))
    except (TypeError, ValueError):
        count = 10
    try:
        min_dur = max(8, min(120, int(src.get("min_dur", 15))))
        max_dur = max(min_dur + 5, min(180, int(src.get("max_dur", 60))))
        target_dur = max(min_dur, min(max_dur, int(src.get("target_dur", 32))))
    except (TypeError, ValueError):
        min_dur, max_dur, target_dur = 15, 60, 32

    sub_font = str(src.get("sub_font") or "montserrat")
    if not subtitles.font_exists(sub_font):
        sub_font = "montserrat"
    try:
        sub_size = max(70, min(180, int(src.get("sub_size", 118))))
    except (TypeError, ValueError):
        sub_size = 118
    sub_pos = str(src.get("sub_position") or "bottom").strip().lower()
    if sub_pos == "center":
        sub_pos = "middle"
    if sub_pos not in subtitles.POSITIONS:
        sub_pos = "bottom"
    try:
        sub_offset = max(-120, min(180, int(src.get("sub_offset", 0))))
    except (TypeError, ValueError):
        sub_offset = 0
    sub_free = None
    raw_free = src.get("sub_free")
    if isinstance(raw_free, (list, tuple)) and len(raw_free) >= 2:
        try:
            sub_free = [round(max(0.0, min(1.0, float(raw_free[0]))), 4),
                        round(max(0.0, min(1.0, float(raw_free[1]))), 4)]
        except (TypeError, ValueError):
            sub_free = None
    sub_speed = str(src.get("sub_speed") or "calm")
    if sub_speed not in subtitles.SPEEDS:
        sub_speed = "calm"
    sub_anim = str(src.get("sub_anim") or "pop")
    if sub_anim not in subtitles.ANIMATIONS:
        sub_anim = "pop"
    accent = str(src.get("accent") or "yellow").strip()
    if not subtitles.is_valid_color(accent):
        accent = "yellow"
    try:
        ow = max(0, min(14, int(src.get("sub_outline_width", 7))))
    except (TypeError, ValueError):
        ow = 7
    ocol = str(src.get("sub_outline_color") or "#000000").strip()
    if not subtitles.is_valid_color(ocol):
        ocol = "#000000"

    ai_preset = str(src.get("ai_preset") or "best").strip().lower()
    if ai_preset not in ("best", "funny", "emotions", "drama", "insights", "action", "quotes", "story"):
        ai_preset = "best"

    pool_norm = _gl.normalize_pool_config(src.get("game_pool")) if hasattr(_gl, "normalize_pool_config") else None

    return {
        "aspect": aspect,
        "mode": mode,
        "cut_mode": cut_mode,
        "count": count,
        "min_dur": min_dur,
        "max_dur": max_dur,
        "target_dur": target_dur,
        "language": str(src.get("language") or "auto").strip().lower()[:16],
        "cut_pauses": bool(src.get("cut_pauses", False)),
        "subtitles": bool(src.get("subtitles", True)),
        "sub_font": sub_font,
        "sub_size": sub_size,
        "sub_position": sub_pos,
        "sub_offset": sub_offset,
        "sub_free": sub_free,
        "sub_speed": sub_speed,
        "sub_anim": sub_anim,
        "accent": accent,
        "uppercase": bool(src.get("uppercase", True)),
        "show_hook": bool(src.get("show_hook", True)),
        "sub_outline": bool(src.get("sub_outline", True)),
        "sub_outline_width": ow,
        "sub_outline_color": ocol,
        "ai_mode": bool(src.get("ai_mode", False)),
        "ai_preset": ai_preset,
        "ai_prompt": str(src.get("ai_prompt") or "")[:600],
        "watermark": normalize_watermark(src.get("watermark")),
        "intro_asset_id": str(src.get("intro_asset_id") or "").strip(),
        "outro_asset_id": str(src.get("outro_asset_id") or "").strip(),
        "game_pool": pool_norm,
        "bgm": bgm.normalize_config(src.get("bgm")),
        "punch_in_zoom": bool(src.get("punch_in_zoom", False)),
        "auto_dual_split": bool(src.get("auto_dual_split", True)),
        "bot_deliver": bool(src.get("bot_deliver", False)),
    }


def list_profiles() -> List[Dict[str, Any]]:
    return db.list_profiles()


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    return db.get_profile(profile_id)


def create_profile(name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    clean_name = " ".join(str(name or "").split())[:80]
    if not clean_name:
        raise ValueError("Укажите название профиля (Brand Kit)")
    return db.create_profile(clean_name, normalize_profile_config(config))


def update_profile(profile_id: str, *, name: Optional[str] = None,
                   config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    existing = db.get_profile(profile_id)
    if not existing:
        return None
    merged_cfg = None
    if config is not None:
        base = dict(existing.get("config") or {})
        base.update(config)
        merged_cfg = normalize_profile_config(base)
    return db.update_profile(profile_id, name=name, config=merged_cfg)


def delete_profile(profile_id: str) -> bool:
    return db.delete_profile(profile_id)
