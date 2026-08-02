from __future__ import annotations

from datetime import date
import unittest

from orchestration.ecb_fx_refresh import EcbFxRefreshConfig, resolve_refresh_window


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


if __name__ == "__main__":
    unittest.main()
