from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from google.api_core.exceptions import NotFound

from orchestration.raw_freshness import AccountFreshnessResult
from orchestration.skipped_accounts_alert import (
    SkippedAccount,
    SkippedAccountsAlertConfig,
    build_alert_message,
    classify_skipped_accounts,
    diff_against_previous,
    load_previous_account_ids,
)


def _result(
    account_id: str,
    last_raw_date: date | None,
    *,
    account_name: str | None = None,
) -> AccountFreshnessResult:
    return AccountFreshnessResult(
        client_id="idconsult",
        account_id=account_id,
        report_date=date(2026, 8, 1),  # EXECUTION_TS in Europe/Sofia
        last_raw_date=last_raw_date,
        max_allowed_lag_days=3,
        account_name=account_name,
    )


EXECUTION_TS = datetime(2026, 8, 1, 3, 30, tzinfo=timezone.utc)


class ClassifySkippedAccountsTest(unittest.TestCase):
    """The alert takes the probe's own verdict (is_stale); it has no rule of its own."""

    def _classify(self, results: list[AccountFreshnessResult]):
        return classify_skipped_accounts(results)

    def test_fresh_account_is_not_skipped(self) -> None:
        self.assertEqual(self._classify([_result("1", date(2026, 7, 31))]), ())

    def test_account_at_the_threshold_is_not_skipped(self) -> None:
        # Lag of exactly max_allowed_lag_days stays in the marts: the rule
        # excludes only when lag > threshold.
        self.assertEqual(self._classify([_result("1", date(2026, 7, 29))]), ())

    def test_account_past_the_threshold_is_skipped(self) -> None:
        skipped = self._classify([_result("1", date(2026, 7, 28))])

        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].account_id, "1")
        self.assertEqual(skipped[0].lag_days, 4)

    def test_account_with_no_raw_data_is_skipped(self) -> None:
        skipped = self._classify([_result("1", None)])

        self.assertEqual(len(skipped), 1)
        self.assertIsNone(skipped[0].lag_days)

    def test_long_running_regression_reports_full_lag(self) -> None:
        # Onesleep RS: last raw 2026-06-15, evaluated 2026-08-01.
        skipped = self._classify(
            [_result("5304022952", date(2026, 6, 15), account_name="Onesleep RS")]
        )

        self.assertEqual(skipped[0].lag_days, 47)
        self.assertEqual(skipped[0].account_name, "Onesleep RS")


class DiffAgainstPreviousTest(unittest.TestCase):
    def _account(self, account_id: str, lag_days: int = 10) -> SkippedAccount:
        return SkippedAccount(
            account_id=account_id,
            client_id="idconsult",
            account_name=f"Account {account_id}",
            last_raw_date=date(2026, 7, 1),
            lag_days=lag_days,
        )

    def test_first_run_is_a_baseline_and_raises_no_new_alert(self) -> None:
        diff = diff_against_previous([self._account("1"), self._account("2")], None)

        self.assertTrue(diff.is_baseline)
        self.assertEqual(diff.newly_skipped, ())
        self.assertEqual(len(diff.still_skipped), 2)
        self.assertFalse(diff.has_changes)

    def test_new_drop_out_is_detected(self) -> None:
        diff = diff_against_previous([self._account("1"), self._account("2")], ["1"])

        self.assertEqual([a.account_id for a in diff.newly_skipped], ["2"])
        self.assertEqual([a.account_id for a in diff.still_skipped], ["1"])
        self.assertEqual(diff.recovered, ())
        self.assertTrue(diff.has_changes)

    def test_recovery_is_detected(self) -> None:
        diff = diff_against_previous([self._account("1")], ["1", "2"])

        self.assertEqual([a.account_id for a in diff.recovered], ["2"])
        self.assertEqual(diff.newly_skipped, ())
        self.assertTrue(diff.has_changes)

    def test_steady_state_reports_no_changes(self) -> None:
        diff = diff_against_previous([self._account("1")], ["1"])

        self.assertFalse(diff.has_changes)
        self.assertEqual(len(diff.still_skipped), 1)

    def test_everything_healthy_after_previous_outage(self) -> None:
        diff = diff_against_previous([], ["1"])

        self.assertEqual([a.account_id for a in diff.recovered], ["1"])
        self.assertEqual(diff.current, ())

    def test_current_is_ordered_by_worst_lag_first(self) -> None:
        diff = diff_against_previous(
            [self._account("1", lag_days=5), self._account("2", lag_days=47)],
            ["1", "2"],
        )

        self.assertEqual([a.account_id for a in diff.current], ["2", "1"])


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    """Serves canned rows for the new and the legacy state table; None means NotFound."""

    def __init__(self, freshness_rows, legacy_rows):
        self.freshness_rows = freshness_rows
        self.legacy_rows = legacy_rows

    def query(self, sql, job_config=None):
        rows = self.freshness_rows if "ops_account_freshness" in sql else self.legacy_rows
        if rows is None:
            raise NotFound("table not found")
        return _Rows(rows)


class LoadPreviousAccountIdsTest(unittest.TestCase):
    def _load(self, freshness_rows, legacy_rows):
        return load_previous_account_ids(
            _FakeClient(freshness_rows, legacy_rows),
            SkippedAccountsAlertConfig(),
            run_ts=EXECUTION_TS,
        )

    def test_previous_run_stale_accounts_come_from_ops_account_freshness(self) -> None:
        rows = [
            {"account_id": "1", "status": "stale"},
            {"account_id": "2", "status": "healthy"},
        ]
        self.assertEqual(self._load(rows, legacy_rows=None), ["1"])

    def test_a_previous_run_with_nothing_stale_is_not_a_baseline(self) -> None:
        self.assertEqual(self._load([{"account_id": "2", "status": "healthy"}], None), [])

    def test_first_run_on_the_new_table_reads_the_legacy_state(self) -> None:
        legacy = [{"account_id": "1"}, {"account_id": "3"}]
        self.assertEqual(self._load([], legacy), ["1", "3"])

    def test_legacy_sentinel_means_nothing_was_skipped(self) -> None:
        self.assertEqual(self._load(None, [{"account_id": "__none__"}]), [])

    def test_no_history_anywhere_is_a_baseline(self) -> None:
        self.assertIsNone(self._load(None, None))


class AlertMessageTest(unittest.TestCase):
    def test_message_names_the_new_drop_out(self) -> None:
        current = [
            SkippedAccount(
                account_id="5304022952",
                client_id="idconsult",
                account_name="Onesleep RS",
                last_raw_date=date(2026, 6, 15),
                lag_days=47,
            )
        ]
        message = build_alert_message(diff_against_previous(current, []))

        self.assertIn("DROPPED OUT", message)
        self.assertIn("Onesleep RS", message)
        self.assertIn("5304022952", message)
        self.assertIn("47d lag", message)

    def test_all_healthy_message(self) -> None:
        message = build_alert_message(diff_against_previous([], []))

        self.assertIn("All active Google Ads accounts are fresh", message)


if __name__ == "__main__":
    unittest.main()
