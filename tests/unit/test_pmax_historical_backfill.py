from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest

from orchestration.pmax_historical_backfill import (
    HistoryPolicy,
    LedgerRecord,
    history_dates_newest_first,
    next_eligible_dates,
)


class PmaxHistoricalBackfillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = HistoryPolicy(
            start_date=date(2025, 1, 1),
            rolling_boundary=date(2026, 7, 3),
            attempt_cap=3,
            retry_delay=timedelta(hours=24),
        )
        self.now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    def test_dates_are_newest_first_and_do_not_overlap_rolling_boundary(self) -> None:
        dates = history_dates_newest_first(self.policy.start_date, self.policy.rolling_boundary)
        self.assertEqual(dates[0], date(2026, 7, 2))
        self.assertEqual(dates[-1], date(2025, 1, 1))
        self.assertNotIn(self.policy.rolling_boundary, dates)

    def test_active_and_succeeded_dates_are_skipped(self) -> None:
        records = {
            date(2026, 7, 2): LedgerRecord(date(2026, 7, 2), "SUCCEEDED", 1),
            date(2026, 7, 1): LedgerRecord(date(2026, 7, 1), "RUNNING", 1),
        }
        self.assertEqual(
            next_eligible_dates(self.policy, records, self.now, limit=1),
            (date(2026, 6, 30),),
        )

    def test_failed_date_respects_retry_delay_and_attempt_cap(self) -> None:
        records = {
            date(2026, 7, 2): LedgerRecord(
                date(2026, 7, 2), "FAILED", 1, self.now - timedelta(hours=23)
            ),
            date(2026, 7, 1): LedgerRecord(
                date(2026, 7, 1), "FAILED", 3, self.now - timedelta(days=2)
            ),
        }
        self.assertEqual(
            next_eligible_dates(self.policy, records, self.now, limit=1),
            (date(2026, 6, 30),),
        )
        records[date(2026, 7, 2)] = LedgerRecord(
            date(2026, 7, 2), "FAILED", 1, self.now - timedelta(hours=24)
        )
        self.assertEqual(
            next_eligible_dates(self.policy, records, self.now, limit=1),
            (date(2026, 7, 2),),
        )
