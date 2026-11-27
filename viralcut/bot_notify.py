"""Локальные боты одобрения клипов (Telegram long-polling + Discord Gateway v10).

Только исходящие соединения: без проброса портов, без публичного сервера.
Контроль доступа — строго fail-closed: пустой белый список запрещает всем.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import db, jobs, pipeline, profiles, render, settings as app_settings
from .config import PROJECTS_DIR

TG_MAX_VIDEO_BYTES = 45 * 1024 * 1024  # 45 МБ (< 50 МБ лимит Telegram Bot API)
DC_MAX_VIDEO_BYTES = 24 * 1024 * 1024  # 24 МБ (< 25 МБ лимит Discord)
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_STATE_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()
_TG_THREAD: Optional[threading.Thread] = None
_DC_THREAD: Optional[threading.Thread] = None
_TG_OFFSET: int = 0
_SEEN_UPDATES: Set[int] = set()
_STATUS: Dict[str, Any] = {
    "telegram": {"running": False, "last_error": "", "bot_username": ""},
    "discord": {"running": False, "last_error": "", "bot_username": ""},
}


# --- Строгий fail-closed контроль доступа -----------------------------------

def parse_allowed_users(allowed_raw: str) -> Tuple[Set[str], Set[str]]:
    """Разбирает белый список (числовые ID и/или @username) в два множества."""
    ids: Set[str] = set()
    usernames: Set[str] = set()
    for token in re.split(r"[\s,;]+", str(allowed_raw or "").strip()):
        tok = token.strip()
        if not tok:
            continue
        if tok.startswith("@"):
            uname = tok.lstrip("@").strip().lower()
            if uname:
                usernames.add(uname)
        elif tok.lstrip("-").isdigit():
            ids.add(tok)
        else:
            usernames.add(tok.lower())
    return ids, usernames


def is_authorized_user(user_id: Any, username: Any, allowed_raw: str) -> bool:
    """Fail-closed проверка доступа: пустой список всегда возвращает False."""
    allowed_ids, allowed_usernames = parse_allowed_users(allowed_raw)
    if not allowed_ids and not allowed_usernames:
        return False
    uid = str(user_id).strip() if user_id is not None else ""
    if uid and uid in allowed_ids:
        return True
    uname = str(username or "").strip().lower().lstrip("@")
    if uname and uname in allowed_usernames:
        return True
    return False


# --- HTTP / Multipart helpers (stdlib only) ----------------------------------

def _http_json(url: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None,
               headers: Optional[Dict[str, str]] = None, timeout: int = 25) -> Dict[str, Any]:
    hdrs = {"User-Agent": "KrlzCut-Bot/2.1"}
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}


def _multipart_post(url: str, fields: Dict[str, str], files: Dict[str, Tuple[str, Path, str]],
                    headers: Optional[Dict[str, str]] = None, timeout: int = 90) -> Dict[str, Any]:
    boundary = f"----KrlzCutBoundary{uuid.uuid4().hex}"
    chunks: List[bytes] = []
    for key, val in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{val}\r\n".encode("utf-8")
        )
    for key, (fname, fpath, mime) in files.items():
        ctype = mime or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"; filename="{fname}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode("utf-8")
        )
        chunks.append(fpath.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)

    hdrs = {
        "User-Agent": "KrlzCut-Bot/2.1",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}


# --- Общие действия одобрения (Telegram + Discord) ---------------------------

def _ensure_preview_file(clip: Dict[str, Any], max_bytes: int) -> Optional[Path]:
    pid = clip["project_id"]
    cid = clip["id"]
    preview = PROJECTS_DIR / pid / "previews" / f"{cid}.mp4"
    if preview.is_file() and 0 < preview.stat().st_size <= max_bytes:
        return preview
    full = Path(clip["path"]) if clip.get("path") else None
    if full and full.is_file() and 0 < full.stat().st_size <= max_bytes:
        return full
    if full and full.is_file():
        try:
            preview.parent.mkdir(parents=True, exist_ok=True)
            made = render.make_preview(full, preview)
            if made and made.is_file() and made.stat().st_size <= max_bytes:
                return made
        except Exception:
            pass
    return None


def _clip_caption_text(clip: Dict[str, Any], max_len: int = 980) -> str:
    title = str(clip.get("title") or clip.get("hook") or "Клип").strip()
    score = int(round(float(clip.get("score") or 0) * 100))
    dur = max(0.0, float(clip.get("end") or 0) - float(clip.get("start") or 0))
    caption = str(clip.get("caption") or "").strip()
    head = f"{title}\nScore: {score}/100 · {dur:.1f}s"
    text = f"{head}\n\n{caption}" if caption else head
    return text[:max_len]


def _regenerate_hook_and_caption(clip: Dict[str, Any]) -> Tuple[str, str]:
    words = clip.get("words") or []
    transcript = " ".join(str(w.get("word") or "") for w in words).strip()
    old_hook = str(clip.get("hook") or clip.get("title") or "").strip()
    try:
        from . import ai

        if ai.configured():
            resp = ai.chat([
                {"role": "system", "content": "Придумай свежий короткий вирусный хук (3-7 слов, без точки в конце) и короткое описание с хэштегами. Верни JSON: {\"hook\": \"...\", \"caption\": \"...\"}."},
                {"role": "user", "content": f"Старый хук: {old_hook}\nТекст клипа: {transcript[:900]}"},
            ], max_tokens=220, temperature=0.8)
            raw = resp.get("text") or ""
            s, e = raw.find("{"), raw.rfind("}")
            if s != -1 and e > s:
                parsed = json.loads(raw[s:e + 1])
                nh = " ".join(str(parsed.get("hook") or "").split())[:90]
                nc = " ".join(str(parsed.get("caption") or "").split())[:280]
                if nh:
                    return nh, nc or str(clip.get("caption") or "")
    except Exception:
        pass
    # Локальный fallback без ИИ: берём другую часть речи или перестраиваем хук
    tokens = [t for t in transcript.split() if len(t) > 1]
    if len(tokens) >= 6:
        mid = max(1, len(tokens) // 3)
        alt = " ".join(tokens[mid:mid + 6]).strip(".,;:—- ")
        if alt and alt.lower() != old_hook.lower():
            return alt[:1].upper() + alt[1:], str(clip.get("caption") or "")
    fallback = f"Смотри до конца: {old_hook}" if old_hook and not old_hook.lower().startswith("смотри") else (old_hook or "Главный момент")
    return fallback[:80], str(clip.get("caption") or "")


def _watch_rerender_and_push(cid: str) -> None:
    """Ждёт окончания перерендера после Regenerate Hook и отправляет обновлённый клип."""
    deadline = time.time() + 240.0
    while time.time() < deadline and not _STOP_EVENT.is_set():
        time.sleep(2.5)
        clip = db.get_clip(cid)
        if not clip:
            return
        if clip.get("status") == "ready":
            notify_clip_ready(cid)
            return
        if clip.get("status") == "error":
            return


def handle_clip_action(action: str, cid: str) -> Dict[str, Any]:
    """Выполняет approve / skip / rehook для клипа (общее ядро Telegram и Discord)."""
    clip = db.get_clip(cid)
    if not clip:
        return {"ok": False, "label": "Клип не найден"}
    if action == "approve":
        db.set_clip_approval(cid, "approved")
        try:
            exp = pipeline.export_approved_clip(cid)
            return {"ok": True, "status": "approved", "label": "Approved", "export": exp}
        except Exception as exc:  # noqa: BLE001
            return {"ok": True, "status": "approved", "label": f"Approved (без экспорта: {str(exc)[:80]})"}
    if action == "skip":
        db.set_clip_approval(cid, "skipped")
        return {"ok": True, "status": "skipped", "label": "Skipped"}
    if action == "rehook":
        new_hook, new_caption = _regenerate_hook_and_caption(clip)
        db.set_clip_approval(cid, "pending")
        submitted = jobs.submit_rerender(cid, {"hook": new_hook, "caption": new_caption})
        if submitted:
            threading.Thread(
                target=_watch_rerender_and_push, args=(cid,), name=f"bot-rehook-{cid[:6]}", daemon=True
            ).start()
        return {"ok": True, "status": "rehook", "label": f"Regenerating: {new_hook[:48]}", "hook": new_hook}
    return {"ok": False, "label": "Неизвестное действие"}


def handle_url_submission(url: str) -> Dict[str, Any]:
    """Создаёт и запускает проект из ссылки, присланной авторизованным пользователем."""
    conf = app_settings.get()
    base_opts: Dict[str, Any] = {}
    default_pid = str(conf.get("default_profile_id") or "").strip()
    if default_pid:
        kit = profiles.get_profile(default_pid)
        if kit and isinstance(kit.get("config"), dict):
            base_opts.update(kit["config"])
    base_opts["autostart"] = True
    base_opts["bot_deliver"] = True
    opts = pipeline.normalize_options(base_opts)
    project = db.create_project(url, opts)
    jobs.submit_prepare(project["id"])
    return {"ok": True, "project_id": project["id"]}


# --- Telegram Bot API (Long Polling) -----------------------------------------

def _tg_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _resolve_tg_chat_id(conf: Dict[str, Any]) -> str:
    explicit = str(conf.get("tg_chat_id") or "").strip()
    if explicit:
        return explicit
    ids, _ = parse_allowed_users(conf.get("tg_allowed_users") or "")
    return next(iter(sorted(ids)), "")


def send_clip_telegram(cid: str, conf: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    conf = conf or app_settings.get()
    token = str(conf.get("tg_token") or "").strip()
    chat_id = _resolve_tg_chat_id(conf)
    if not token or not chat_id:
        return {"ok": False, "error": "Не указан токен Telegram или chat_id"}
    clip = db.get_clip(cid)
    if not clip:
        return {"ok": False, "error": "Клип не найден"}
    preview = _ensure_preview_file(clip, TG_MAX_VIDEO_BYTES)
    if not preview:
        return {"ok": False, "error": "Видеофайл клипа не найден или превышает 45 МБ"}
    markup = {
        "inline_keyboard": [[
            {"text": "Approve", "callback_data": f"approve:{cid}"},
            {"text": "Skip", "callback_data": f"skip:{cid}"},
            {"text": "Regenerate Hook", "callback_data": f"rehook:{cid}"},
        ]]
    }
    resp = _multipart_post(
        _tg_url(token, "sendVideo"),
        fields={
            "chat_id": chat_id,
            "caption": _clip_caption_text(clip, 1000),
            "supports_streaming": "true",
            "reply_markup": json.dumps(markup, ensure_ascii=False),
        },
        files={"video": (f"{cid}.mp4", preview, "video/mp4")},
    )
    return {"ok": bool(resp.get("ok")), "result": resp.get("result")}


def process_telegram_update(update: Dict[str, Any], conf: Dict[str, Any]) -> bool:
    """Обрабатывает один Telegram update с обязательной проверкой белого списка."""
    token = str(conf.get("tg_token") or "").strip()
    allowed_raw = str(conf.get("tg_allowed_users") or "")
    if not token:
        return False

    cb = update.get("callback_query")
    if isinstance(cb, dict):
        sender = cb.get("from") or {}
        if not is_authorized_user(sender.get("id"), sender.get("username"), allowed_raw):
            return False  # тихо игнорируем неавторизованных
        cb_id = str(cb.get("id") or "")
        data = str(cb.get("data") or "")
        if ":" not in data:
            return False
        action, cid = data.split(":", 1)
        res = handle_clip_action(action.strip(), cid.strip())
        try:
            _http_json(_tg_url(token, "answerCallbackQuery"), method="POST",
                       payload={"callback_query_id": cb_id, "text": res.get("label", "OK")[:180]})
        except Exception:
            pass
        msg = cb.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        msg_id = msg.get("message_id")
        if chat_id and msg_id:
            status_tag = f"[{res.get('label', action)}]"
            old_cap = str(msg.get("caption") or "").split("\n\nStatus:")[0]
            new_cap = f"{old_cap}\n\nStatus: {status_tag}"[:1000]
            try:
                _http_json(_tg_url(token, "editMessageCaption"), method="POST", payload={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "caption": new_cap,
                    "reply_markup": {"inline_keyboard": []},
                })
            except Exception:
                pass
        return True

    msg = update.get("message")
    if isinstance(msg, dict):
        sender = msg.get("from") or {}
        if not is_authorized_user(sender.get("id"), sender.get("username"), allowed_raw):
            return False  # тихо игнорируем неавторизованных
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        text = str(msg.get("text") or "").strip()
        if not chat_id or not text:
            return False
        if not str(conf.get("tg_chat_id") or "").strip():
            try:
                app_settings.update({"tg_chat_id": chat_id})
            except Exception:
                pass
        if text.startswith("/start") or text.startswith("/status"):
            active = sum(
                1 for p in db.list_projects(50)
                if p.get("status") in ("queued", "running", "preparing", "processing")
            )
            reply = f"KrlzCut подключён. Активных задач в очереди: {active}. Пришлите ссылку на видео для запуска нарезки."
            try:
                _http_json(_tg_url(token, "sendMessage"), method="POST",
                           payload={"chat_id": chat_id, "text": reply})
            except Exception:
                pass
            return True
        m = _URL_RE.search(text)
        if m:
            url = m.group(0)
            res = handle_url_submission(url)
            try:
                _http_json(_tg_url(token, "sendMessage"), method="POST", payload={
                    "chat_id": chat_id,
                    "text": f"Проект запущен: {res['project_id']}\nГотовые клипы придут сюда автоматически.",
                })
            except Exception:
                pass
            return True
    return False


def _tg_poll_loop() -> None:
    global _TG_OFFSET
    backoff = 2.0
    webhook_cleared = False
    while not _STOP_EVENT.is_set():
        conf = app_settings.get()
        token = str(conf.get("tg_token") or "").strip()
        if not conf.get("tg_enabled") or not token:
            with _STATE_LOCK:
                _STATUS["telegram"]["running"] = False
            break
        with _STATE_LOCK:
            _STATUS["telegram"]["running"] = True
        if not webhook_cleared:
            try:
                _http_json(_tg_url(token, "deleteWebhook"), method="POST", payload={"drop_pending_updates": False}, timeout=12)
                webhook_cleared = True
            except Exception:
                pass
        try:
            params = urllib.parse.urlencode({
                "timeout": 30,
                "offset": _TG_OFFSET,
                "allowed_updates": json.dumps(["message", "callback_query"]),
            })
            data = _http_json(_tg_url(token, f"getUpdates?{params}"), timeout=38)
            backoff = 2.0
            with _STATE_LOCK:
                _STATUS["telegram"]["last_error"] = ""
            if data.get("ok"):
                for upd in data.get("result") or []:
                    uid = int(upd.get("update_id") or 0)
                    if uid >= _TG_OFFSET:
                        _TG_OFFSET = uid + 1
                    if uid in _SEEN_UPDATES:
                        continue
                    _SEEN_UPDATES.add(uid)
                    if len(_SEEN_UPDATES) > 2000:
                        _SEEN_UPDATES.clear()
                    try:
                        process_telegram_update(upd, conf)
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001
            with _STATE_LOCK:
                _STATUS["telegram"]["last_error"] = str(exc)[:180]
            _STOP_EVENT.wait(backoff)
            backoff = min(30.0, backoff * 2.0)
    with _STATE_LOCK:
        _STATUS["telegram"]["running"] = False


# --- Discord Gateway v10 + REST v10 ------------------------------------------

_DC_API = "https://discord.com/api/v10"


def _dc_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bot {token}"}


def send_clip_discord(cid: str, conf: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    conf = conf or app_settings.get()
    token = str(conf.get("dc_token") or "").strip()
    channel_id = str(conf.get("dc_channel_id") or "").strip()
    if not token or not channel_id:
        return {"ok": False, "error": "Не указан токен Discord или Channel ID"}
    clip = db.get_clip(cid)
    if not clip:
        return {"ok": False, "error": "Клип не найден"}
    preview = _ensure_preview_file(clip, DC_MAX_VIDEO_BYTES)
    if not preview:
        return {"ok": False, "error": "Видеофайл клипа не найден или превышает 24 МБ"}
    payload_json = {
        "content": _clip_caption_text(clip, 1900),
        "components": [{
            "type": 1,
            "components": [
                {"type": 2, "style": 3, "label": "Approve", "custom_id": f"approve:{cid}"},
                {"type": 2, "style": 2, "label": "Skip", "custom_id": f"skip:{cid}"},
                {"type": 2, "style": 1, "label": "Regenerate Hook", "custom_id": f"rehook:{cid}"},
            ],
        }],
    }
    resp = _multipart_post(
        f"{_DC_API}/channels/{channel_id}/messages",
        fields={"payload_json": json.dumps(payload_json, ensure_ascii=False)},
        files={"files[0]": (f"{cid}.mp4", preview, "video/mp4")},
        headers=_dc_headers(token),
    )
    return {"ok": bool(resp.get("id")), "result": resp}


def process_discord_interaction(payload: Dict[str, Any], conf: Dict[str, Any]) -> bool:
    """Обрабатывает Discord INTERACTION_CREATE (нажатие кнопок) с fail-closed проверкой."""
    if int(payload.get("type") or 0) != 3:  # MESSAGE_COMPONENT
        return False
    user = (payload.get("member") or {}).get("user") or payload.get("user") or {}
    if not is_authorized_user(user.get("id"), user.get("username"), str(conf.get("dc_allowed_users") or "")):
        return False
    cid_raw = str((payload.get("data") or {}).get("custom_id") or "")
    if ":" not in cid_raw:
        return False
    action, cid = cid_raw.split(":", 1)
    res = handle_clip_action(action.strip(), cid.strip())
    inter_id = str(payload.get("id") or "")
    inter_tok = str(payload.get("token") or "")
    if inter_id and inter_tok:
        old_content = str((payload.get("message") or {}).get("content") or "").split("\n\nStatus:")[0]
        new_content = f"{old_content}\n\nStatus: [{res.get('label', action)}]"[:1950]
        try:
            _http_json(
                f"{_DC_API}/interactions/{inter_id}/{inter_tok}/callback",
                method="POST",
                payload={"type": 7, "data": {"content": new_content, "components": []}},
            )
        except Exception:
            pass
    return True


async def _dc_gateway_session(token: str) -> None:
    import websockets

    uri = "wss://gateway.discord.gg/?v=10&encoding=json"
    seq: Optional[int] = None

    async with websockets.connect(uri, max_size=4 * 1024 * 1024) as ws:
        hello_raw = await asyncio.wait_for(ws.recv(), timeout=15)
        hello = json.loads(hello_raw)
        hb_interval = max(5.0, float((hello.get("d") or {}).get("heartbeat_interval", 41250)) / 1000.0)

        await ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": token,
                "intents": 512,  # GUILD_MESSAGES (достаточно для interaction events без privileged intents)
                "properties": {"os": sys.platform, "browser": "KrlzCut", "device": "KrlzCut"},
            },
        }))

        async def _heartbeat() -> None:
            while not _STOP_EVENT.is_set():
                await asyncio.sleep(hb_interval)
                try:
                    await ws.send(json.dumps({"op": 1, "d": seq}))
                except Exception:
                    break

        hb_task = asyncio.create_task(_heartbeat())
        try:
            while not _STOP_EVENT.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                except asyncio.TimeoutError:
                    continue
                msg = json.loads(raw)
                if msg.get("s") is not None:
                    seq = msg["s"]
                op = msg.get("op")
                if op == 1:
                    await ws.send(json.dumps({"op": 1, "d": seq}))
                elif op == 0 and msg.get("t") == "INTERACTION_CREATE":
                    conf = app_settings.get()
                    try:
                        await asyncio.to_thread(process_discord_interaction, msg.get("d") or {}, conf)
                    except Exception:
                        pass
        finally:
            hb_task.cancel()


def _dc_gateway_loop() -> None:
    backoff = 3.0
    while not _STOP_EVENT.is_set():
        conf = app_settings.get()
        token = str(conf.get("dc_token") or "").strip()
        if not conf.get("dc_enabled") or not token:
            with _STATE_LOCK:
                _STATUS["discord"]["running"] = False
            break
        with _STATE_LOCK:
            _STATUS["discord"]["running"] = True
        try:
            asyncio.run(_dc_gateway_session(token))
            backoff = 3.0
        except Exception as exc:  # noqa: BLE001
            with _STATE_LOCK:
                _STATUS["discord"]["last_error"] = str(exc)[:180]
            _STOP_EVENT.wait(backoff)
            backoff = min(30.0, backoff * 2.0)
    with _STATE_LOCK:
        _STATUS["discord"]["running"] = False


# --- Жизненный цикл и публичные функции -------------------------------------

def notify_clip_ready(cid: str) -> Dict[str, Any]:
    conf = app_settings.get()
    results: Dict[str, Any] = {}
    if conf.get("tg_enabled") and str(conf.get("tg_token") or "").strip():
        try:
            results["telegram"] = send_clip_telegram(cid, conf)
        except Exception as exc:  # noqa: BLE001
            results["telegram"] = {"ok": False, "error": str(exc)[:180]}
    if conf.get("dc_enabled") and str(conf.get("dc_token") or "").strip():
        try:
            results["discord"] = send_clip_discord(cid, conf)
        except Exception as exc:  # noqa: BLE001
            results["discord"] = {"ok": False, "error": str(exc)[:180]}
    return results


def notify_clip_ready_async(cid: str) -> None:
    threading.Thread(target=notify_clip_ready, args=(cid,), name=f"bot-push-{cid[:6]}", daemon=True).start()


def test_bot(platform: str) -> Dict[str, Any]:
    """Проверяет валидность сохранённого токена через getMe / @me без утечки токена."""
    conf = app_settings.get()
    plat = str(platform or "").strip().lower()
    if plat == "telegram":
        token = str(conf.get("tg_token") or "").strip()
        if not token:
            return {"ok": False, "error": "Токен Telegram не задан"}
        try:
            data = _http_json(_tg_url(token, "getMe"), timeout=12)
            if not data.get("ok"):
                return {"ok": False, "error": str(data.get("description") or "Ошибка Telegram API")}
            uname = (data.get("result") or {}).get("username") or ""
            with _STATE_LOCK:
                _STATUS["telegram"]["bot_username"] = uname
            return {"ok": True, "username": uname}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:180]}
    if plat == "discord":
        token = str(conf.get("dc_token") or "").strip()
        if not token:
            return {"ok": False, "error": "Токен Discord не задан"}
        try:
            data = _http_json(f"{_DC_API}/users/@me", headers=_dc_headers(token), timeout=12)
            uname = str(data.get("username") or "")
            if not uname:
                return {"ok": False, "error": "Discord не вернул профиль бота"}
            with _STATE_LOCK:
                _STATUS["discord"]["bot_username"] = uname
            return {"ok": True, "username": uname}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:180]}
    return {"ok": False, "error": "Неизвестная платформа (telegram | discord)"}


def status() -> Dict[str, Any]:
    conf = app_settings.get()
    tg_ids, tg_names = parse_allowed_users(conf.get("tg_allowed_users") or "")
    dc_ids, dc_names = parse_allowed_users(conf.get("dc_allowed_users") or "")
    with _STATE_LOCK:
        snap = {
            "telegram": {
                **_STATUS["telegram"],
                "enabled": bool(conf.get("tg_enabled")),
                "configured": bool(str(conf.get("tg_token") or "").strip()),
                "allowed_count": len(tg_ids) + len(tg_names),
                "chat_id": _resolve_tg_chat_id(conf),
            },
            "discord": {
                **_STATUS["discord"],
                "enabled": bool(conf.get("dc_enabled")),
                "configured": bool(str(conf.get("dc_token") or "").strip() and str(conf.get("dc_channel_id") or "").strip()),
                "allowed_count": len(dc_ids) + len(dc_names),
            },
        }
    return snap


def start_bots() -> None:
    global _TG_THREAD, _DC_THREAD
    conf = app_settings.get()
    _STOP_EVENT.clear()
    if conf.get("tg_enabled") and str(conf.get("tg_token") or "").strip():
        if _TG_THREAD is None or not _TG_THREAD.is_alive():
            _TG_THREAD = threading.Thread(target=_tg_poll_loop, name="tg-approval-bot", daemon=True)
            _TG_THREAD.start()
    if conf.get("dc_enabled") and str(conf.get("dc_token") or "").strip():
        if _DC_THREAD is None or not _DC_THREAD.is_alive():
            _DC_THREAD = threading.Thread(target=_dc_gateway_loop, name="dc-approval-bot", daemon=True)
            _DC_THREAD.start()


def stop_bots() -> None:
    _STOP_EVENT.set()
    for t in (_TG_THREAD, _DC_THREAD):
        if t is not None and t.is_alive():
            t.join(timeout=2.0)


def restart_bots() -> None:
    stop_bots()
    start_bots()
