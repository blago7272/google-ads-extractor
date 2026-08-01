"""Detect and surface accounts that have dropped out of the reporting marts.

Since the raw freshness gate became non-blocking, a stale account is silently
excluded from every mart by the selective-freshness models and simply stops
appearing in reporting. Nothing announced the transition, so `Onesleep RS`
(5304022952) went missing for 47 days before anyone noticed.

This module closes that gap. On every release it:

  1. classifies each active account using the same rule as the
     `stg_account_freshness` model -- `date_diff(current_date(report_timezone),
     last_raw_date) > max_allowed_lag_days` -- so the alert set matches
     `mart_skipped_accounts` exactly rather than drifting from it;
  2. diffs that set against the previous release's set, persisted in
     `<cfg_dataset>.ops_skipped_accounts_state`;
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
from datetime import date, datetime, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import requests
from google.cloud import bigquery

from orchestration.logging_utils import emit_log
from orchestration.raw_freshness import AccountFreshnessResult

STATE_TABLE_SCHEMA = (
    bigquery.SchemaField("run_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("account_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("client_id", "STRING"),
    bigquery.SchemaField("account_name", "STRING"),
    bigquery.SchemaField("last_raw_date", "DATE"),
    bigquery.SchemaField("days_lag", "INTEGER"),
)


@dataclass(frozen=True)
class SkippedAccountsAlertConfig:
    project_id: str = "gads-export-all"
    cfg_dataset: str = "gads_reporting_cfg"
    state_table: str = "ops_skipped_accounts_state"
    report_timezone: str = "Europe/Sofia"
    max_allowed_lag_days: int = 3
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @property
    def full_state_table(self) -> str:
        return f"{self.project_id}.{self.cfg_dataset}.{self.state_table}"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @classmethod
    def from_env(
        cls,
        *,
        project_id: str,
        cfg_dataset: str,
        report_timezone: str,
        max_allowed_lag_days: int,
    ) -> "SkippedAccountsAlertConfig":
        return cls(
            project_id=project_id,
            cfg_dataset=cfg_dataset,
            report_timezone=report_timezone,
            max_allowed_lag_days=max_allowed_lag_days,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        )


@dataclass(frozen=True)
class SkippedAccount:
    account_id: str
    client_id: str
    account_name: str | None
    last_raw_date: date | None
    days_lag: int | None

    def as_payload(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "client_id": self.client_id,
            "account_name": self.account_name,
            "last_raw_date": self.last_raw_date,
            "days_lag": self.days_lag,
        }

    def as_line(self) -> str:
        label = self.account_name or self.account_id
        if self.last_raw_date is None:
            return f"{label} ({self.account_id}) — no raw data at all"
        return (
            f"{label} ({self.account_id}) — last raw {self.last_raw_date.isoformat()}, "
            f"{self.days_lag}d lag"
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
                key=lambda account: (-(account.days_lag or 10**6), account.account_id),
            )
        )

    @property
    def has_changes(self) -> bool:
        return bool(self.newly_skipped or self.recovered)


def _today_in_timezone(execution_ts: datetime, report_timezone: str) -> date:
    try:
        tzinfo = ZoneInfo(report_timezone)
    except Exception:  # noqa: BLE001 - unknown tz name should not break the release
        tzinfo = timezone.utc
    return execution_ts.astimezone(tzinfo).date()


def classify_skipped_accounts(
    results: Sequence[AccountFreshnessResult],
    *,
    execution_ts: datetime,
    report_timezone: str,
    max_allowed_lag_days: int,
) -> tuple[SkippedAccount, ...]:
    """Return the accounts the marts will exclude on this run.

    Mirrors `stg_account_freshness`: lag is measured from *today* in the report
    timezone, not from the account's own expected last date, so this set stays
    identical to `mart_skipped_accounts`.
    """
    today = _today_in_timezone(execution_ts, report_timezone)
    skipped: list[SkippedAccount] = []

    for result in results:
        if result.last_raw_date is None:
            skipped.append(
                SkippedAccount(
                    account_id=result.account_id,
                    client_id=result.client_id,
                    account_name=result.account_name,
                    last_raw_date=None,
                    days_lag=None,
                )
            )
            continue

        days_lag = (today - result.last_raw_date).days
        if days_lag > max_allowed_lag_days:
            skipped.append(
                SkippedAccount(
                    account_id=result.account_id,
                    client_id=result.client_id,
                    account_name=result.account_name,
                    last_raw_date=result.last_raw_date,
                    days_lag=days_lag,
                )
            )

    return tuple(sorted(skipped, key=lambda account: account.account_id))


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
            days_lag=None,
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


def _ensure_state_table(client: bigquery.Client, config: SkippedAccountsAlertConfig) -> None:
    table = bigquery.Table(config.full_state_table, schema=list(STATE_TABLE_SCHEMA))
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="run_ts",
    )
    client.create_table(table, exists_ok=True)


def load_previous_account_ids(
    client: bigquery.Client,
    config: SkippedAccountsAlertConfig,
) -> list[str] | None:
    """Account ids skipped by the most recent recorded run, or None if no runs yet."""
    query = f"""
    select account_id
    from `{config.full_state_table}`
    where run_ts = (select max(run_ts) from `{config.full_state_table}`)
    """
    rows = list(client.query(query).result())
    if not rows:
        return None
    return [row["account_id"] for row in rows]


def record_state(
    client: bigquery.Client,
    config: SkippedAccountsAlertConfig,
    accounts: Iterable[SkippedAccount],
    *,
    run_ts: datetime,
) -> int:
    """Append this run's skipped set via a load job (free; avoids streaming inserts)."""
    payload = [
        {
            "run_ts": run_ts.isoformat(),
            "account_id": account.account_id,
            "client_id": account.client_id or None,
            "account_name": account.account_name,
            "last_raw_date": account.last_raw_date.isoformat() if account.last_raw_date else None,
            "days_lag": account.days_lag,
        }
        for account in accounts
    ]
    if not payload:
        # Nothing skipped. Write a sentinel so the next run can tell "everything
        # healthy" apart from "no state recorded yet" and still detect a new drop-out.
        payload = [
            {
                "run_ts": run_ts.isoformat(),
                "account_id": "__none__",
                "client_id": None,
                "account_name": None,
                "last_raw_date": None,
                "days_lag": None,
            }
        ]

    job = client.load_table_from_json(
        payload,
        config.full_state_table,
        job_config=bigquery.LoadJobConfig(
            schema=list(STATE_TABLE_SCHEMA),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ),
    )
    job.result()
    return len(payload)


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
    """Classify, diff, persist and announce the skipped-account set.

    Raises nothing the caller needs to handle for alerting reasons; the release
    orchestrator additionally guards the whole step.
    """
    bq_client = client or bigquery.Client(project=config.project_id)

    current = classify_skipped_accounts(
        results,
        execution_ts=execution_ts,
        report_timezone=config.report_timezone,
        max_allowed_lag_days=config.max_allowed_lag_days,
    )

    _ensure_state_table(bq_client, config)
    previous_ids = load_previous_account_ids(bq_client, config)
    if previous_ids is not None:
        previous_ids = [account_id for account_id in previous_ids if account_id != "__none__"]

    diff = diff_against_previous(current, previous_ids)

    emit_log(
        "skipped_accounts_summary",
        skipped_count=len(diff.current),
        newly_skipped_count=len(diff.newly_skipped),
        recovered_count=len(diff.recovered),
        is_baseline=diff.is_baseline,
        max_allowed_lag_days=config.max_allowed_lag_days,
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

    record_state(bq_client, config, diff.current, run_ts=execution_ts)

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
