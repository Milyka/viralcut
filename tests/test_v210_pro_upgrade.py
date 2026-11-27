"""Comprehensive offline unit tests for KrlzCut v2.1.0 Pro Automation & Editing Upgrade."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from viralcut import (
    ai,
    analyze,
    bgm,
    bot_notify,
    chat_replay,
    db,
    game_layer,
    pipeline,
    profiles,
    reframe,
    render,
    settings,
)


class TestBrandKitsAndBumpers(unittest.TestCase):
    def test_db_migration_and_profile_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            # Создаём старую схему v2 без profiles и без approval_status
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE projects (id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT,
                    status TEXT NOT NULL DEFAULT 'queued', stage TEXT, progress REAL NOT NULL DEFAULT 0,
                    error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, duration REAL,
                    language TEXT, source TEXT, thumb TEXT, meta TEXT, options TEXT);
                CREATE TABLE clips (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, idx INTEGER NOT NULL,
                    start REAL NOT NULL, end REAL NOT NULL, score REAL NOT NULL DEFAULT 0, title TEXT,
                    hook TEXT, caption TEXT, status TEXT NOT NULL DEFAULT 'ready', path TEXT, thumb TEXT,
                    words TEXT, settings TEXT, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
                PRAGMA user_version = 2;
                """
            )
            conn.close()

            with mock.patch.object(db, "DB_PATH", db_path):
                db.init_db()
                kit = profiles.create_profile("Podcast Main", {
                    "aspect": "9:16",
                    "sub_font": "montserrat",
                    "punch_in_zoom": True,
                    "auto_dual_split": True,
                    "bot_deliver": True,
                })
                self.assertEqual(kit["name"], "Podcast Main")
                self.assertTrue(kit["config"]["punch_in_zoom"])
                self.assertTrue(kit["config"]["bot_deliver"])

                listed = profiles.list_profiles()
                self.assertEqual(len(listed), 1)

                updated = profiles.update_profile(kit["id"], name="Podcast Pro", config={"aspect": "4:5"})
                assert updated is not None
                self.assertEqual(updated["name"], "Podcast Pro")
                self.assertEqual(updated["config"]["aspect"], "4:5")

                self.assertTrue(profiles.delete_profile(kit["id"]))
                self.assertEqual(profiles.list_profiles(), [])

    def test_asset_validation_and_watermark_intro_outro_filtergraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "brand_assets"
            meta_path = assets_dir / "assets.json"
            wm_src = root / "logo.png"
            Image.new("RGBA", (128, 64), (250, 250, 250, 255)).save(wm_src)
            bad_wm = root / "bad.jpg"
            bad_wm.write_bytes(b"not-a-png")
            intro_src = root / "intro.mp4"
            intro_src.write_bytes(b"0" * 512)
            outro_src = root / "outro.mp4"
            outro_src.write_bytes(b"0" * 512)
            long_intro = root / "too_long.mp4"
            long_intro.write_bytes(b"0" * 512)

            with mock.patch.object(profiles, "BRAND_ASSETS_DIR", assets_dir), \
                 mock.patch.object(profiles, "ASSETS_META_PATH", meta_path):
                with self.assertRaises(ValueError):
                    profiles.add_asset("watermark", "bad.jpg", bad_wm)
                wm_item = profiles.add_asset("watermark", "logo.png", wm_src)
                self.assertEqual(wm_item["kind"], "watermark")

                with mock.patch.object(profiles.utils, "probe", return_value={"has_video": True, "width": 1080, "height": 1920, "duration": 22.0}):
                    with self.assertRaises(ValueError):
                        profiles.add_asset("intro", "too_long.mp4", long_intro)

                with mock.patch.object(profiles.utils, "probe", return_value={"has_video": True, "width": 1080, "height": 1920, "duration": 2.5, "has_audio": False}):
                    intro_item = profiles.add_asset("intro", "intro.mp4", intro_src)
                    outro_item = profiles.add_asset("outro", "outro.mp4", outro_src)

                # Теперь проверяем filter_complex рендера с watermark + ASS + intro + outro
                src = root / "clip_src.mp4"
                src.write_bytes(b"0" * 64)
                ass = root / "subs.ass"
                ass.write_text("[Script Info]\n", encoding="utf-8")
                out = root / "out.mp4"
                captured = []

                def _fake_probe(p):
                    name = Path(p).name
                    if name.startswith("in_"):
                        return {"width": 1080, "height": 1920, "duration": 2.0, "has_video": True, "has_audio": False}
                    if name.startswith("ou_"):
                        return {"width": 1080, "height": 1920, "duration": 3.0, "has_video": True, "has_audio": True}
                    return {"width": 1920, "height": 1080, "duration": 30.0, "has_video": True, "has_audio": True}

                def _fake_encode(cmd, dur, on_progress=None):
                    captured.append(cmd)
                    Path(cmd[-1]).write_bytes(b"0" * 20000)
                    return 0, [], None

                with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                     mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                     mock.patch.object(render, "hw_encoder", return_value=None):
                    render.render_clip(
                        src, 0.0, 10.0, out, ass_path=ass,
                        aspect="9:16", mode="crop",
                        watermark={"enabled": True, "asset_id": wm_item["id"], "position": "top-right", "scale": 0.2, "opacity": 0.75, "margin": 24},
                        intro_asset_id=intro_item["id"],
                        outro_asset_id=outro_item["id"],
                    )

                self.assertTrue(captured)
                cmd = captured[0]
                fc = cmd[cmd.index("-filter_complex") + 1]
                self.assertIn("colorchannelmixer=aa=0.75", fc)
                self.assertIn("overlay=W-w-24:24:format=auto", fc)
                # ASS прожигается на основном клипе ДО concat
                self.assertLess(fc.index("ass=filename="), fc.index("concat=n=3:v=1:a=1[v][aout]"))
                # У интро нет аудио → anullsrc fallback
                self.assertIn("anullsrc=r=48000:cl=stereo:d=2.000[a_intro]", fc)
                # Итоговое -t = 10 + 2 + 3 = 15.000
                t_val = float(cmd[cmd.index("-t") + 1 if cmd.count("-t") == 1 else len(cmd) - 1 - cmd[::-1].index("-t") + 1])
                self.assertAlmostEqual(t_val, 15.0, places=2)


