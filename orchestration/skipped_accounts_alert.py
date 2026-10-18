"""Detect and surface accounts that have dropped out of the reporting marts.

Since the raw freshness gate became non-blocking, a stale account is silently
excluded from every mart by the selective-freshness models and simply stops
appearing in reporting. Nothing announced the transition, so `Onesleep RS`
(5304022952) went missing for 47 days before anyone noticed.

This module closes that gap. On every release it:

  1. takes the stale accounts straight from the freshness probe's results
     (`AccountFreshnessResult.is_stale`, the one rule in
     `orchestration/raw_freshness.py`), the same rows `stg_account_freshness`
     reads, so the alert set is exactly what the marts exclude;
  2. diffs that set against the previous release's, read back from
     `<cfg_dataset>.ops_account_freshness` (written by the raw_freshness_gate
     step just before this one);
  3. emits structured logs -- an ERROR for newly skipped accounts, an INFO for
     recoveries, and a standing WARNING listing every currently skipped account
     so a long-running outage keeps surfacing instead of alerting once and
     going quiet;
  4. optionally posts the same summary to Telegram.

Alerting never fails the release: a broken notifier must not break a working
data pipeline. Every failure path is logged and swallowed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from orchestration.logging_utils import emit_log
from orchestration.raw_freshness import ACCOUNT_FRESHNESS_TABLE, AccountFreshnessResult


@dataclass(frozen=True)
class SkippedAccountsAlertConfig:
    project_id: str = "gads-export-all"
    cfg_dataset: str = "gads_reporting_cfg"
    freshness_table: str = ACCOUNT_FRESHNESS_TABLE
    # Written by releases before ops_account_freshness existed. Read only, and only
    # until the new table has a previous run, so the switch-over is not a baseline.
    legacy_state_table: str = "ops_skipped_accounts_state"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @property
    def full_freshness_table(self) -> str:
        return f"{self.project_id}.{self.cfg_dataset}.{self.freshness_table}"

    @property
    def full_legacy_state_table(self) -> str:
        return f"{self.project_id}.{self.cfg_dataset}.{self.legacy_state_table}"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @classmethod
    def from_env(cls, *, project_id: str, cfg_dataset: str) -> "SkippedAccountsAlertConfig":
        return cls(
            project_id=project_id,
            cfg_dataset=cfg_dataset,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        )


@dataclass(frozen=True)
class SkippedAccount:
    account_id: str
    client_id: str
    account_name: str | None
    last_raw_date: date | None
    lag_days: int | None

    def as_payload(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "client_id": self.client_id,
            "account_name": self.account_name,
            "last_raw_date": self.last_raw_date,
            "lag_days": self.lag_days,
        }

    def as_line(self) -> str:
        label = self.account_name or self.account_id
        if self.last_raw_date is None:
            return f"{label} ({self.account_id}) — no raw data at all"
        return (
            f"{label} ({self.account_id}) — last raw {self.last_raw_date.isoformat()}, "
            f"{self.lag_days}d lag"
        )


@dataclass(frozen=True)
class SkippedAccountsDiff:
    newly_skipped: tuple[SkippedAccount, ...]
    recovered: tuple[SkippedAccount, ...]
    still_skipped: tuple[SkippedAccount, ...]
    is_baseline: bool

    @property
    def current(self) -> tuple[SkippedAccount, ...]:
        return tuple(
            sorted(
                self.newly_skipped + self.still_skipped,
                key=lambda account: (-(account.lag_days or 10**6), account.account_id),
            )
        )

    @property
    def has_changes(self) -> bool:
        return bool(self.newly_skipped or self.recovered)


def classify_skipped_accounts(
    results: Sequence[AccountFreshnessResult],
) -> tuple[SkippedAccount, ...]:
    """The accounts the marts exclude on this run: the probe's stale results."""
    return tuple(
        sorted(
            (
                SkippedAccount(
                    account_id=result.account_id,
                    client_id=result.client_id,
                    account_name=result.account_name,
                    last_raw_date=result.last_raw_date,
                    lag_days=result.lag_days,
                )
                for result in results
                if result.is_stale
            ),
            key=lambda account: account.account_id,
        )
    )


def diff_against_previous(
    current: Sequence[SkippedAccount],
    previous_account_ids: Sequence[str] | None,
) -> SkippedAccountsDiff:
    """Diff the current skipped set against the previous release's set.

    `previous_account_ids is None` means no prior state exists. That first run is
    treated as a baseline: the current set is recorded but nothing is reported as
    a new regression, so deploying this does not fire an alert for every account
    that was already stale.
    """
    if previous_account_ids is None:
        return SkippedAccountsDiff(
            newly_skipped=(),
            recovered=(),
            still_skipped=tuple(current),
            is_baseline=True,
        )

    previous = set(previous_account_ids)
    current_by_id = {account.account_id: account for account in current}
    newly_skipped = tuple(
        account for account in current if account.account_id not in previous
    )
    still_skipped = tuple(
        account for account in current if account.account_id in previous
    )
    recovered = tuple(
        SkippedAccount(
            account_id=account_id,
            client_id="",
            account_name=None,
            last_raw_date=None,
            lag_days=None,
        )
        for account_id in sorted(previous - set(current_by_id))
    )
    return SkippedAccountsDiff(
        newly_skipped=newly_skipped,
        recovered=recovered,
        still_skipped=still_skipped,
        is_baseline=False,
    )


