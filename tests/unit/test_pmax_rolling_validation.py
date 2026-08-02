from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest

from orchestration.pmax_rolling_validation import (
    latest_state_by_run_date,
    rolling_window_dates,
    window_state_summary,
)


class PmaxRollingValidationTest(unittest.TestCase):
    def test_rolling_window_is_end_exclusive_and_has_exact_size(self) -> None:
        dates = rolling_window_dates(date(2026, 8, 2), 30)
        self.assertEqual(len(dates), 30)
        self.assertEqual(dates[0], date(2026, 7, 3))
        self.assertEqual(dates[-1], date(2026, 8, 1))

    def test_latest_schedule_attempt_controls_each_date_state(self) -> None:
        runs = [
            SimpleNamespace(
                run_time=datetime(2026, 8, 1, 8, tzinfo=timezone.utc),
                schedule_time=datetime(2026, 8, 2, 20, tzinfo=timezone.utc),
                state="SUCCEEDED",
            ),
            SimpleNamespace(
                run_time=datetime(2026, 8, 1, 8, tzinfo=timezone.utc),
                schedule_time=datetime(2026, 8, 3, 8, tzinfo=timezone.utc),
                state="RUNNING",
            ),
        ]
        self.assertEqual(
            latest_state_by_run_date(runs), {date(2026, 8, 1): "RUNNING"}
        )

    def test_window_summary_separates_incomplete_and_failed_dates(self) -> None:
        expected = (date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 1))
        succeeded, incomplete, failed = window_state_summary(
            expected,
            {
                date(2026, 7, 30): "SUCCEEDED",
                date(2026, 7, 31): "PENDING",
                date(2026, 8, 1): "FAILED",
            },
        )
        self.assertEqual(succeeded, (date(2026, 7, 30),))
        self.assertEqual(incomplete, (date(2026, 7, 31),))
        self.assertEqual(failed, (date(2026, 8, 1),))
