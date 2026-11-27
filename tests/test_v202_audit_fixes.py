"""Targeted regression tests for KrlzCut v2.0.2 audit fixes."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from viralcut import ai, game_layer, main, render, subtitles, utils


class TestGameLayerNormalize(unittest.TestCase):
    def test_accepts_canonical_and_legacy_fields_and_clamps_zoom_2_5(self) -> None:
        canonical = game_layer.normalize_config({
            "enabled": True,
            "clip_id": "builtin_neon_waves",
            "split": "65/35",
            "start": 12.5,
            "top_zoom": 2.4,
            "game_zoom": 3.5,
            "audio": True,
        })
        assert canonical is not None
        self.assertEqual(canonical["start"], 12.5)
        self.assertTrue(canonical["audio"])
        self.assertEqual(canonical["top_zoom"], 2.4)
        self.assertEqual(canonical["game_zoom"], 2.5)

        legacy = game_layer.normalize_config({
            "enabled": True,
            "start_offset": 7.25,
            "game_audio": True,
            "top_zoom": 2.5,
        })
        assert legacy is not None
        self.assertEqual(legacy["start"], 7.2)
        self.assertTrue(legacy["audio"])
        self.assertEqual(legacy["top_zoom"], 2.5)


class TestCleanClipEdit(unittest.TestCase):
    def test_normalizes_center_to_middle_and_accepts_middle(self) -> None:
        cleaned = main._clean_clip_edit(main.ClipEdit(sub_position="center"))
        self.assertEqual(cleaned["sub_position"], "middle")

        cleaned2 = main._clean_clip_edit(main.ClipEdit(sub_position="middle"))
        self.assertEqual(cleaned2["sub_position"], "middle")

    def test_rejects_unknown_position(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            main._clean_clip_edit(main.ClipEdit(sub_position="invalid_pos"))
        self.assertEqual(ctx.exception.status_code, 400)


class TestEnrichProjectThumbUrl(unittest.TestCase):
    def test_computes_real_relative_thumbs_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid = "proj123"
            thumb = root / pid / "thumbs" / "clip01.jpg"
            thumb.parent.mkdir(parents=True, exist_ok=True)
            thumb.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
            with mock.patch.object(main, "PROJECTS_DIR", root), \
                 mock.patch.object(main.db, "list_clips", return_value=[{"status": "ready", "thumb": str(thumb), "path": ""}]):
                enriched = main._enrich_project({"id": pid, "source": ""})
            self.assertEqual(enriched["thumb_url"], f"/media/{pid}/thumbs/clip01.jpg")


class TestProbeAttachedPic(unittest.TestCase):
    def test_ignores_cover_art_attached_pic_stream(self) -> None:
        fake_stderr = "\n".join([
            "Input #0, mp3, from 'podcast.mp3':",
            "  Duration: 00:05:12.40, start: 0.025057, bitrate: 192 kb/s",
            "  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 192 kb/s",
            "  Stream #0:1: Video: mjpeg (Baseline), yuvj444p(pc), 1400x1400 [SAR 1:1 DAR 1:1], 90k tbr, 90k tbn (attached pic)",
        ])
        proc = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stdout="", stderr=fake_stderr)
        with mock.patch.object(utils, "run", return_value=proc):
            info = utils.probe(Path("podcast.mp3"))
        self.assertFalse(info["has_video"])
        self.assertEqual(info["width"], 0)
        self.assertEqual(info["height"], 0)
        self.assertTrue(info["has_audio"])
        self.assertAlmostEqual(info["duration"], 312.4, places=1)


class TestAiModelsKeyProtection(unittest.TestCase):
    def test_strips_saved_key_on_foreign_base_url_and_blocks_override_for_cloud_provider(self) -> None:
        ai._MODELS_CACHE.update({"ts": 0.0, "base": "", "data": []})
        captured_headers = {}

        class _FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *_a):
                return False
            def read(self):
                return json.dumps({"data": [{"id": "m1", "type": "chat"}]}).encode("utf-8")

        def _fake_urlopen(req, timeout=20):
            captured_headers["url"] = req.full_url
            captured_headers["auth"] = req.get_header("Authorization")
            return _FakeResp()

        # 1. Custom provider with foreign override_base must strip Authorization header
        with mock.patch.object(ai, "_conf", return_value={"provider": "custom", "base": "https://saved.example/v1", "model": "m1", "label": "Custom", "key_url": ""}), \
             mock.patch.object(ai, "key", return_value="sk-secret-token"), \
             mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            res = ai.models(force=True, base_url="https://attacker.evil/v1")
        self.assertEqual(res["base"], "https://attacker.evil/v1")
        self.assertIsNone(captured_headers["auth"])

        # 2. Same origin on custom provider keeps Authorization header
        captured_headers.clear()
        with mock.patch.object(ai, "_conf", return_value={"provider": "custom", "base": "https://saved.example/v1", "model": "m1", "label": "Custom", "key_url": ""}), \
             mock.patch.object(ai, "key", return_value="sk-secret-token"), \
             mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            res2 = ai.models(force=True, base_url="https://saved.example/v2")
        self.assertEqual(res2["base"], "https://saved.example/v2")
        self.assertEqual(captured_headers["auth"], "Bearer sk-secret-token")

        # 3. Cloud provider (deepseek) must ignore unsaved override_base completely
        captured_headers.clear()
        with mock.patch.object(ai, "_conf", return_value={"provider": "deepseek", "base": "https://api.deepseek.com/v1", "model": "deepseek-chat", "label": "DeepSeek", "key_url": ""}), \
             mock.patch.object(ai, "key", return_value="sk-ds-secret"), \
             mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            res3 = ai.models(force=True, base_url="https://attacker.evil/v1")
        self.assertEqual(res3["base"], "https://api.deepseek.com/v1")
        self.assertTrue(captured_headers["url"].startswith("https://api.deepseek.com/v1/"))


class TestRenderWindowsGpuFallback(unittest.TestCase):
    def _run_render(self, *, encoder_mode: str, hw: str | None, alt_hw: str | None,
                    fail_encoders: set[str | None]) -> tuple[list[str | None], dict | None]:
        tried: list[str | None] = []
        render._fallback_notice = None
        render._last_fallback = 0.0

        def _fake_encode(cmd, duration, on_progress):
            # Extract codec after -c:v
            idx = cmd.index("-c:v")
            enc = cmd[idx + 1]
            enc_key = None if enc == "libx264" else enc
            tried.append(enc_key)
            if enc_key in fail_encoders:
                return 1, ["encode error\n"], None
            out = Path(cmd[-1])
            out.write_bytes(b"0" * 12000)
            return 0, [], None

        def _fake_find_hw(excluded=()):
            if alt_hw and alt_hw not in excluded:
                return alt_hw
            return None

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            src.write_bytes(b"0" * 2048)
            out = Path(tmp) / "out.mp4"
            probe_info = {"duration": 10.0, "width": 1280, "height": 720, "fps": 30.0, "has_audio": False, "has_video": True}
            with mock.patch.object(render.sys, "platform", "win32"), \
                 mock.patch.object(render, "probe", return_value=probe_info), \
                 mock.patch.object(render, "_encoder_mode", return_value=encoder_mode), \
                 mock.patch.object(render, "hw_encoder", return_value=hw), \
                 mock.patch.object(render, "_find_hw_encoder", side_effect=_fake_find_hw), \
                 mock.patch.object(render, "_run_encode", side_effect=_fake_encode):
                render.render_clip(src, 0.0, 5.0, out, aspect="9:16", mode="crop")
        return tried, render.cpu_fallback_notice()

    def test_windows_gpu_notifies_when_no_hardware_passes_probe(self) -> None:
        tried, notice = self._run_render(encoder_mode="gpu", hw=None, alt_hw=None, fail_encoders=set())
        self.assertEqual(tried, [None])
        assert notice is not None
        self.assertEqual(notice["reason"], "gpu_unavailable")

        # In auto mode, no hardware passing probe should NOT trigger error toast notice
        tried_auto, notice_auto = self._run_render(encoder_mode="auto", hw=None, alt_hw=None, fail_encoders=set())
        self.assertEqual(tried_auto, [None])
        self.assertIsNone(notice_auto)

    def test_windows_gpu_tries_other_hardware_before_notifying_about_cpu(self) -> None:
        tried, notice = self._run_render(
            encoder_mode="gpu", hw="h264_nvenc", alt_hw="h264_qsv",
            fail_encoders={"h264_nvenc", "h264_qsv"},
        )
        self.assertEqual(tried, ["h264_nvenc", "h264_qsv", None])
        assert notice is not None
        self.assertEqual(notice["reason"], "gpu_failed")

        # In auto mode, tries alternative GPU then CPU silently without firing gpu_failed toast
        tried_auto, notice_auto = self._run_render(
            encoder_mode="auto", hw="h264_nvenc", alt_hw="h264_qsv",
            fail_encoders={"h264_nvenc", "h264_qsv"},
        )
        self.assertEqual(tried_auto, ["h264_nvenc", "h264_qsv", None])
        self.assertIsNone(notice_auto)


class TestSplitScreenSubtitleAnchor(unittest.TestCase):
    def test_bottom_subtitles_anchor_at_split_boundary(self) -> None:
        words = [{"word": "Привет", "start": 0.2, "end": 0.8}]
        ass = subtitles.build_ass(
            words, 0.0, 2.0, position="bottom", aspect="9:16", split_ratio=0.60,
        )
        # 1920 * 0.60 = 1152
        self.assertIn(r"\an5\pos(540,1152)", ass)


if __name__ == "__main__":
    unittest.main()
