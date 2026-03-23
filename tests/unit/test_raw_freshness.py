from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from orchestration.raw_freshness import AccountFreshnessResult, summarize_raw_freshness


class RawFreshnessEvaluationTest(unittest.TestCase):
    def test_result_is_ready_when_last_raw_matches_expected(self) -> None:
        result = AccountFreshnessResult(
            client_id="client-a",
            account_id="123",
            account_timezone="Europe/Sofia",
            expected_last_date=date(2026, 3, 22),
            last_raw_date=date(2026, 3, 22),
            max_allowed_lag_days=0,
        )

        self.assertTrue(result.is_ready)
        self.assertEqual(result.days_lag, 0)
        self.assertEqual(result.freshness_status, "healthy")

    def test_result_respects_allowed_lag(self) -> None:
        result = AccountFreshnessResult(
            client_id="client-a",
            account_id="123",
            account_timezone="Europe/Sofia",
            expected_last_date=date(2026, 3, 22),
            last_raw_date=date(2026, 3, 21),
            max_allowed_lag_days=1,
        )

        self.assertTrue(result.is_ready)
        self.assertEqual(result.days_lag, 1)

    def test_summary_flags_failing_accounts(self) -> None:
        passing = AccountFreshnessResult(
            client_id="client-a",
            account_id="123",
            account_timezone="Europe/Sofia",
            expected_last_date=date(2026, 3, 22),
            last_raw_date=date(2026, 3, 22),
            max_allowed_lag_days=0,
        )
        failing = AccountFreshnessResult(
            client_id="client-b",
            account_id="456",
            account_timezone="Europe/Sofia",
            expected_last_date=date(2026, 3, 22),
            last_raw_date=None,
            max_allowed_lag_days=0,
        )

        summary = summarize_raw_freshness(
            [passing, failing],
            checked_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
        )

        self.assertFalse(summary.is_ready)
        self.assertEqual(summary.account_count, 2)
        self.assertEqual(summary.ready_count, 1)
        self.assertEqual(summary.failing_count, 1)
        self.assertEqual(summary.failing_accounts[0].account_id, "456")


if __name__ == "__main__":
    unittest.main()
