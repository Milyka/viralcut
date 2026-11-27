"""Regression tests for KrlzCut v2.1.2 bot concurrency & lifecycle hardening."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import types
import unittest
from unittest import mock

from viralcut import bot_notify


class TestBotConcurrencyV212(unittest.TestCase):
    def setUp(self) -> None:
        self._reset_bot_state()

    def tearDown(self) -> None:
        bot_notify.stop_bots(shutdown=False)
        self._reset_bot_state()

    def _reset_bot_state(self) -> None:
        bot_notify._SHUTDOWN_EVENT.clear()
        with bot_notify._STATE_LOCK:
            bot_notify._TG_THREAD = None
            bot_notify._TG_STOP = None
            bot_notify._TG_ACTIVE_HASH = ""
            bot_notify._DC_THREAD = None
            bot_notify._DC_STOP = None
            bot_notify._DC_ACTIVE_HASH = ""
            bot_notify._TG_OFFSET = 0
            bot_notify._TG_TOKEN_HASH = ""
            bot_notify._SEEN_UPDATES.clear()
            bot_notify._STATUS["telegram"] = {"running": False, "last_error": "", "bot_username": ""}
            bot_notify._STATUS["discord"] = {"running": False, "last_error": "", "bot_username": ""}

    def test_discord_gateway_reads_heartbeat_ack_while_interaction_blocks(self) -> None:
        interaction_started = threading.Event()
        release_interaction = threading.Event()
        ack_seen_while_blocked = {"value": False}

        def _slow_interaction(_payload, _conf) -> bool:
            interaction_started.set()
            release_interaction.wait(timeout=3.0)
            return True

        class _FakeWs:
            def __init__(self) -> None:
                self._step = 0
                self.sent = []

            async def send(self, data: str) -> None:
                self.sent.append(json.loads(data))

            async def close(self) -> None:
                return None

            async def recv(self) -> str:
                self._step += 1
                if self._step == 1:
                    return json.dumps({"op": 10, "d": {"heartbeat_interval": 41250}})
                if self._step == 2:
                    return json.dumps({
                        "op": 0,
                        "s": 1,
                        "t": "INTERACTION_CREATE",
                        "d": {"type": 3, "id": "inter_1"},
                    })
                if self._step == 3:
                    # Wait briefly until the worker thread starts, then confirm we still read OP 11
                    for _ in range(50):
                        if interaction_started.is_set():
                            break
                        await asyncio.sleep(0.01)
                    ack_seen_while_blocked["value"] = (
                        interaction_started.is_set() and not release_interaction.is_set()
                    )
                    return json.dumps({"op": 11})
                release_interaction.set()
                return json.dumps({"op": 7})

        class _FakeConnect:
            def __init__(self, ws: _FakeWs) -> None:
                self._ws = ws

            async def __aenter__(self) -> _FakeWs:
                return self._ws

            async def __aexit__(self, *_a) -> bool:
                return False

        fake_ws = _FakeWs()
        fake_mod = types.ModuleType("websockets")
        fake_mod.connect = lambda *_a, **_kw: _FakeConnect(fake_ws)  # type: ignore[attr-defined]

        stop_evt = threading.Event()
        with mock.patch.dict(sys.modules, {"websockets": fake_mod}), \
             mock.patch.object(bot_notify.app_settings, "get", return_value={"dc_allowed_users": "42"}), \
             mock.patch.object(bot_notify, "process_discord_interaction", side_effect=_slow_interaction):
            asyncio.run(bot_notify._dc_gateway_session("DC_TOK", stop_evt))

        self.assertTrue(interaction_started.is_set())
        self.assertTrue(ack_seen_while_blocked["value"])

    def test_restart_bots_skips_unchanged_telegram_and_respawns_on_token_change(self) -> None:
        conf_box = {"conf": {"tg_enabled": True, "tg_token": "111:AAA", "tg_allowed_users": "1", "dc_enabled": False}}

        def _fake_tg_loop(stop_evt: threading.Event) -> None:
            stop_evt.wait(5.0)

        with mock.patch.object(bot_notify.app_settings, "get", side_effect=lambda: dict(conf_box["conf"])), \
             mock.patch.object(bot_notify, "_tg_poll_loop", side_effect=_fake_tg_loop):
            bot_notify.start_bots()
            t1 = bot_notify._TG_THREAD
            s1 = bot_notify._TG_STOP
            self.assertIsNotNone(t1)
            self.assertIsNotNone(s1)

            # Updating non-token setting must NOT restart Telegram poller
            conf_box["conf"]["tg_allowed_users"] = "1, 2"
            bot_notify.restart_bots()
            self.assertIs(bot_notify._TG_THREAD, t1)
            self.assertFalse(s1.is_set())

            # Changing token MUST stop old poller and spawn a new one
            conf_box["conf"]["tg_token"] = "222:BBB"
            bot_notify.restart_bots()
            self.assertTrue(s1.is_set())
            self.assertIsNot(bot_notify._TG_THREAD, t1)
            self.assertIsNot(bot_notify._TG_STOP, s1)

            # Disabling Telegram MUST stop the running poller cleanly
            s2 = bot_notify._TG_STOP
            conf_box["conf"]["tg_enabled"] = False
            bot_notify.restart_bots()
            self.assertTrue(s2.is_set())

    def test_superseded_tg_poller_skips_updates_and_preserves_new_status(self) -> None:
        stop_old = threading.Event()
        stop_new = threading.Event()
        with bot_notify._STATE_LOCK:
            bot_notify._TG_STOP = stop_old

        def _fake_http(url: str, **_kw):
            if "deleteWebhook" in url:
                return {"ok": True}
            # Simulate restart happening while getUpdates is blocked in-flight
            with bot_notify._STATE_LOCK:
                bot_notify._TG_STOP = stop_new
            stop_old.set()
            return {"ok": True, "result": [{"update_id": 55, "message": {"text": "/status"}}]}

        with mock.patch.object(
            bot_notify.app_settings, "get",
            return_value={"tg_enabled": True, "tg_token": "111:AAA", "tg_allowed_users": "777"},
        ), \
             mock.patch.object(bot_notify, "_http_json", side_effect=_fake_http), \
             mock.patch.object(bot_notify, "process_telegram_update") as proc_mock:
            bot_notify._tg_poll_loop(stop_old)

        proc_mock.assert_not_called()
        self.assertEqual(bot_notify._TG_OFFSET, 0)

        # Superseded thread error must NOT overwrite new thread's clean last_error
        stop_stale = threading.Event()
        with bot_notify._STATE_LOCK:
            bot_notify._TG_STOP = stop_stale
            bot_notify._STATUS["telegram"]["last_error"] = ""

        def _failing_http(url: str, **_kw):
            if "deleteWebhook" in url:
                return {"ok": True}
            with bot_notify._STATE_LOCK:
                bot_notify._TG_STOP = stop_new
            raise RuntimeError("stale poller failed")

        with mock.patch.object(
            bot_notify.app_settings, "get",
            return_value={"tg_enabled": True, "tg_token": "111:AAA", "tg_allowed_users": "777"},
        ), \
             mock.patch.object(bot_notify, "_http_json", side_effect=_failing_http):
            bot_notify._tg_poll_loop(stop_stale)

        self.assertEqual(bot_notify._STATUS["telegram"]["last_error"], "")

    def test_tg_poll_loop_rereads_settings_after_get_updates_returns(self) -> None:
        stop_evt = threading.Event()
        with bot_notify._STATE_LOCK:
            bot_notify._TG_STOP = stop_evt

        conf_state = {"allowed": "777"}
        poll_calls = {"n": 0}

        def _fake_get_settings():
            return {
                "tg_enabled": True,
                "tg_token": "111:AAA",
                "tg_allowed_users": conf_state["allowed"],
                "tg_chat_id": "777",
            }

        def _fake_http(url: str, **_kw):
            if "deleteWebhook" in url:
                return {"ok": True}
            poll_calls["n"] += 1
            if poll_calls["n"] == 1:
                # User 777 is removed from allowlist while getUpdates is in flight
                conf_state["allowed"] = ""
                return {
                    "ok": True,
                    "result": [{
                        "update_id": 10,
                        "callback_query": {
                            "id": "cb1",
                            "from": {"id": 777, "username": "owner"},
                            "data": "approve:clip1",
                        },
                    }],
                }
            stop_evt.set()
            return {"ok": True, "result": []}

        with mock.patch.object(bot_notify.app_settings, "get", side_effect=_fake_get_settings), \
             mock.patch.object(bot_notify, "_http_json", side_effect=_fake_http), \
             mock.patch.object(bot_notify, "handle_clip_action") as act_mock:
            bot_notify._tg_poll_loop(stop_evt)

        act_mock.assert_not_called()

    def test_watch_rerender_aborts_immediately_on_shutdown(self) -> None:
        timer = threading.Timer(0.05, lambda: bot_notify.stop_bots(shutdown=True))
        timer.start()
        started = time.monotonic()
        try:
            with mock.patch.object(bot_notify, "notify_clip_ready") as notify_mock:
                result = bot_notify._watch_rerender_and_push(
                    "clip_1", prev_updated_at=100.0, poll_interval=5.0, timeout=30.0
                )
        finally:
            timer.cancel()
        elapsed = time.monotonic() - started
        self.assertFalse(result)
        self.assertLess(elapsed, 1.0)
        notify_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
