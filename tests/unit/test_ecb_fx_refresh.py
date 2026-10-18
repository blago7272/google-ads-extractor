from __future__ import annotations

from datetime import date, timedelta
import unittest
from unittest import mock

import requests

from orchestration.ecb_fx_refresh import (
    EcbFetchFailed,
    EcbFxRefreshConfig,
    resolve_refresh_window,
    run_ecb_fx_refresh,
)


TODAY = date(2026, 8, 2)


class ResolveRefreshWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EcbFxRefreshConfig()

    def _window(self, latest_loaded: date | None):
        return resolve_refresh_window(latest_loaded, TODAY, self.config)

    def test_steady_state_keeps_the_fixed_lookback(self) -> None:
        # Watermark is current, so the fixed lookback still governs and recent
        # days are re-fetched in case the ECB published late.
        window = self._window(date(2026, 8, 1))

        self.assertEqual(window.start_date, date(2026, 7, 26))  # TODAY - 7
        self.assertEqual(window.reason, "steady_state")
        self.assertFalse(window.capped)

    def test_short_gap_still_uses_the_lookback_floor(self) -> None:
        # A 3-day-old watermark is already inside the 7-day lookback.
        window = self._window(date(2026, 7, 30))

        self.assertEqual(window.start_date, date(2026, 7, 26))
        self.assertEqual(window.reason, "steady_state")

    def test_long_gap_reaches_back_to_the_watermark(self) -> None:
        # The real incident: pipeline frozen, watermark stuck at 2026-06-08.
        # A fixed today-7 window would never recover those dates.
        window = self._window(date(2026, 6, 8))

        self.assertEqual(window.start_date, date(2026, 6, 6))  # watermark - 2 overlap
        self.assertEqual(window.reason, "watermark_catchup")
        self.assertFalse(window.capped)
        self.assertGreater((TODAY - window.start_date).days, self.config.lookback_days)

    def test_gap_of_any_length_self_heals_up_to_the_cap(self) -> None:
        window = self._window(date(2026, 1, 5))

        self.assertEqual(window.start_date, date(2026, 1, 3))
        self.assertEqual(window.reason, "watermark_catchup")

    def test_absurd_watermark_is_capped_not_trusted(self) -> None:
        window = self._window(date(1999, 1, 4))

        self.assertTrue(window.capped)
        self.assertEqual(window.reason, "catchup_capped")
        self.assertEqual((TODAY - window.start_date).days, self.config.max_catchup_days)

    def test_empty_table_falls_back_to_the_lookback(self) -> None:
        # A daily job must not try to seed all history; that is the backfill
        # script's job.
        window = self._window(None)

        self.assertEqual(window.start_date, date(2026, 7, 26))
        self.assertEqual(window.reason, "no_existing_rows")

    def test_end_date_is_always_today(self) -> None:
        for latest in (None, date(2026, 8, 1), date(2026, 6, 8), date(1999, 1, 4)):
            self.assertEqual(self._window(latest).end_date, TODAY)


ECB_CSV = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-10-16,1.1000\n"
)


def _response(status: int, text: str = "") -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode("utf-8")
    resp.url = "https://data-api.ecb.europa.eu/test"
    return resp


class _FakeJob:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def result(self):
        return self._rows


class _FakeBigQuery:
    """Answers the watermark query; records DELETEs and loads instead of running them."""

    def __init__(self, latest_loaded: date | None):
        self.latest_loaded = latest_loaded
        self.deletes = 0
        self.loads = 0

    def query(self, sql: str):
        if sql.lstrip().upper().startswith("DELETE"):
            self.deletes += 1
            return _FakeJob()
        return _FakeJob([{"latest_loaded": self.latest_loaded}])

    def load_table_from_file(self, *_args, **_kwargs):
        self.loads += 1
        return _FakeJob()


class EcbFetchRetryAndFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EcbFxRefreshConfig()
        self.sleeps: list[float] = []
        self.messages: list[str] = []

    def _run(self, responses, latest_loaded: date | None = None):
        client = _FakeBigQuery(latest_loaded if latest_loaded is not None else date.today() - timedelta(days=2))
        with mock.patch("orchestration.ecb_fx_refresh.requests.get", side_effect=responses) as get:
            result = run_ecb_fx_refresh(
                self.config,
                client=client,
                sleep=self.sleeps.append,
                notifier=self.messages.append,
            )
        return result, client, get

    def test_transient_errors_are_retried_with_backoff_then_succeed(self) -> None:
        result, client, get = self._run([
            _response(500),
            requests.Timeout("read timed out"),
            _response(200, ECB_CSV),
        ])

        self.assertEqual(get.call_count, 3)
        self.assertEqual(self.sleeps, [2, 4])
        self.assertEqual(result.rows_loaded, 1)
        self.assertIsNone(result.fallback_reason)
        self.assertEqual((client.deletes, client.loads), (1, 1))
        self.assertEqual(self.messages, [])

    def test_exhausted_retries_keep_the_stored_rates_and_warn(self) -> None:
        stored = date.today() - timedelta(days=3)
        result, client, get = self._run([_response(504)] * 4, latest_loaded=stored)

        self.assertEqual(get.call_count, 4)
        self.assertEqual(self.sleeps, [2, 4, 8])
        self.assertIn("504", result.fallback_reason)
        self.assertEqual(result.latest_stored_date, stored)
        self.assertEqual(result.rows_loaded, 0)
        # The stored rates are untouched.
        self.assertEqual((client.deletes, client.loads), (0, 0))
        self.assertEqual(len(self.messages), 1)
        self.assertIn(str(stored), self.messages[0])

    def test_client_errors_are_not_retried(self) -> None:
        result, _client, get = self._run([_response(400)])

        self.assertEqual(get.call_count, 1)
        self.assertEqual(self.sleeps, [])
        self.assertIsNotNone(result.fallback_reason)

    def test_too_old_stored_rates_fail_instead_of_falling_back(self) -> None:
        # Past the carry-forward window the marts would show NULL cost_eur.
        too_old = date.today() - timedelta(days=self.config.fallback_max_age_days + 1)

        with self.assertRaises(EcbFetchFailed):
            self._run([_response(503)] * 4, latest_loaded=too_old)
        self.assertEqual(self.messages, [])


if __name__ == "__main__":
    unittest.main()
