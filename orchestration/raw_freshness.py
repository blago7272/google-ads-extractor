"""The account freshness rule, and the probe that applies it before dbt runs.

One rule, used everywhere (the release log, the skipped-accounts alert, the
marts' include/exclude decision and `mart_data_freshness`):

    lag_days = today in the report timezone - last raw date
    stale    = lag_days > max_allowed_lag_days   (or no raw data at all)

The threshold and timezone are defined once, as the `vars` of dbt_project.yml
(`raw_freshness_max_allowed_lag_days`, `report_timezone`), so this module and
the dbt models cannot drift apart. `RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS`
overrides the threshold for both.

Each release appends every active account's result to
`<cfg_dataset>.ops_account_freshness` (the audit trail; never truncated), and
`stg_account_freshness` reads that run's rows instead of re-deriving them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from google.cloud import bigquery

LAG_DAYS_ENV_VAR = "RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS"
ACCOUNT_FRESHNESS_TABLE = "ops_account_freshness"
ACCOUNT_FRESHNESS_SCHEMA = (
    bigquery.SchemaField("run_timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("report_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("account_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("client_id", "STRING"),
    bigquery.SchemaField("account_name", "STRING"),
    bigquery.SchemaField("last_raw_date", "DATE"),
    bigquery.SchemaField("lag_days", "INTEGER"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("max_allowed_lag_days", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("report_timezone", "STRING", mode="REQUIRED"),
)


@lru_cache(maxsize=1)
def _dbt_project_vars() -> dict:
    path = Path(__file__).resolve().parents[1] / "dbt_project.yml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["vars"]


def default_report_timezone() -> str:
    return str(_dbt_project_vars()["report_timezone"])


def default_max_allowed_lag_days() -> int:
    """The project threshold, or the env override that dbt honours too."""
    override = os.getenv(LAG_DAYS_ENV_VAR)
    if override not in (None, ""):
        return int(override)
    return int(_dbt_project_vars()["raw_freshness_max_allowed_lag_days"])


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
    max_allowed_lag_days: int = field(default_factory=default_max_allowed_lag_days)
    report_timezone: str = field(default_factory=default_report_timezone)
    execution_ts: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.execution_ts.tzinfo is None:
            object.__setattr__(self, "execution_ts", self.execution_ts.replace(tzinfo=timezone.utc))
        else:
            object.__setattr__(self, "execution_ts", self.execution_ts.astimezone(timezone.utc))

    @property
    def account_freshness_table(self) -> str:
        return f"{self.project_id}.{self.cfg_dataset}.{ACCOUNT_FRESHNESS_TABLE}"


@dataclass(frozen=True)
class AccountFreshnessResult:
    client_id: str
    account_id: str
    report_date: date
    last_raw_date: date | None
    max_allowed_lag_days: int
    account_name: str | None = None

    @property
    def lag_days(self) -> int | None:
        if self.last_raw_date is None:
            return None
        return (self.report_date - self.last_raw_date).days

    @property
    def is_stale(self) -> bool:
        lag = self.lag_days
        return lag is None or lag > self.max_allowed_lag_days

    @property
    def is_ready(self) -> bool:
        return not self.is_stale

    @property
    def freshness_status(self) -> str:
        """`healthy` accounts are built into the marts; `stale` ones are excluded."""
        return "stale" if self.is_stale else "healthy"


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
    account_name
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
  date(@execution_ts, @report_timezone) as report_date,
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
            bigquery.ScalarQueryParameter("report_timezone", "STRING", config.report_timezone),
        ]
    )

    rows = client.query(query, job_config=job_config).result()

    return [
        AccountFreshnessResult(
            client_id=row["client_id"],
            account_id=row["account_id"],
            report_date=row["report_date"],
            last_raw_date=row["last_raw_date"],
            max_allowed_lag_days=config.max_allowed_lag_days,
            account_name=row["account_name"],
        )
        for row in rows
    ]


def summarize_raw_freshness(
    results: Sequence[AccountFreshnessResult],
    *,
    max_allowed_lag_days: int,
    checked_at: datetime | None = None,
) -> RawFreshnessSummary:
    checked = checked_at or _utc_now()
    failing_accounts = tuple(result for result in results if result.is_stale)
    return RawFreshnessSummary(
        account_count=len(results),
        ready_count=len(results) - len(failing_accounts),
        failing_count=len(failing_accounts),
        max_allowed_lag_days=max_allowed_lag_days,
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
    summary = summarize_raw_freshness(
        results,
        max_allowed_lag_days=config.max_allowed_lag_days,
        checked_at=config.execution_ts,
    )
    return results, summary


def account_freshness_rows(
    results: Iterable[AccountFreshnessResult],
    config: RawFreshnessConfig,
) -> list[dict[str, object]]:
    return [
        {
            "run_timestamp": config.execution_ts.isoformat(),
            "report_date": result.report_date.isoformat(),
            "account_id": result.account_id,
            "client_id": result.client_id,
            "account_name": result.account_name,
            "last_raw_date": result.last_raw_date.isoformat() if result.last_raw_date else None,
            "lag_days": result.lag_days,
            "status": result.freshness_status,
            "max_allowed_lag_days": result.max_allowed_lag_days,
            "report_timezone": config.report_timezone,
        }
        for result in results
    ]


def write_account_freshness(
    client: bigquery.Client,
    config: RawFreshnessConfig,
    results: Sequence[AccountFreshnessResult],
) -> int:
    """Append this run's results to ops_account_freshness (a load job: free, no streaming buffer)."""
    table = bigquery.Table(config.account_freshness_table, schema=list(ACCOUNT_FRESHNESS_SCHEMA))
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="run_timestamp",
    )
    table.clustering_fields = ["account_id"]
    client.create_table(table, exists_ok=True)

    rows = account_freshness_rows(results, config)
    if not rows:
        return 0
    job = client.load_table_from_json(
        rows,
        config.account_freshness_table,
        job_config=bigquery.LoadJobConfig(
            schema=list(ACCOUNT_FRESHNESS_SCHEMA),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ),
    )
    job.result()
    return len(rows)


def failing_accounts_payload(results: Iterable[AccountFreshnessResult]) -> list[dict[str, object]]:
    return [
        {
            "client_id": result.client_id,
            "account_id": result.account_id,
            "account_name": result.account_name,
            "report_date": result.report_date,
            "last_raw_date": result.last_raw_date,
            "lag_days": result.lag_days,
            "freshness_status": result.freshness_status,
        }
        for result in results
        if result.is_stale
    ]
