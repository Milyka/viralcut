"""Регрессионные тесты для KrlzCut v2.1.1 (безопасность ботов, пайплайн, рендер, live, загрузки)."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from viralcut import bgm, bot_notify, chat_replay, db, live, main, profiles, render


class TestBotSecurityAndReliabilityV211(unittest.TestCase):
    def test_safe_err_redacts_telegram_bot_token(self) -> None:
        raw = RuntimeError(
            "HTTP 401 for https://api.telegram.org/bot123456789:AAH_secret-Token_99/getUpdates failed"
        )
        redacted = bot_notify._safe_err(raw)
        self.assertNotIn("123456789", redacted)
        self.assertNotIn("AAH_secret-Token_99", redacted)
        self.assertIn("bot***", redacted)

    def test_discord_interaction_defers_type_6_then_patches_original(self) -> None:
        calls = []

        def _fake_http(url, *, method="GET", headers=None, payload=None, timeout=20.0):
            calls.append((method, url, payload))
            return {"ok": True}

        conf = {
            "dc_token": "DC_TOK",
            "dc_allowed_users": "42",
        }
        inter = {
            "type": 3,
            "id": "inter_99",
            "application_id": "app_777",
            "token": "tok_abc",
            "member": {"user": {"id": "42", "username": "owner"}},
            "message": {"content": "Clip #1"},
            "data": {"custom_id": "approve:clip_1"},
        }
        with mock.patch.object(bot_notify, "_http_json", side_effect=_fake_http), \
             mock.patch.object(bot_notify, "handle_clip_action", return_value={"ok": True, "label": "Approved"}) as act_mock:
            handled = bot_notify.process_discord_interaction(inter, conf)

        self.assertTrue(handled)
        act_mock.assert_called_once_with("approve", "clip_1")
        self.assertEqual(len(calls), 2)
        # 1. Сначала немедленный deferred ACK (type 6)
        self.assertEqual(calls[0][0], "POST")
        self.assertTrue(calls[0][1].endswith("/interactions/inter_99/tok_abc/callback"))
        self.assertEqual(calls[0][2], {"type": 6})
        # 2. Затем PATCH оригинального сообщения через webhook
        self.assertEqual(calls[1][0], "PATCH")
        self.assertTrue(calls[1][1].endswith("/webhooks/app_777/tok_abc/messages/@original"))
        self.assertIn("Status: [Approved]", calls[1][2]["content"])

    def test_watch_rerender_ignores_stale_updated_at_until_fresh(self) -> None:
        prev_ts = 1000.0
        snapshots = [
            {"id": "c1", "status": "ready", "updated_at": 1000.0},   # старый снимок до старта рендера
            {"id": "c1", "status": "rendering", "updated_at": 1001.0},
            {"id": "c1", "status": "ready", "updated_at": 1005.5},   # свежий готовый рендер
        ]
        idx = {"i": 0}

        def _fake_get_clip(_cid):
            cur = snapshots[min(idx["i"], len(snapshots) - 1)]
            idx["i"] += 1
            return cur

        with mock.patch.object(bot_notify.db, "get_clip", side_effect=_fake_get_clip), \
             mock.patch.object(bot_notify, "notify_clip_ready") as notify_mock:
            bot_notify._watch_rerender_and_push("c1", prev_ts, poll_interval=0.01, timeout=2.0)

        notify_mock.assert_called_once_with("c1")
        self.assertGreaterEqual(idx["i"], 3)

    def test_handle_url_submission_dispatches_stream_vs_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with mock.patch.object(db, "DB_PATH", db_path), \
                 mock.patch.object(bot_notify.app_settings, "get", return_value={"default_profile_id": "p_stream"}), \
                 mock.patch.object(bot_notify.profiles, "get_profile", return_value={
                     "id": "p_stream",
                     "name": "StreamKit",
                     "config": {"cut_mode": "stream", "aspect": "9:16"},
                 }), \
                 mock.patch.object(bot_notify.jobs, "submit_stream") as stream_mock, \
                 mock.patch.object(bot_notify.jobs, "submit_prepare") as prep_mock:
                db.init_db()
                res_stream = bot_notify.handle_url_submission("https://twitch.tv/testchannel")
                self.assertTrue(res_stream["ok"])
                stream_mock.assert_called_once()
                prep_mock.assert_not_called()

            with mock.patch.object(db, "DB_PATH", db_path), \
                 mock.patch.object(bot_notify.app_settings, "get", return_value={}), \
                 mock.patch.object(bot_notify.profiles, "get_profile", return_value=None), \
                 mock.patch.object(bot_notify.jobs, "submit_stream") as stream_mock, \
                 mock.patch.object(bot_notify.jobs, "submit_prepare") as prep_mock:
                res_vod = bot_notify.handle_url_submission("https://youtu.be/dQw4w9WgXcQ")
                self.assertTrue(res_vod["ok"])
                prep_mock.assert_called_once()
                stream_mock.assert_not_called()


class TestChatReplayAndPipelineV211(unittest.TestCase):
    def test_parse_chat_replay_continues_past_single_message_spike(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "video.live_chat.json"
            lines = []
            # Тихая зона в начале (t=15s): 1 хайп-сообщение ("LULW" -> вес 1.65, z=1.65, counts=1)
            lines.append(json.dumps({
                "replayChatItemAction": {
                    "videoOffsetTimeMsec": "15000",
                    "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
                        "message": {"runs": [{"text": "LULW"}]},
                    }}}}],
                }
            }))
            # Активная зона позже (t=160..240s): фоновый шум (1-2 сообщения/корзину -> выше MAD)
            # и реальный пик в t=200s с 4 сообщениями (z ~ 1.4-1.6, меньше чем 1.65 у одиночного хайпа!).
            for sec in range(150, 250, 5):
                n_msg = 4 if sec == 200 else (2 if sec % 10 == 0 else 1)
                for k in range(n_msg):
                    lines.append(json.dumps({
                        "replayChatItemAction": {
                            "videoOffsetTimeMsec": str(sec * 1000 + k * 200),
                            "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
                                "message": {"runs": [{"text": "hello"}]},
                            }}}}],
                        }
                    }))
            chat_path.write_text("\n".join(lines), encoding="utf-8")

            parsed = chat_replay.parse_chat_replay(chat_path, duration=260.0, bin_sec=5.0)
            assert parsed is not None
            peak_starts = [p["start"] for p in parsed["peaks"]]
            # Одиночное сообщение в 15s (counts=1 < 2) отброшено, но цикл НЕ оборвался break'ом,
            # поэтому реальный пик на 200s сохранён!
            self.assertNotIn(15.0, peak_starts)
            self.assertIn(200.0, peak_starts)

            # load_or_build удаляет исходный .live_chat.json после сохранения chat_curve.json
            workdir = Path(tmp) / "proj"
            workdir.mkdir()
            raw_chat = workdir / "source.live_chat.json"
            raw_chat.write_text("\n".join(lines), encoding="utf-8")
            curve = chat_replay.load_or_build(workdir, duration=260.0)
            self.assertIsNotNone(curve)
            self.assertTrue((workdir / "chat_curve.json").is_file())
            self.assertFalse(raw_chat.exists())


class TestBrandAssetsEarlyValidationAndLiveV211(unittest.TestCase):
    def test_brand_assets_upload_rejects_bad_kind_and_suffix_before_disk_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets_dir = Path(tmp) / "brand_assets"
            with mock.patch.object(profiles, "BRAND_ASSETS_DIR", assets_dir), \
                 mock.patch.object(profiles, "ASSETS_META_PATH", assets_dir / "assets.json"):
                client = TestClient(main.app)
                hdr = {"X-Krlz-Token": main._SESSION_TOKEN}

                # Недопустимый kind
                r1 = client.post(
                    "/api/brand-assets",
                    headers=hdr,
                    data={"kind": "avatar", "name": "bad"},
                    files={"file": ("logo.png", b"FAKEPNG", "image/png")},
                )
                self.assertEqual(r1.status_code, 400)
                self.assertFalse(assets_dir.exists())

                # Недопустимое расширение для watermark (.exe)
                r2 = client.post(
                    "/api/brand-assets",
                    headers=hdr,
                    data={"kind": "watermark", "name": "evil"},
                    files={"file": ("payload.exe", b"MZ12345", "application/octet-stream")},
                )
                self.assertEqual(r2.status_code, 400)
                self.assertFalse(assets_dir.exists())

                # Недопустимое расширение для intro (.png)
                r3 = client.post(
                    "/api/brand-assets",
                    headers=hdr,
                    data={"kind": "intro", "name": "img"},
                    files={"file": ("pic.png", b"PNG", "image/png")},
                )
                self.assertEqual(r3.status_code, 400)
                self.assertFalse(assets_dir.exists())

    def test_live_settings_preserves_v210_fields(self) -> None:
        opts = {
            "aspect": "9:16",
            "mode": "auto",
            "watermark": {"enabled": True, "asset_id": "wa_123", "position": "bottom-left", "scale": 0.2, "opacity": 0.7, "margin": 24},
            "intro_asset_id": "in_111",
            "outro_asset_id": "ou_222",
            "bgm": {"enabled": True, "track_id": "bgm_9", "volume_db": -12.0, "ducking": True, "duck_db": -24.0},
            "punch_in_zoom": True,
            "auto_dual_split": False,
        }
        s = live._settings(opts)
        self.assertEqual(s["watermark"]["asset_id"], "wa_123")
        self.assertEqual(s["watermark"]["position"], "bottom-left")
        self.assertEqual(s["intro_asset_id"], "in_111")
        self.assertEqual(s["outro_asset_id"], "ou_222")
        self.assertEqual(s["bgm"]["track_id"], "bgm_9")
        self.assertTrue(s["punch_in_zoom"])
        self.assertFalse(s["auto_dual_split"])


class TestRenderDuckingAndBumperDurationV211(unittest.TestCase):
    def test_render_skips_ducking_when_drop_lt_1db_and_passes_bumper_total_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            bgm_file = root / "track.mp3"
            intro_file = root / "intro.mp4"
            out = root / "out.mp4"
            for f in (src, bgm_file, intro_file):
                f.write_bytes(b"0" * 64)

            captured = []

            def _fake_probe(p):
                if Path(p) == intro_file:
                    return {"width": 1080, "height": 1920, "duration": 3.5, "has_video": True, "has_audio": True}
                return {"width": 1920, "height": 1080, "duration": 30.0, "has_video": True, "has_audio": True}

            def _fake_encode(cmd, dur, on_progress=None):
                captured.append((cmd, dur))
                Path(cmd[-1]).write_bytes(b"0" * 20000)
                return 0, [], None

            with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                 mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                 mock.patch.object(render, "hw_encoder", return_value=None), \
                 mock.patch.object(bgm, "resolve_path", return_value=bgm_file), \
                 mock.patch.object(profiles, "resolve_asset", side_effect=lambda aid, expected_kind=None: intro_file if aid == "in_1" else None):
                render.render_clip(
                    src, 0.0, 10.0, out, aspect="9:16", mode="crop",
                    intro_asset_id="in_1",
                    # vol_db=-16, duck_db=-15.5 → drop_db=0 < 1.0 → sidechaincompress пропускается
                    bgm={"enabled": True, "track_id": "bgm_1", "volume_db": -16.0, "ducking": True, "duck_db": -15.5},
                )

            cmd, encode_dur = captured[0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            self.assertNotIn("sidechaincompress", fc)
            # 10.0 основной клип + 3.5 интро = 13.5с переданы в _run_encode
            self.assertAlmostEqual(encode_dur, 13.5, places=2)


if __name__ == "__main__":
    unittest.main()
