from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Mapping


ACTIVE_STATUSES = frozenset({"PENDING", "RUNNING"})
TERMINAL_SUCCESS_STATUSES = frozenset({"SUCCEEDED"})
RETRYABLE_FAILURE_STATUSES = frozenset({"FAILED", "CANCELLED"})


@dataclass(frozen=True)
class LedgerRecord:
    source_date: date
    status: str
    attempt_count: int
    updated_at: datetime | None = None
    transfer_run_name: str | None = None


@dataclass(frozen=True)
class HistoryPolicy:
    start_date: date
    rolling_boundary: date
    attempt_cap: int
    retry_delay: timedelta


def history_dates_newest_first(start_date: date, rolling_boundary: date) -> tuple[date, ...]:
    """Return [start_date, rolling_boundary) in newest-first order."""
    if start_date >= rolling_boundary:
        return ()
    length = (rolling_boundary - start_date).days
    return tuple(rolling_boundary - timedelta(days=offset) for offset in range(1, length + 1))


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_eligible(record: LedgerRecord | None, policy: HistoryPolicy, now: datetime) -> bool:
    """Whether a date may be submitted without duplicating an active or accepted run."""
    if record is None:
        return True

    status = record.status.upper()
    if status in ACTIVE_STATUSES or status in TERMINAL_SUCCESS_STATUSES:
        return False
    if record.attempt_count >= policy.attempt_cap:
        return False
    if status in RETRYABLE_FAILURE_STATUSES:
        if record.updated_at is None:
            return True
        return _as_utc(now) - _as_utc(record.updated_at) >= policy.retry_delay

    # An unrecognised ledger state must be investigated, rather than retried.
    return False


def next_eligible_dates(
    policy: HistoryPolicy,
    records_by_date: Mapping[date, LedgerRecord],
    now: datetime,
    limit: int,
) -> tuple[date, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")

    eligible: list[date] = []
    for source_date in history_dates_newest_first(policy.start_date, policy.rolling_boundary):
        if is_eligible(records_by_date.get(source_date), policy, now):
            eligible.append(source_date)
            if len(eligible) == limit:
                break
    return tuple(eligible)
