from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Sequence

from google.cloud import bigquery


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RawFreshnessConfig:
    project_id: str = "gads-export-all"
    cfg_dataset: str = "gads_reporting_cfg"
    cfg_accounts_table: str = "cfg_accounts"
    raw_dataset: str = "gads_raw"
    raw_account_stats_pattern: str = "p_ads_AccountStats_*"
    max_allowed_lag_days: int = 0
    execution_ts: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.execution_ts.tzinfo is None:
            object.__setattr__(self, "execution_ts", self.execution_ts.replace(tzinfo=timezone.utc))
        else:
            object.__setattr__(self, "execution_ts", self.execution_ts.astimezone(timezone.utc))


@dataclass(frozen=True)
class AccountFreshnessResult:
    client_id: str
    account_id: str
    account_timezone: str
    expected_last_date: date
    last_raw_date: date | None
    max_allowed_lag_days: int = 0
    account_name: str | None = None

    @property
    def days_lag(self) -> int | None:
        if self.last_raw_date is None:
            return None
        return max((self.expected_last_date - self.last_raw_date).days, 0)

    @property
    def is_ready(self) -> bool:
        if self.last_raw_date is None:
            return False
        return self.days_lag is not None and self.days_lag <= self.max_allowed_lag_days

    @property
    def freshness_status(self) -> str:
        return "healthy" if self.is_ready else "error"


@dataclass(frozen=True)
class RawFreshnessSummary:
    account_count: int
    ready_count: int
    failing_count: int
    max_allowed_lag_days: int
    checked_at: datetime
    failing_accounts: tuple[AccountFreshnessResult, ...]

    @property
    def is_ready(self) -> bool:
        return self.failing_count == 0


class RawFreshnessGateFailed(RuntimeError):
    def __init__(self, summary: RawFreshnessSummary):
        super().__init__(f"Raw freshness gate failed for {summary.failing_count} account(s)")
        self.summary = summary


def build_raw_freshness_query(config: RawFreshnessConfig) -> str:
    return f"""
with active_accounts as (
  select
    client_id,
    cast(account_id as string) as account_id,
    account_name,
    timezone as account_timezone
  from `{config.project_id}.{config.cfg_dataset}.{config.cfg_accounts_table}`
  where is_active = true
),
raw_max_dates as (
  select
    cast(customer_id as string) as account_id,
    max(segments_date) as last_raw_date
  from `{config.project_id}.{config.raw_dataset}.{config.raw_account_stats_pattern}`
  group by 1
)
select
  a.client_id,
  a.account_id,
  a.account_name,
  a.account_timezone,
  date_sub(date(@execution_ts, a.account_timezone), interval 1 day) as expected_last_date,
  r.last_raw_date
from active_accounts a
left join raw_max_dates r using (account_id)
order by a.client_id, a.account_id
""".strip()


def fetch_raw_freshness_results(
    client: bigquery.Client,
    config: RawFreshnessConfig,
) -> list[AccountFreshnessResult]:
    query = build_raw_freshness_query(config)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("execution_ts", "TIMESTAMP", config.execution_ts),
        ]
    )

    query_job = client.query(query, job_config=job_config)
    rows = query_job.result()

    return [
        AccountFreshnessResult(
            client_id=row["client_id"],
            account_id=row["account_id"],
            account_timezone=row["account_timezone"],
            expected_last_date=row["expected_last_date"],
            last_raw_date=row["last_raw_date"],
            max_allowed_lag_days=config.max_allowed_lag_days,
            account_name=row["account_name"],
        )
        for row in rows
    ]


def summarize_raw_freshness(
    results: Sequence[AccountFreshnessResult],
    *,
    checked_at: datetime | None = None,
) -> RawFreshnessSummary:
    checked = checked_at or _utc_now()
    failing_accounts = tuple(result for result in results if not result.is_ready)
    return RawFreshnessSummary(
        account_count=len(results),
        ready_count=len(results) - len(failing_accounts),
        failing_count=len(failing_accounts),
        max_allowed_lag_days=results[0].max_allowed_lag_days if results else 0,
        checked_at=checked,
        failing_accounts=failing_accounts,
    )


def run_raw_freshness_probe(
    config: RawFreshnessConfig,
    *,
    client: bigquery.Client | None = None,
) -> tuple[list[AccountFreshnessResult], RawFreshnessSummary]:
    bq_client = client or bigquery.Client(project=config.project_id)
    results = fetch_raw_freshness_results(bq_client, config)
    summary = summarize_raw_freshness(results, checked_at=config.execution_ts)
    return results, summary


def failing_accounts_payload(results: Iterable[AccountFreshnessResult]) -> list[dict[str, object]]:
    return [
        {
            "client_id": result.client_id,
            "account_id": result.account_id,
            "account_name": result.account_name,
            "account_timezone": result.account_timezone,
            "expected_last_date": result.expected_last_date,
            "last_raw_date": result.last_raw_date,
            "days_lag": result.days_lag,
            "freshness_status": result.freshness_status,
        }
        for result in results
        if not result.is_ready
    ]
