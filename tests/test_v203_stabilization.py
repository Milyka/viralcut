"""Regression tests for KrlzCut v2.0.3 stabilization fixes."""
from __future__ import annotations

import concurrent.futures
import re
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from viralcut import (
    ai,
    assistant_actions,
    db,
    game_layer,
    jobs,
    live,
    main,
    pipeline,
    render,
    settings,
    transcribe,
)


class TestSecurityGuardMiddleware(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_patch = mock.patch.object(db, "DB_PATH", Path(self._tmp.name) / "test.db")
        self._db_patch.start()
        db.init_db()
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        self._db_patch.stop()
        self._tmp.cleanup()

    def test_rejects_non_loopback_host(self) -> None:
        resp = self.client.get("/api/health", headers={"Host": "evil.example:8765"})
        self.assertEqual(resp.status_code, 403)

    def test_allows_health_without_token(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)

    def test_rejects_cross_site_and_foreign_origin_on_mutations(self) -> None:
        tok = main._SESSION_TOKEN
        resp_sfs = self.client.post(
            "/api/settings",
            json={"power": 60},
            headers={"X-Krlz-Token": tok, "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(resp_sfs.status_code, 403)

        resp_origin = self.client.post(
            "/api/settings",
            json={"power": 60},
            headers={"X-Krlz-Token": tok, "Origin": "https://evil.example"},
        )
        self.assertEqual(resp_origin.status_code, 403)

    def test_requires_session_token_from_index_html_for_mutations(self) -> None:
        resp_missing = self.client.post("/api/settings", json={"power": 60})
        self.assertEqual(resp_missing.status_code, 403)

        resp_wrong = self.client.post(
            "/api/settings",
            json={"power": 60},
            headers={"X-Krlz-Token": "wrong-token"},
        )
        self.assertEqual(resp_wrong.status_code, 403)

        html_resp = self.client.get("/")
        self.assertEqual(html_resp.status_code, 200)
        match = re.search(r'<meta\s+name="krlz-token"\s+content="([^"]+)"', html_resp.text)
        self.assertIsNotNone(match)
        token = match.group(1)
        self.assertEqual(token, main._SESSION_TOKEN)

        cfg = Path(self._tmp.name) / "settings.json"
        with mock.patch.object(settings, "SETTINGS_FILE", cfg), \
             mock.patch.object(render, "hw_encoder", return_value=None):
            resp_ok = self.client.post(
                "/api/settings",
                json={"power": 65},
                headers={"X-Krlz-Token": token},
            )
        self.assertEqual(resp_ok.status_code, 200)
        self.assertEqual(resp_ok.json().get("power"), 65)


class TestSsrfValidation(unittest.TestCase):
    def test_local_server_rejects_file_and_remote_hosts(self) -> None:
        self.assertFalse(ai.local_server("file:///etc/passwd")["available"])
        self.assertFalse(ai.local_server("http://example.com:11434/v1")["available"])
        self.assertFalse(ai.local_server("https://127.0.0.1:11434/v1")["available"])

    def test_settings_update_rejects_non_http_ai_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with mock.patch.object(settings, "SETTINGS_FILE", cfg):
                with self.assertRaises(ValueError):
                    settings.update({"ai_base": "file:///etc/passwd"})
                with self.assertRaises(ValueError):
                    settings.update({"ai_base": "ftp://127.0.0.1/v1"})
                updated = settings.update({"ai_base": "http://127.0.0.1:11434/v1"})
                self.assertEqual(updated["ai_base"], "http://127.0.0.1:11434/v1")


class TestStorageAndCleanup(unittest.TestCase):
    def test_stats_and_cleanup_handle_krlzcut_zip_and_strips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            proj_root = data_dir / "projects"
            pdir = proj_root / "p1"
            strips_dir = pdir / "strips"
            strips_dir.mkdir(parents=True, exist_ok=True)
            zip_file = pdir / "krlzcut_export.zip"
            zip_file.write_bytes(b"Z" * 2048)
            strip_file = strips_dir / "c1_0_10.jpg"
            strip_file.write_bytes(b"J" * 4096)

            with mock.patch.object(
                pipeline.db, "list_projects",
                return_value=[{"id": "p1", "status": "done", "source": ""}],
            ):
                stats = pipeline.storage_stats(data_dir=data_dir, projects_dir=proj_root)
                self.assertGreaterEqual(stats["temp_bytes"], 2048 + 4096)

                res = pipeline.cleanup_storage(
                    include_sources=False, data_dir=data_dir, projects_dir=proj_root
                )
                self.assertGreaterEqual(res["freed_bytes"], 2048 + 4096)
                self.assertFalse(zip_file.exists())
                self.assertFalse(strips_dir.exists())


class TestGameLayerDisableAndRender(unittest.TestCase):
    def test_clean_clip_edit_preserves_explicit_game_layer_disable(self) -> None:
        cleaned = main._clean_clip_edit(main.ClipEdit(game_layer={"enabled": False}))
        self.assertIn("game_layer", cleaned)
        self.assertIsNone(cleaned["game_layer"])

    def test_apply_style_to_project_allows_clearing_game_layer(self) -> None:
        saved_options = {}
        queued_patches = []
        proj = {
            "id": "p1",
            "options": {"game_layer": {"enabled": True, "clip_id": "builtin_neon_waves"}, "sub_free": {"x": 0.5, "y": 0.5}},
            "source": "",
        }
        clip = {
            "id": "c1",
            "project_id": "p1",
            "status": "ready",
            "settings": {"game_layer": {"enabled": True, "clip_id": "builtin_neon_waves"}},
        }

        def _fake_update_project(pid, **fields):
            saved_options.update(fields.get("options") or {})

        def _fake_submit(cid, patch):
            queued_patches.append((cid, patch))
            return True

        with mock.patch.object(pipeline.db, "get_project", return_value=proj), \
             mock.patch.object(pipeline.db, "update_project", side_effect=_fake_update_project), \
             mock.patch.object(pipeline.db, "list_clips", return_value=[clip]), \
             mock.patch.object(jobs, "submit_rerender", side_effect=_fake_submit):
            res = pipeline.apply_style_to_project("p1", {"game_layer": None, "sub_free": None})

        self.assertTrue(res["ok"])
        self.assertEqual(res["clips"], 1)
        self.assertIsNone(saved_options.get("game_layer"))
        self.assertIsNone(saved_options.get("sub_free"))
        self.assertEqual(len(queued_patches), 1)
        self.assertIn("game_layer", queued_patches[0][1])
        self.assertIsNone(queued_patches[0][1]["game_layer"])

    def test_ensure_builtin_is_thread_safe_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bdir = Path(tmp) / "builtin"
            spec = game_layer.BUILTIN_LOOPS[0]
            call_count = 0
            lock = threading.Lock()

            def _fake_run(cmd, **kwargs):
                nonlocal call_count
                with lock:
                    call_count += 1
                time.sleep(0.05)
                out_path = Path(cmd[-1])
                out_path.write_bytes(b"MP4" * 4096)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(game_layer, "GAME_DIR", bdir), \
                 mock.patch.object(game_layer.utils, "run", side_effect=_fake_run):
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    paths = list(pool.map(lambda _: game_layer._ensure_builtin(spec), range(4)))

            self.assertEqual(call_count, 1)
            self.assertTrue(all(p is not None and p.is_file() for p in paths))
            self.assertEqual(len(set(paths)), 1)

    def test_render_wraps_game_start_modulo_and_normalizes_vstack_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            game = root / "game.mp4"
            out = root / "out.mp4"
            src.write_bytes(b"0" * 64)
            game.write_bytes(b"0" * 64)
            captured_cmds = []

            def _fake_probe(path):
                if Path(path) == game:
                    return {"width": 1080, "height": 1920, "duration": 8.0, "has_audio": False, "has_video": True}
                return {"width": 1920, "height": 1080, "duration": 60.0, "has_audio": True, "has_video": True}

            def _fake_encode(cmd, duration, on_progress=None):
                captured_cmds.append(cmd)
                Path(cmd[-1]).write_bytes(b"0" * 20000)
                return 0, [], None

            with mock.patch.object(render, "probe", side_effect=_fake_probe), \
                 mock.patch.object(render, "_run_encode", side_effect=_fake_encode), \
                 mock.patch.object(render, "hw_encoder", return_value=None), \
                 mock.patch.object(game_layer, "resolve_path", return_value=game):
                render.render_clip(
                    src, 0.0, 12.0, out,
                    mode="crop", aspect="9:16",
                    game_layer={
                        "enabled": True,
                        "clip_id": "builtin_neon_waves",
                        "split": "50/50",
                        "start": 10.5,
                        "top_zoom": 1.0,
                        "game_zoom": 1.0,
                        "audio": False,
                    },
                )

            self.assertTrue(captured_cmds)
            cmd = captured_cmds[0]
            # 10.5 % 8.0 == 2.5
            ss_indices = [i for i, tok in enumerate(cmd) if tok == "-ss"]
            self.assertGreaterEqual(len(ss_indices), 2)
            self.assertAlmostEqual(float(cmd[ss_indices[1] + 1]), 2.5, places=2)
            fc = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("fps=30,setsar=1,setpts=PTS-STARTPTS[_topn]", fc)
            self.assertIn("fps=30,setsar=1,setpts=PTS-STARTPTS[_botn]", fc)
            self.assertIn("[_topn][_botn]vstack=inputs=2", fc)

    def test_hw_args_differentiates_quality_presets(self) -> None:
        nv_fast = render._hw_args("h264_nvenc", 23, "fast")
        nv_bal = render._hw_args("h264_nvenc", 23, "balanced")
        nv_high = render._hw_args("h264_nvenc", 23, "high")
        self.assertNotEqual(nv_fast, nv_bal)
        self.assertNotEqual(nv_bal, nv_high)
        self.assertIn("p3", nv_fast)
        self.assertIn("p6", nv_high)

        vt_fast = render._hw_args("h264_videotoolbox", 23, "fast")
        vt_high = render._hw_args("h264_videotoolbox", 23, "high")
        self.assertIn("65", vt_fast)
        self.assertIn("82", vt_high)


class TestLiveEvenDbWhisperAndAssistant(unittest.TestCase):
    def test_live_settings_preserves_v2_fields_and_even_segments_capped(self) -> None:
        cfg = live._settings({
            "sub_anim": "bounce",
            "sub_outline": False,
            "sub_outline_width": 9,
            "sub_outline_color": "#112233",
            "game_layer": {"enabled": True, "clip_id": "builtin_neon_waves", "start": 3.0},
        })
        self.assertEqual(cfg["sub_anim"], "bounce")
        self.assertFalse(cfg["sub_outline"])
        self.assertEqual(cfg["sub_outline_width"], 9)
        self.assertEqual(cfg["sub_outline_color"], "#112233")
        self.assertIsNotNone(cfg["game_layer"])

        segs = pipeline._even_segments(36000.0, 10.0, 0)
        self.assertEqual(len(segs), pipeline.MAX_EVEN_CLIPS)

    def test_db_clip_summaries_by_project_single_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with mock.patch.object(db, "DB_PATH", db_path):
                db.init_db()
                p1 = db.create_project("https://example.com/1", {})
                p2 = db.create_project("https://example.com/2", {})
                c1 = db.add_clip(p1["id"], 1, 0, 10, 80, "A", "", "", [], {}, status="ready")
                db.update_clip(c1["id"], thumb="/tmp/t1.jpg")
                c2 = db.add_clip(p1["id"], 2, 10, 20, 70, "B", "", "", [], {}, status="queued")
                db.update_clip(c2["id"], thumb="/tmp/t2.jpg")
                c3 = db.add_clip(p2["id"], 1, 0, 10, 60, "C", "", "", [], {}, status="ready")
                db.update_clip(c3["id"], thumb="/tmp/t3.jpg")
                summaries = db.clip_summaries_by_project()
            self.assertEqual(summaries[p1["id"]]["total_clips"], 2)
            self.assertEqual(summaries[p1["id"]]["ready_clips"], 1)
            self.assertEqual(summaries[p1["id"]]["thumb"], "/tmp/t1.jpg")
            self.assertEqual(summaries[p2["id"]]["total_clips"], 1)
            self.assertEqual(summaries[p2["id"]]["thumb"], "/tmp/t3.jpg")

    def test_whisper_delete_model_blocks_during_download_or_active_transcribe(self) -> None:
        with mock.patch.dict(transcribe._MODEL_DOWNLOADS, {"medium": {"downloading": True, "error": ""}}, clear=False):
            with self.assertRaises(RuntimeError):
                transcribe.delete_model("medium")

        with mock.patch.object(transcribe, "_ACTIVE_TRANSCRIBES", 1), \
             mock.patch.object(transcribe, "_ACTIVE_MODEL_KEY", "medium"):
            with self.assertRaises(RuntimeError):
                transcribe.delete_model("medium")

    def test_assistant_style_fields_v2_support(self) -> None:
        fields = assistant_actions._style_fields({
            "accent": "#0EA5E9",
            "sub_position": "center",
            "sub_anim": "slide",
            "sub_outline": False,
            "sub_outline_width": 8,
            "sub_outline_color": "#111111",
            "cut_mode": "even",
            "ai_preset": "insights",
        })
        self.assertEqual(fields["accent"], "#0EA5E9")
        self.assertEqual(fields["sub_position"], "middle")
        self.assertEqual(fields["sub_anim"], "slide")
        self.assertFalse(fields["sub_outline"])
        self.assertEqual(fields["sub_outline_width"], 8)
        self.assertEqual(fields["sub_outline_color"], "#111111")
        self.assertEqual(fields["cut_mode"], "even")
        self.assertEqual(fields["ai_preset"], "insights")


if __name__ == "__main__":
    unittest.main()
