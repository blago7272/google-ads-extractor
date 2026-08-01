from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from orchestration.raw_freshness import AccountFreshnessResult
from orchestration.skipped_accounts_alert import (
    SkippedAccount,
    build_alert_message,
    classify_skipped_accounts,
    diff_against_previous,
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
        account_timezone="Europe/Sofia",
        expected_last_date=date(2026, 7, 31),
        last_raw_date=last_raw_date,
        max_allowed_lag_days=3,
        account_name=account_name,
    )


EXECUTION_TS = datetime(2026, 8, 1, 3, 30, tzinfo=timezone.utc)


class ClassifySkippedAccountsTest(unittest.TestCase):
    def _classify(self, results: list[AccountFreshnessResult]):
        return classify_skipped_accounts(
            results,
            execution_ts=EXECUTION_TS,
            report_timezone="Europe/Sofia",
            max_allowed_lag_days=3,
        )

    def test_fresh_account_is_not_skipped(self) -> None:
        self.assertEqual(self._classify([_result("1", date(2026, 7, 31))]), ())

    def test_account_at_the_threshold_is_not_skipped(self) -> None:
        # Lag of exactly max_allowed_lag_days stays in the marts, matching
        # stg_account_freshness which excludes only when lag > threshold.
        self.assertEqual(self._classify([_result("1", date(2026, 7, 29))]), ())

    def test_account_past_the_threshold_is_skipped(self) -> None:
        skipped = self._classify([_result("1", date(2026, 7, 28))])

        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].account_id, "1")
        self.assertEqual(skipped[0].days_lag, 4)

    def test_account_with_no_raw_data_is_skipped(self) -> None:
        skipped = self._classify([_result("1", None)])

        self.assertEqual(len(skipped), 1)
        self.assertIsNone(skipped[0].days_lag)

    def test_long_running_regression_reports_full_lag(self) -> None:
        # Onesleep RS: last raw 2026-06-15, evaluated 2026-08-01.
        skipped = self._classify(
            [_result("5304022952", date(2026, 6, 15), account_name="Onesleep RS")]
        )

        self.assertEqual(skipped[0].days_lag, 47)
        self.assertEqual(skipped[0].account_name, "Onesleep RS")


class DiffAgainstPreviousTest(unittest.TestCase):
    def _account(self, account_id: str, days_lag: int = 10) -> SkippedAccount:
        return SkippedAccount(
            account_id=account_id,
            client_id="idconsult",
            account_name=f"Account {account_id}",
            last_raw_date=date(2026, 7, 1),
            days_lag=days_lag,
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
            [self._account("1", days_lag=5), self._account("2", days_lag=47)],
            ["1", "2"],
        )

        self.assertEqual([a.account_id for a in diff.current], ["2", "1"])


class AlertMessageTest(unittest.TestCase):
    def test_message_names_the_new_drop_out(self) -> None:
        current = [
            SkippedAccount(
                account_id="5304022952",
                client_id="idconsult",
                account_name="Onesleep RS",
                last_raw_date=date(2026, 6, 15),
                days_lag=47,
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
