from __future__ import annotations

from datetime import date, datetime, timezone
import os
import unittest
from unittest import mock

from orchestration import raw_freshness
from orchestration.raw_freshness import (
    AccountFreshnessResult,
    RawFreshnessConfig,
    account_freshness_rows,
    build_raw_freshness_query,
    summarize_raw_freshness,
)

TODAY = date(2026, 10, 18)


def _result(last_raw_date: date | None, *, threshold: int = 3) -> AccountFreshnessResult:
    return AccountFreshnessResult(
        client_id="client-a",
        account_id="123",
        report_date=TODAY,
        last_raw_date=last_raw_date,
        max_allowed_lag_days=threshold,
        account_name="Account A",
    )


class FreshnessRuleTest(unittest.TestCase):
    """lag = today in the report timezone - last raw date; stale when lag > threshold."""

    def test_yesterdays_data_is_lag_one_and_healthy(self) -> None:
        result = _result(date(2026, 10, 17))

        self.assertEqual(result.lag_days, 1)
        self.assertFalse(result.is_stale)
        self.assertEqual(result.freshness_status, "healthy")

    def test_lag_equal_to_the_threshold_is_still_healthy(self) -> None:
        result = _result(date(2026, 10, 15))

        self.assertEqual(result.lag_days, 3)
        self.assertEqual(result.freshness_status, "healthy")

    def test_lag_past_the_threshold_is_stale(self) -> None:
        result = _result(date(2026, 10, 14))

        self.assertEqual(result.lag_days, 4)
        self.assertTrue(result.is_stale)
        self.assertFalse(result.is_ready)
        self.assertEqual(result.freshness_status, "stale")

    def test_no_raw_data_is_stale_with_no_lag(self) -> None:
        result = _result(None)

        self.assertIsNone(result.lag_days)
        self.assertEqual(result.freshness_status, "stale")

    def test_summary_counts_stale_accounts_as_failing(self) -> None:
        summary = summarize_raw_freshness(
            [_result(date(2026, 10, 17)), _result(date(2026, 9, 30))],
            max_allowed_lag_days=3,
            checked_at=datetime(2026, 10, 18, 3, 30, tzinfo=timezone.utc),
        )

        self.assertEqual((summary.ready_count, summary.failing_count), (1, 1))
        self.assertFalse(summary.is_ready)


class SingleSourceDefaultsTest(unittest.TestCase):
    def test_threshold_and_timezone_come_from_dbt_project(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(raw_freshness.default_max_allowed_lag_days(), 3)
            self.assertEqual(RawFreshnessConfig().max_allowed_lag_days, 3)
        self.assertEqual(raw_freshness.default_report_timezone(), "Europe/Sofia")

    def test_env_var_overrides_the_threshold(self) -> None:
        with mock.patch.dict(os.environ, {"RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS": "5"}):
            self.assertEqual(RawFreshnessConfig().max_allowed_lag_days, 5)

    def test_query_measures_from_today_in_the_report_timezone(self) -> None:
        query = build_raw_freshness_query(RawFreshnessConfig())

        self.assertIn("date(@execution_ts, @report_timezone) as report_date", query)
        self.assertNotIn("interval 1 day", query)


class AccountFreshnessRowsTest(unittest.TestCase):
    def test_rows_carry_the_audit_fields(self) -> None:
        config = RawFreshnessConfig(
            execution_ts=datetime(2026, 10, 18, 3, 30, tzinfo=timezone.utc),
            max_allowed_lag_days=3,
        )
        rows = account_freshness_rows([_result(date(2026, 10, 10)), _result(None)], config)

        self.assertEqual(
            rows[0],
            {
                "run_timestamp": "2026-10-18T03:30:00+00:00",
                "report_date": "2026-10-18",
                "account_id": "123",
                "client_id": "client-a",
                "account_name": "Account A",
                "last_raw_date": "2026-10-10",
                "lag_days": 8,
                "status": "stale",
                "max_allowed_lag_days": 3,
                "report_timezone": "Europe/Sofia",
            },
        )
        self.assertIsNone(rows[1]["last_raw_date"])
        self.assertIsNone(rows[1]["lag_days"])


if __name__ == "__main__":
    unittest.main()