def build_alert_message(diff: SkippedAccountsDiff) -> str:
    lines: list[str] = []
    if diff.newly_skipped:
        lines.append(
            f"🔴 {len(diff.newly_skipped)} account(s) DROPPED OUT of Google Ads reporting:"
        )
        lines.extend(f"  • {account.as_line()}" for account in diff.newly_skipped)
    if diff.recovered:
        lines.append(f"🟢 {len(diff.recovered)} account(s) recovered:")
        lines.extend(f"  • {account.account_id}" for account in diff.recovered)
    if diff.still_skipped:
        lines.append(f"⚠️ {len(diff.still_skipped)} account(s) still excluded:")
        lines.extend(f"  • {account.as_line()}" for account in diff.still_skipped)
    if not lines:
        return "✅ All active Google Ads accounts are fresh — nothing excluded from the marts."
    return "\n".join(lines)


def _previous_run_stale_ids(
    client: bigquery.Client,
    config: SkippedAccountsAlertConfig,
    *,
    run_ts: datetime,
) -> list[str] | None:
    """Stale account ids of the latest run before `run_ts`, or None if there is none.

    Every run records every active account, so a previous run with no stale
    accounts returns [] rather than None.
    """
    query = f"""
    select account_id, status
    from `{config.full_freshness_table}`
    where run_timestamp = (
      select max(run_timestamp)
      from `{config.full_freshness_table}`
      where run_timestamp < @run_ts
    )
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_ts", "TIMESTAMP", run_ts)]
    )
    try:
        rows = list(client.query(query, job_config=job_config).result())
    except NotFound:
        return None
    if not rows:
        return None
    return [row["account_id"] for row in rows if row["status"] == "stale"]


def _legacy_stale_ids(
    client: bigquery.Client,
    config: SkippedAccountsAlertConfig,
) -> list[str] | None:
    """The last skipped set recorded in ops_skipped_accounts_state, if that table exists."""
    query = f"""
    select account_id
    from `{config.full_legacy_state_table}`
    where run_ts = (select max(run_ts) from `{config.full_legacy_state_table}`)
    """
    try:
        rows = list(client.query(query).result())
    except NotFound:
        return None
    if not rows:
        return None
    # "__none__" was the sentinel for "nothing skipped".
    return [row["account_id"] for row in rows if row["account_id"] != "__none__"]


def load_previous_account_ids(
    client: bigquery.Client,
    config: SkippedAccountsAlertConfig,
    *,
    run_ts: datetime,
) -> list[str] | None:
    """Account ids the previous release excluded, or None if no release is recorded."""
    previous = _previous_run_stale_ids(client, config, run_ts=run_ts)
    if previous is not None:
        return previous
    return _legacy_stale_ids(client, config)


def send_telegram(config: SkippedAccountsAlertConfig, message: str) -> bool:
    if not config.telegram_enabled:
        return False

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": config.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()
    return True


def run_skipped_accounts_alert(
    results: Sequence[AccountFreshnessResult],
    config: SkippedAccountsAlertConfig,
    *,
    execution_ts: datetime,
    client: bigquery.Client | None = None,
) -> SkippedAccountsDiff:
    """Classify, diff and announce the skipped-account set.

    Raises nothing the caller needs to handle for alerting reasons; the release
    orchestrator additionally guards the whole step.
    """
    bq_client = client or bigquery.Client(project=config.project_id)

    current = classify_skipped_accounts(results)
    previous_ids = load_previous_account_ids(bq_client, config, run_ts=execution_ts)
    diff = diff_against_previous(current, previous_ids)

    emit_log(
        "skipped_accounts_summary",
        skipped_count=len(diff.current),
        newly_skipped_count=len(diff.newly_skipped),
        recovered_count=len(diff.recovered),
        is_baseline=diff.is_baseline,
    )

    if diff.is_baseline:
        emit_log(
            "skipped_accounts_baseline_initialized",
            skipped_accounts=[account.as_payload() for account in diff.current],
        )

    if diff.newly_skipped:
        # The alert to page on: an account that was in reporting yesterday is gone today.
        emit_log(
            "skipped_accounts_alert",
            level="ERROR",
            newly_skipped=[account.as_payload() for account in diff.newly_skipped],
        )

    if diff.recovered:
        emit_log(
            "skipped_accounts_recovered",
            recovered_account_ids=[account.account_id for account in diff.recovered],
        )

    if diff.current:
        # Standing warning: re-emitted every run so a long outage never goes quiet.
        emit_log(
            "skipped_accounts_still_excluded",
            level="WARNING",
            skipped_accounts=[account.as_payload() for account in diff.current],
        )

    if diff.has_changes or diff.current:
        message = build_alert_message(diff)
        try:
            if send_telegram(config, message):
                emit_log("skipped_accounts_telegram_sent", chat_id=config.telegram_chat_id)
            else:
                emit_log(
                    "skipped_accounts_telegram_skipped",
                    reason="TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set",
                )
        except Exception as exc:  # noqa: BLE001 - a notifier must never break the release
            emit_log(
                "skipped_accounts_telegram_failed",
                level="ERROR",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    return diff
