from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any


def rolling_window_dates(end_exclusive: date, days: int) -> tuple[date, ...]:
    if days <= 0:
        raise ValueError("days must be positive")
    start = end_exclusive - timedelta(days=days)
    return tuple(start + timedelta(days=offset) for offset in range(days))


def timestamp_to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "ToDatetime"):
        return value.ToDatetime(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported timestamp value: {value!r}")


def latest_state_by_run_date(runs: Iterable[Any]) -> dict[date, str]:
    """Return the most recently scheduled state for each source run date."""
    latest: dict[date, tuple[datetime, str]] = {}
    for run in runs:
        run_date = timestamp_to_datetime(run.run_time).date()
        schedule_time = timestamp_to_datetime(run.schedule_time)
        state = getattr(run.state, "name", str(run.state))
        existing = latest.get(run_date)
        if existing is None or schedule_time > existing[0]:
            latest[run_date] = (schedule_time, state)
    return {run_date: state for run_date, (_, state) in latest.items()}


def window_state_summary(
    expected_dates: Iterable[date], latest_states: dict[date, str]
) -> tuple[tuple[date, ...], tuple[date, ...], tuple[date, ...]]:
    succeeded: list[date] = []
    incomplete: list[date] = []
    failed: list[date] = []
    for run_date in expected_dates:
        state = latest_states.get(run_date)
        if state == "SUCCEEDED":
            succeeded.append(run_date)
        elif state in {"FAILED", "CANCELLED"}:
            failed.append(run_date)
        else:
            incomplete.append(run_date)
    return tuple(succeeded), tuple(incomplete), tuple(failed)
