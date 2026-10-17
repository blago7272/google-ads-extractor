from __future__ import annotations

import json
import os
import unittest
import urllib.error
from unittest import mock

from orchestration import ops_telegram
from orchestration.release_orchestrator import ReleaseStepFailed, main

TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "123:secret-token", "TELEGRAM_CHAT_ID": "1945218457"}


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return b'{"ok": true}'


class SendOpsMessageTest(unittest.TestCase):
    def test_posts_the_text_to_the_ops_chat(self) -> None:
        with mock.patch.dict(os.environ, TELEGRAM_ENV), mock.patch(
            "orchestration.ops_telegram.urllib.request.urlopen", return_value=_FakeResponse()
        ) as urlopen:
            self.assertTrue(ops_telegram.send_ops_message("hello"))

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/bot123:secret-token/sendMessage")
        self.assertEqual(json.loads(request.data)["chat_id"], "1945218457")
        self.assertEqual(json.loads(request.data)["text"], "hello")

    def test_without_credentials_it_skips(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "orchestration.ops_telegram.urllib.request.urlopen"
        ) as urlopen:
            self.assertFalse(ops_telegram.send_ops_message("hello"))
        urlopen.assert_not_called()

    def test_a_telegram_error_never_raises_or_leaks_the_token(self) -> None:
        error = urllib.error.URLError("boom for https://api.telegram.org/bot123:secret-token/sendMessage")
        with mock.patch.dict(os.environ, TELEGRAM_ENV), mock.patch(
            "orchestration.ops_telegram.urllib.request.urlopen", side_effect=error
        ), mock.patch("orchestration.ops_telegram.emit_log") as emit_log:
            self.assertFalse(ops_telegram.send_ops_message("hello"))

        logged = emit_log.call_args.kwargs["error_message"]
        self.assertNotIn("secret-token", logged)


class ReleaseFailureAlertTest(unittest.TestCase):
    def _run_main(self, side_effect: BaseException) -> tuple[int, list[str]]:
        sent: list[str] = []
        with mock.patch(
            "orchestration.release_orchestrator.run_release", side_effect=side_effect
        ), mock.patch(
            "orchestration.ops_telegram.send_ops_message",
            side_effect=lambda text, **_kw: sent.append(text) or True,
        ), mock.patch.dict(os.environ, {"CLOUD_RUN_EXECUTION": "reporting-release-orchestrator-abcde"}):
            code = main([])
        return code, sent

    def test_a_failed_step_alerts_the_ops_chat(self) -> None:
        code, sent = self._run_main(ReleaseStepFailed("ecb_fx_refresh", "504 Gateway Time-out"))

        self.assertEqual(code, 1)
        self.assertEqual(len(sent), 1)
        self.assertIn("FAILED", sent[0])
        self.assertIn("Step: ecb_fx_refresh", sent[0])
        self.assertIn("504 Gateway Time-out", sent[0])
        self.assertIn("reporting-release-orchestrator-abcde", sent[0])

    def test_an_unexpected_exception_alerts_the_ops_chat(self) -> None:
        code, sent = self._run_main(KeyError("missing_setting"))

        self.assertEqual(code, 1)
        self.assertIn("Error type: KeyError", sent[0])

    def test_invalid_arguments_alert_before_exiting(self) -> None:
        sent: list[str] = []
        with mock.patch(
            "orchestration.ops_telegram.send_ops_message",
            side_effect=lambda text, **_kw: sent.append(text) or True,
        ), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                main(["--no-such-flag"])

        self.assertIn("Step: argument_parsing", sent[0])


if __name__ == "__main__":
    unittest.main()