class TestGameLayerPool(unittest.TestCase):
    def test_tag_filtering_repeat_avoidance_and_offset_clamping(self) -> None:
        fake_clips = [
            {"id": "game_1", "name": "MC 1", "duration": 60.0, "builtin": False, "tags": ["minecraft", "parkour"]},
            {"id": "game_2", "name": "MC 2", "duration": 45.0, "builtin": False, "tags": ["minecraft"]},
            {"id": "game_3", "name": "GTA", "duration": 120.0, "builtin": False, "tags": ["gta"]},
        ]
        pool_cfg = {"enabled": True, "tag": "minecraft", "split": "60/40", "clip_ids": []}
        with mock.patch.object(game_layer, "list_clips", return_value=fake_clips):
            prev = None
            for _ in range(25):
                picked = game_layer.pick_random_from_pool(
                    pool_cfg, clip_len=20.0, exclude_ids=[prev] if prev else None
                )
                assert picked is not None
                self.assertIn(picked["clip_id"], ("game_1", "game_2"))
                if prev is not None:
                    self.assertNotEqual(picked["clip_id"], prev)
                dur = 60.0 if picked["clip_id"] == "game_1" else 45.0
                self.assertGreaterEqual(picked["start"], 0.0)
                self.assertLessEqual(picked["start"], dur - 20.0 + 0.1)
                prev = picked["clip_id"]


class TestChatReplayAndMultimodalScoring(unittest.TestCase):
    def test_streaming_parser_bins_and_detects_hype_spike(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_file = Path(tmp) / "vod.live_chat.json"
            lines = []
            # Базовый фон: по 1 сообщению каждые 5 сек (0..120с)
            for sec in range(0, 120, 5):
                lines.append(json.dumps({
                    "replayChatItemAction": {
                        "videoOffsetTimeMsec": str(sec * 1000),
                        "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"message": {"runs": [{"text": "hello"}]}}}}}],
                    }
                }))
            # Мощный всплеск хайпа на 60..64с (25 сообщений)
            for k in range(25):
                lines.append(json.dumps({
                    "replayChatItemAction": {
                        "videoOffsetTimeMsec": str(int((60.0 + k * 0.15) * 1000)),
                        "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"message": {"runs": [{"text": "OMEGALUL NO WAY!!!"}]}}}}}],
                    }
                }))
            chat_file.write_text("\n".join(lines), encoding="utf-8")

            parsed = chat_replay.parse_chat_replay(chat_file, duration=120.0, bin_sec=5.0)
            assert parsed is not None
            self.assertEqual(parsed["bin_sec"], 5.0)
            self.assertGreaterEqual(parsed["total_messages"], 40)
            self.assertTrue(parsed["peaks"])
            top_peak = parsed["peaks"][0]
            self.assertGreaterEqual(top_peak["start"], 55.0)
            self.assertLessEqual(top_peak["start"], 65.0)
            self.assertIn("OMEGALUL", top_peak["sample_msg"])

            # Окно [50, 60] с лагом +4с попадает прямо в [54, 64]
            self.assertGreater(chat_replay.window_score(parsed, 50.0, 60.0, lag_sec=4.0), 0.5)
            # Отсутствующий файл → None без ошибки
            self.assertIsNone(chat_replay.parse_chat_replay(Path(tmp) / "missing.json", 120.0))

    def test_ai_plan_clips_includes_multimodal_peaks_block(self) -> None:
        captured_payload = {}

        def _fake_post(url, payload, api_key):
            captured_payload.update(payload)
            return {"choices": [{"message": {"content": json.dumps({"clips": [{"start": 52, "end": 72, "hook": "Невероятный момент", "title": "Пик чата", "caption": "#shorts"}]})}}]}

        segs = [{"start": 0.0, "end": 80.0, "text": "Раз два три проверка момента в эфире"}]
        peaks = [{"start": 56.0, "end": 64.0, "score": 0.94, "reasons": ["chat spike", "audio burst (+10dB)"], "sample": "OMEGALUL"}]
        with mock.patch.object(ai, "_conf", return_value={"provider": "openai", "base": "https://api.openai.com/v1", "model": "gpt-4o-mini", "label": "OpenAI", "key_url": ""}), \
             mock.patch.object(ai, "key", return_value="sk-test"), \
             mock.patch.object(ai, "_post", side_effect=_fake_post):
            res = ai.plan_clips(segs, 90.0, options={"count": 3, "min_dur": 10, "max_dur": 40}, multimodal_peaks=peaks)
        self.assertEqual(len(res["clips"]), 1)
        prompt_text = captured_payload["messages"][1]["content"]
        self.assertIn("[TIMELINE HYPE PEAKS", prompt_text)
        self.assertIn("chat spike", prompt_text)


class TestDualSplitReframeAndRender(unittest.TestCase):
    def test_detects_dual_split_above_60pct_and_falls_back_for_single_speaker(self) -> None:
        dual_samples = [
            (float(i), [
                {"cx": 420.0, "cy": 420.0, "w": 220.0, "h": 240.0, "score": 0.92},
                {"cx": 1480.0, "cy": 430.0, "w": 210.0, "h": 230.0, "score": 0.91},
            ], [None, None])
            for i in range(8)
        ] + [(8.0, [{"cx": 960.0, "cy": 400.0, "w": 220.0, "h": 240.0, "score": 0.9}], [None])]
        dual = reframe._detect_dual_split(dual_samples, 1920, 1080, 9, 16)
        assert dual is not None
        self.assertEqual(dual["layout"], "dual_split")
        self.assertGreaterEqual(dual["coverage"], 0.60)
        self.assertLess(dual["top"]["x"], dual["bottom"]["x"])

        single_samples = [
            (float(i), [{"cx": 960.0, "cy": 420.0, "w": 220.0, "h": 240.0, "score": 0.92}], [None])
            for i in range(10)
        ]
        self.assertIsNone(reframe._detect_dual_split(single_samples, 1920, 1080, 9, 16))

        # Проверка FFmpeg 50/50 vstack графа
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pod.mp4"
            out = Path(tmp) / "out.mp4"
            src.write_bytes(b"0" * 64)
            captured = []

            def _fake_encode(cmd, dur, on_progress=None):
                captured.append(cmd)
                Path(cmd[-1]).write_bytes(b"0" * 20000)
                return 0, [], None

            with mock.patch.object(render, "probe", return_value={"width": 1920, "height": 1080, "duration": 20.0, "has_video": True, "has_audio": True}), \
                 mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                 mock.patch.object(render, "hw_encoder", return_value=None):
                render.render_clip(src, 0.0, 10.0, out, aspect="9:16", mode="auto", crop_path=dual)

            fc = captured[0][captured[0].index("-filter_complex") + 1]
            self.assertIn("split=2[_ds_in1][_ds_in2]", fc)
            self.assertIn("[_topn][_botn]vstack=inputs=2[base]", fc)


class TestBgmDuckingAndPunchInZoom(unittest.TestCase):
    def test_bgm_sidechain_with_voice_without_voice_with_game_and_punch_in_zoom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            bgm_file = root / "track.mp3"
            game_file = root / "game.mp4"
            out = root / "out.mp4"
            for f in (src, bgm_file, game_file):
                f.write_bytes(b"0" * 64)

            def _run_case(has_voice: bool, with_game_audio: bool, punch_zoom: bool) -> str:
                captured = []

                def _fake_probe(p):
                    if Path(p) == game_file:
                        return {"width": 1080, "height": 1920, "duration": 10.0, "has_video": True, "has_audio": with_game_audio}
                    return {"width": 1920, "height": 1080, "duration": 30.0, "has_video": True, "has_audio": has_voice}

                def _fake_encode(cmd, dur, on_progress=None):
                    captured.append(cmd)
                    Path(cmd[-1]).write_bytes(b"0" * 20000)
                    return 0, [], None

                with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                     mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                     mock.patch.object(render, "hw_encoder", return_value=None), \
                     mock.patch.object(bgm, "resolve_path", return_value=bgm_file), \
                     mock.patch.object(game_layer, "resolve_path", return_value=game_file):
                    render.render_clip(
                        src, 0.0, 12.0, out, aspect="9:16", mode="crop",
                        bgm={"enabled": True, "track_id": "bgm_1", "volume_db": -14.0, "ducking": True, "duck_db": -22.0},
                        game_layer={"enabled": True, "clip_id": "g1", "audio": True} if with_game_audio else None,
                        punch_in_zoom=punch_zoom,
                    )
                return captured[0][captured[0].index("-filter_complex") + 1]

            fc_voice = _run_case(has_voice=True, with_game_audio=False, punch_zoom=True)
            self.assertIn("asplit=2[voice][voicemix]", fc_voice)
            self.assertIn("sidechaincompress=threshold=0.04:", fc_voice)
            self.assertIn("amix=inputs=2:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95", fc_voice)
            self.assertIn("zoompan=z='if(lte(on,90),1+0.08*(on/90)", fc_voice)
            self.assertIn("s=1080x1920:fps=30", fc_voice)

            fc_silent = _run_case(has_voice=False, with_game_audio=False, punch_zoom=False)
            self.assertNotIn("sidechaincompress", fc_silent)
            self.assertIn("[bgm_pre]", fc_silent)

            fc_game = _run_case(has_voice=True, with_game_audio=True, punch_zoom=False)
            self.assertIn("sidechaincompress=threshold=0.04:", fc_game)
            self.assertIn("amix=inputs=3:duration=first", fc_game)


class TestBotWhitelistAndCallbacks(unittest.TestCase):
    def test_fail_closed_authorization_whitelist(self) -> None:
        # Пустой белый список → всегда False
        self.assertFalse(bot_notify.is_authorized_user(123456, "milyka", ""))
        self.assertFalse(bot_notify.is_authorized_user(123456, "milyka", "   "))
        # Совпадение по числовому ID
        self.assertTrue(bot_notify.is_authorized_user(123456, "other", "123456, @admin"))
        # Совпадение по @username без учёта регистра
        self.assertTrue(bot_notify.is_authorized_user(999999, "MiLyKa", "123456, @milyka"))
        # Чужой пользователь → False
        self.assertFalse(bot_notify.is_authorized_user(999999, "intruder", "123456, @milyka"))

    def test_settings_hides_bot_tokens_in_public_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with mock.patch.object(settings, "SETTINGS_FILE", cfg):
                saved = settings.update({"tg_token": "12345:SECRET_TG", "dc_token": "SECRET_DC", "tg_allowed_users": "@milyka"})
                pub = settings.public(saved)
                self.assertEqual(pub["tg_token"], "")
                self.assertTrue(pub["tg_token_set"])
                self.assertEqual(pub["dc_token"], "")
                self.assertTrue(pub["dc_token_set"])

    def test_telegram_callbacks_approve_skip_rehook_and_block_unauthorized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.db"
            clip_mp4 = root / "clip.mp4"
            clip_mp4.write_bytes(b"MP4DATA")
            exports_dir = root / "approved_out"
            exports_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(db, "DB_PATH", db_path), \
                 mock.patch.object(settings, "SETTINGS_FILE", root / "settings.json"), \
                 mock.patch.object(pipeline, "DATA_DIR", root):
                db.init_db()
                settings.update({"clips_dir": str(exports_dir)})
                proj = db.create_project("https://example.com/v", {})
                clip = db.add_clip(
                    proj["id"], 0, 0.0, 12.0, 0.88, "Test Clip", "Old Hook", "#viral",
                    [{"word": "Это", "start": 0.1, "end": 0.4}, {"word": "тестовый", "start": 0.5, "end": 0.9},
                     {"word": "клип", "start": 1.0, "end": 1.4}, {"word": "для", "start": 1.5, "end": 1.7},
                     {"word": "проверки", "start": 1.8, "end": 2.2}, {"word": "бота", "start": 2.3, "end": 2.7}],
                    {}, status="ready",
                )
                db.update_clip(clip["id"], path=str(clip_mp4))
                conf = {"tg_token": "123:ABC", "tg_allowed_users": "777, @owner", "tg_chat_id": "777"}

                # 1. Чужой пользователь игнорируется молча
                with mock.patch.object(bot_notify, "_http_json") as http_mock:
                    handled = bot_notify.process_telegram_update({
                        "update_id": 100,
                        "callback_query": {
                            "id": "cb0",
                            "from": {"id": 999, "username": "stranger"},
                            "data": f"approve:{clip['id']}",
                        },
                    }, conf)
                    self.assertFalse(handled)
                    http_mock.assert_not_called()

                # 2. Авторизованный Approve → статус approved + экспорт mp4/srt/txt
                with mock.patch.object(bot_notify, "_http_json", return_value={"ok": True}):
                    handled = bot_notify.process_telegram_update({
                        "update_id": 101,
                        "callback_query": {
                            "id": "cb1",
                            "from": {"id": 777, "username": "owner"},
                            "data": f"approve:{clip['id']}",
                            "message": {"message_id": 10, "chat": {"id": 777}, "caption": "Test Clip"},
                        },
                    }, conf)
                    self.assertTrue(handled)
                after_approve = db.get_clip(clip["id"])
                assert after_approve is not None
                self.assertEqual(after_approve["approval_status"], "approved")
                approved_files = list((exports_dir / "Approved").glob("*"))
                suffixes = {p.suffix for p in approved_files}
                self.assertTrue({".mp4", ".srt", ".txt"}.issubset(suffixes))

                # 3. Авторизованный Skip → статус skipped
                with mock.patch.object(bot_notify, "_http_json", return_value={"ok": True}):
                    bot_notify.process_telegram_update({
                        "update_id": 102,
                        "callback_query": {
                            "id": "cb2",
                            "from": {"id": 888, "username": "OWNER"},
                            "data": f"skip:{clip['id']}",
                        },
                    }, conf)
                self.assertEqual(db.get_clip(clip["id"])["approval_status"], "skipped")

                # 4. Авторизованный Regenerate Hook → вызывает jobs.submit_rerender (в фоне после answerCallbackQuery)
                with mock.patch.object(bot_notify, "_http_json", return_value={"ok": True}), \
                     mock.patch.object(bot_notify.jobs, "submit_rerender", return_value=True) as rerender_mock, \
                     mock.patch.object(bot_notify, "_watch_rerender_and_push"):
                    bot_notify.process_telegram_update({
                        "update_id": 103,
                        "callback_query": {
                            "id": "cb3",
                            "from": {"id": 777, "username": "owner"},
                            "data": f"rehook:{clip['id']}",
                        },
                    }, conf)
                    import time as _time
                    deadline = _time.monotonic() + 2.0
                    while not rerender_mock.called and _time.monotonic() < deadline:
                        _time.sleep(0.02)
                    rerender_mock.assert_called_once()
                    args = rerender_mock.call_args[0]
                    self.assertEqual(args[0], clip["id"])
                    self.assertTrue(args[1].get("hook"))


class TestPreV210AuditFixesAndCombinedFiltergraphs(unittest.TestCase):
    def test_split_screen_face_focus_uses_x_key_and_guards_dual_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            game = root / "game.mp4"
            out = root / "out.mp4"
            src.write_bytes(b"0" * 64)
            game.write_bytes(b"0" * 64)
            captured = []

            def _fake_probe(p):
                if Path(p) == game:
                    return {"width": 1080, "height": 1920, "duration": 10.0, "has_video": True, "has_audio": False}
                return {"width": 1920, "height": 1080, "duration": 30.0, "has_video": True, "has_audio": True}

            def _fake_encode(cmd, dur, on_progress=None):
                captured.append(cmd)
                Path(cmd[-1]).write_bytes(b"0" * 20000)
                return 0, [], None

            # Лицо справа: x=[1100, 1200], crop_w=608 → avg_x=1150, center=1454/1920 ≈ 0.757
            crop_path = {"times": [0.0, 5.0], "x": [1100.0, 1200.0], "y": [0.0, 0.0], "crop_w": 608, "crop_h": 1080, "source": [1920, 1080]}
            with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                 mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                 mock.patch.object(render, "hw_encoder", return_value=None), \
                 mock.patch.object(game_layer, "resolve_path", return_value=game):
                render.render_clip(
                    src, 0.0, 8.0, out, aspect="9:16", mode="auto", crop_path=crop_path,
                    game_layer={"enabled": True, "clip_id": "g1", "split": "60/40"},
                )

            fc = captured[0][captured[0].index("-filter_complex") + 1]
            # Ожидаем фокус ~0.757 (не дефолтный 0.500!)
            self.assertIn("0.757", fc)

    def test_assistant_execute_forwards_v2_style_fields(self) -> None:
        from viralcut import assistant_actions

        fake_clip = {"id": "c1", "project_id": "p1", "idx": 0, "status": "ready"}
        fake_proj = {"id": "p1", "status": "done", "options": {}}
        with mock.patch.object(assistant_actions.db, "get_clip", return_value=fake_clip), \
             mock.patch.object(assistant_actions.jobs, "submit_rerender", return_value=True) as sub_mock:
            res = assistant_actions.execute({
                "type": "rerender_clip",
                "clip_id": "c1",
                "sub_anim": "bounce",
                "sub_outline": False,
                "sub_outline_width": 9,
                "sub_outline_color": "#112233",
            })
            self.assertTrue(res["ok"])
            patch = sub_mock.call_args[0][1]
            self.assertEqual(patch["sub_anim"], "bounce")
            self.assertFalse(patch["sub_outline"])
            self.assertEqual(patch["sub_outline_width"], 9)
            self.assertEqual(patch["sub_outline_color"], "#112233")

        saved_opts = {}
        with mock.patch.object(assistant_actions.db, "get_project", return_value=fake_proj), \
             mock.patch.object(assistant_actions.db, "update_project", side_effect=lambda pid, **kw: saved_opts.update(kw.get("options") or {})):
            res2 = assistant_actions.execute({
                "type": "update_project",
                "project_id": "p1",
                "sub_anim": "slide",
                "sub_outline_width": 5,
            })
            self.assertTrue(res2["ok"])
            self.assertEqual(saved_opts["sub_anim"], "slide")
            self.assertEqual(saved_opts["sub_outline_width"], 5)

    def test_enrich_project_cache_busts_thumb_and_reports_size_bytes(self) -> None:
        from viralcut import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid = "p1"
            src = root / pid / "source.mp4"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(b"X" * 4096)
            thumb = root / pid / "thumbs" / "c1.jpg"
            thumb.parent.mkdir(parents=True, exist_ok=True)
            thumb.write_bytes(b"J" * 32)
            with mock.patch.object(main, "PROJECTS_DIR", root):
                out = main._enrich_project(
                    {"id": pid, "source": str(src), "meta": {}},
                    summary={"total_clips": 1, "ready_clips": 1, "thumb": str(thumb), "updated_at": 1700001234.5},
                )
            self.assertEqual(out["thumb_url"], f"/media/{pid}/thumbs/c1.jpg?v=1700001234")
            self.assertEqual(out["size_bytes"], 4096)

    def test_security_guard_rejects_empty_host_header(self) -> None:
        from fastapi.testclient import TestClient
        from viralcut import main

        client = TestClient(main.app, raise_server_exceptions=False)
        resp = client.get("/api/health", headers={"Host": ""})
        self.assertEqual(resp.status_code, 403)

    def test_per_model_active_refcount_blocks_delete_even_after_model_switch(self) -> None:
        from viralcut import transcribe

        with mock.patch.dict(transcribe._ACTIVE_BY_MODEL, {"medium": 1}, clear=True), \
             mock.patch.object(transcribe, "active_model_key", return_value="small"):
            with self.assertRaises(RuntimeError):
                transcribe.delete_model("medium")

    def test_combined_v210_filtergraphs_have_no_label_collisions(self) -> None:
        import re as _re

        def _assert_unique_output_labels(fc: str) -> None:
            # Каждый узел графа заканчивается выходными метками [lbl]; имена не должны дублироваться
            out_labels = []
            for chain in fc.split(";"):
                chain = chain.strip()
                if not chain:
                    continue
                tail = _re.findall(r"\[([A-Za-z0-9_]+)\]$", chain)
                # для concat=n=...[v][aout] могут быть 2 выходные метки в конце
                m = _re.search(r"((?:\[[A-Za-z0-9_]+\])+)$", chain)
                if m:
                    out_labels.extend(_re.findall(r"\[([A-Za-z0-9_]+)\]", m.group(1)))
            self.assertEqual(len(out_labels), len(set(out_labels)), f"Duplicate FFmpeg output labels: {out_labels}\n{fc}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            game = root / "game.mp4"
            bgm_file = root / "bgm.mp3"
            wm_file = root / "wm.png"
            intro = root / "intro.mp4"
            outro = root / "outro.mp4"
            ass = root / "s.ass"
            out = root / "out.mp4"
            for f in (src, game, bgm_file, intro, outro):
                f.write_bytes(b"0" * 64)
            Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(wm_file)
            ass.write_text("[Script Info]\n", encoding="utf-8")

            def _run_graph(info_map, **kwargs) -> str:
                captured = []

                def _fake_probe(p):
                    return info_map.get(Path(p).name, info_map["default"])

                def _fake_encode(cmd, dur, on_progress=None):
                    captured.append(cmd)
                    Path(cmd[-1]).write_bytes(b"0" * 20000)
                    return 0, [], None

                def _fake_asset(aid, kind=None):
                    if aid == "wm1":
                        return wm_file
                    if aid == "in1":
                        return intro
                    if aid == "ou1":
                        return outro
                    return None

                with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                     mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                     mock.patch.object(render, "hw_encoder", return_value=None), \
                     mock.patch.object(game_layer, "resolve_path", return_value=game), \
                     mock.patch.object(bgm, "resolve_path", return_value=bgm_file), \
                     mock.patch.object(profiles, "resolve_asset", side_effect=_fake_asset):
                    render.render_clip(src, 0.0, 10.0, out, ass_path=ass, **kwargs)
                fc = captured[0][captured[0].index("-filter_complex") + 1]
                _assert_unique_output_labels(fc)
                return fc

            # 1. game_layer(audio=True) + bgm(ducking=True) + watermark + intro/outro + ASS
            fc1 = _run_graph(
                {
                    "default": {"width": 1920, "height": 1080, "duration": 20.0, "has_video": True, "has_audio": True},
                    "game.mp4": {"width": 1080, "height": 1920, "duration": 10.0, "has_video": True, "has_audio": True},
                    "intro.mp4": {"width": 1080, "height": 1920, "duration": 2.0, "has_video": True, "has_audio": False},
                    "outro.mp4": {"width": 1080, "height": 1920, "duration": 2.0, "has_video": True, "has_audio": True},
                },
                aspect="9:16", mode="crop",
                game_layer={"enabled": True, "clip_id": "g1", "split": "60/40", "audio": True},
                bgm={"enabled": True, "track_id": "b1", "volume_db": -14.0, "ducking": True, "duck_db": -22.0},
                watermark={"enabled": True, "asset_id": "wm1", "position": "top-right", "scale": 0.16, "opacity": 0.85, "margin": 30},
                intro_asset_id="in1", outro_asset_id="ou1",
            )
            self.assertIn("vstack=inputs=2[base]", fc1)
            self.assertIn("sidechaincompress", fc1)
            self.assertIn("amix=inputs=3", fc1)
            self.assertIn("concat=n=3:v=1:a=1[v][aout]", fc1)

            # 2. dual_split + punch_in_zoom + watermark + ASS
            dual = {
                "layout": "dual_split",
                "top": {"x": 100, "y": 50, "w": 800, "h": 710},
                "bottom": {"x": 1000, "y": 50, "w": 800, "h": 710},
                "source": [1920, 1080],
                "coverage": 0.9,
            }
            fc2 = _run_graph(
                {"default": {"width": 1920, "height": 1080, "duration": 20.0, "has_video": True, "has_audio": True}},
                aspect="9:16", mode="auto", crop_path=dual,
                punch_in_zoom=True,
                watermark={"enabled": True, "asset_id": "wm1", "position": "bottom-left", "scale": 0.15, "opacity": 0.8, "margin": 20},
            )
            self.assertIn("split=2[_ds_in1][_ds_in2]", fc2)
            self.assertIn("overlay=20:H-h-20", fc2)
            self.assertIn("ass=filename=", fc2)

            # 3. audio_only + bgm + ASS
            fc3 = _run_graph(
                {"default": {"width": 0, "height": 0, "duration": 20.0, "has_video": False, "has_audio": True}},
                aspect="9:16", mode="auto",
                bgm={"enabled": True, "track_id": "b1", "volume_db": -16.0, "ducking": True, "duck_db": -22.0},
            )
            self.assertIn("color=c=#0f0e16:s=1080x1920", fc3)
            self.assertIn("sidechaincompress", fc3)
            self.assertIn("ass=filename=", fc3)


if __name__ == "__main__":
    unittest.main()
