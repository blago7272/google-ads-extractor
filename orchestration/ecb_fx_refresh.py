"""Refresh ECB daily exchange rates as part of the release pipeline.

Fetches the latest ECB reference rates for the configured currencies and
upserts them into the `ecb_exchange_rates_daily` table in BigQuery.
Uses a 7-day lookback window to fill any gaps from weekends or holidays.

The ECB API has transient outages (HTTP 500 on 2026-09-18, 504 on 2026-10-04,
each of which used to fail the whole release). A transient error is retried
with backoff; if the API is still down, the release keeps the rates already in
BigQuery and the marts carry the latest one forward (see
`stg_account_fx_rates_daily`, `fx_carry_forward_days`).
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import requests
from google.cloud import bigquery

from orchestration.logging_utils import emit_log
from orchestration.ops_telegram import send_ops_message

ECB_API_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"
)

# Waits before each retry of a transient failure: four attempts in all.
RETRY_BACKOFF_SECONDS = (2, 4, 8)


class EcbFetchFailed(RuntimeError):
    """The ECB API could not be read, after any retries."""


@dataclass(frozen=True)
class EcbFxRefreshConfig:
    project_id: str = "gads-export-all"
    dataset: str = "gads_reporting_cfg"
    table: str = "ecb_exchange_rates_daily"
    currencies: tuple[str, ...] = ("USD", "GBP", "RON", "MXN")
    # Minimum window fetched on every run, even when the table is fully up to date.
    lookback_days: int = 7
    # Re-fetch this far back past the stored watermark, to absorb a late ECB publication.
    watermark_overlap_days: int = 2
    # Ceiling on a catch-up window, so a corrupt watermark cannot trigger a huge fetch.
    max_catchup_days: int = 400
    # Fall back to the stored rates only while they are this fresh. Keep it at or
    # below the dbt var `fx_carry_forward_days` (30): past that, the marts cannot
    # carry the stored rate forward and cost_eur goes NULL, so failing is better.
    fallback_max_age_days: int = 30

    @property
    def full_table(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.table}"


@dataclass(frozen=True)
class RefreshWindow:
    start_date: date
    end_date: date
    reason: str
    capped: bool = False


def resolve_refresh_window(
    latest_loaded: date | None,
    end_date: date,
    config: EcbFxRefreshConfig,
) -> RefreshWindow:
    """Decide how far back to fetch, so a gap of any length self-heals.

    A fixed `today - lookback_days` window cannot recover from an outage longer
    than the lookback: the window slides past the missing dates and nothing ever
    fetches them again. That is exactly how 2026-05-26..06-05 was lost -- the
    pipeline froze, a manual backfill caught up to 05-25, and by the time the
    release resumed on 06-14 the 7-day window only reached back to 06-08.

    So anchor the start on the stored watermark instead, and keep the fixed
    lookback as a floor so a healthy run still re-fetches recent days (ECB can
    publish late). An absurd watermark is capped rather than trusted.
    """
    default_start = end_date - timedelta(days=config.lookback_days)

    if latest_loaded is None:
        # No rows yet. A daily job should not attempt to seed all history --
        # that is what scripts/fx_rates_backfill.py is for.
        return RefreshWindow(default_start, end_date, "no_existing_rows")

    catchup_start = latest_loaded - timedelta(days=config.watermark_overlap_days)
    start_date = min(default_start, catchup_start)

    floor = end_date - timedelta(days=config.max_catchup_days)
    if start_date < floor:
        return RefreshWindow(floor, end_date, "catchup_capped", capped=True)

    reason = "watermark_catchup" if start_date < default_start else "steady_state"
    return RefreshWindow(start_date, end_date, reason)


@dataclass(frozen=True)
class EcbFxRefreshResult:
    rows_fetched: int
    rows_loaded: int
    date_range: tuple[str, str] | None
    # Set when the ECB API was unreachable and the stored rates were kept.
    fallback_reason: str | None = None
    latest_stored_date: date | None = None


def _is_transient(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


def _get_with_retry(
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str],
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """GET, retrying timeouts, connection errors and 5xx with exponential backoff.

    Anything else (a 4xx means the request itself is wrong) fails at once.
    """
    for attempt, delay in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if delay is None or not _is_transient(exc):
                raise EcbFetchFailed(
                    f"ECB fetch failed after {attempt} attempt(s): {exc}"
                ) from exc
            emit_log(
                "ecb_fx_fetch_retry",
                level="WARNING",
                attempt=attempt,
                retry_in_seconds=delay,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            sleep(delay)
    raise AssertionError("unreachable")


def _fetch_ecb_rates(
    currencies: tuple[str, ...],
    start_date: str,
    end_date: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    currency_key = "+".join(currencies)
    url = ECB_API_URL.format(currencies=currency_key)
    params = {
        "format": "csvdata",
        "startPeriod": start_date,
        "endPeriod": end_date,
    }
    headers = {"User-Agent": "gads-fx-refresh/1.0"}

    resp = _get_with_retry(url, params=params, headers=headers, sleep=sleep)

    reader = csv.DictReader(io.StringIO(resp.text))
    now = datetime.now(timezone.utc)
    rows = []

    for row in reader:
        obs_value = row.get("OBS_VALUE", "").strip()
        if not obs_value or obs_value == "NaN":
            continue

        currency = row.get("CURRENCY", "").strip()
        time_period = row.get("TIME_PERIOD", "").strip()
        if not currency or not time_period:
            continue

        ecb_rate = float(obs_value)
        rows.append({
            "currency": currency,
            "report_date": time_period,
            "ecb_rate": ecb_rate,
            "eur_exchange_rate": round(1.0 / ecb_rate, 15),
            "rate_source": "ecb_daily",
            "loaded_at": now.isoformat(),
        })

    return rows


def _latest_loaded_date(
    client: bigquery.Client,
    config: EcbFxRefreshConfig,
) -> date | None:
    """Most recent report_date already stored, for the currencies this job manages.

    Scoped to `config.currencies` deliberately. The table also carries static
    EUR/BGN rows written once by scripts/fx_rates_backfill.py, which stop at
    whatever date that run covered; letting those set the watermark would drag
    every refresh back months and re-fetch the same window forever.
    """
    query = f"""
    select max(report_date) as latest_loaded
    from `{config.full_table}`
    where currency in ({", ".join(f"'{c}'" for c in config.currencies)})
    """
    try:
        rows = list(client.query(query).result())
    except Exception as exc:  # noqa: BLE001 - missing table on first run is not fatal
        emit_log(
            "ecb_fx_refresh_watermark_unavailable",
            level="WARNING",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return None

    if not rows:
        return None
    return rows[0]["latest_loaded"]


def _fall_back_to_stored_rates(
    error: EcbFetchFailed,
    latest_loaded: date | None,
    end_date: date,
    config: EcbFxRefreshConfig,
    notifier: Callable[[str], object],
) -> EcbFxRefreshResult:
    """Keep the stored rates if they are fresh enough to carry forward, else re-raise."""
    age_days = None if latest_loaded is None else (end_date - latest_loaded).days
    if age_days is None or age_days > config.fallback_max_age_days:
        emit_log(
            "ecb_fx_refresh_fallback_unavailable",
            level="ERROR",
            latest_stored_date=latest_loaded,
            age_days=age_days,
            fallback_max_age_days=config.fallback_max_age_days,
        )
        raise error

    emit_log(
        "ecb_fx_refresh_fallback",
        level="WARNING",
        reason=str(error),
        latest_stored_date=latest_loaded,
        age_days=age_days,
    )
    notifier(
        "⚠️ ECB FX refresh: the ECB API is unreachable, so today's release keeps the "
        f"rates already stored in BigQuery (latest {latest_loaded}, {age_days} day(s) old). "
        "Reports carry that rate forward; the next run fetches the missing days.\n\n"
        f"{error}"
    )
    return EcbFxRefreshResult(
        rows_fetched=0,
        rows_loaded=0,
        date_range=None,
        fallback_reason=str(error),
        latest_stored_date=latest_loaded,
    )


def run_ecb_fx_refresh(
    config: EcbFxRefreshConfig,
    *,
    client: bigquery.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    notifier: Callable[[str], object] | None = None,
) -> EcbFxRefreshResult:
    """Fetch latest ECB rates and upsert into BigQuery.

    If the ECB API stays down after retries, keep the stored rates (and warn the
    ops chat) instead of failing, as long as they are recent enough to carry forward.
    """
    bq_client = client or bigquery.Client(project=config.project_id)

    end_date = date.today()
    latest_loaded = _latest_loaded_date(bq_client, config)
    window = resolve_refresh_window(latest_loaded, end_date, config)
    start_date = window.start_date

    if window.capped:
        emit_log(
            "ecb_fx_refresh_catchup_capped",
            level="WARNING",
            latest_loaded=latest_loaded,
            max_catchup_days=config.max_catchup_days,
            start_date=str(start_date),
        )

    emit_log(
        "ecb_fx_refresh_started",
        currencies=list(config.currencies),
        start_date=str(start_date),
        end_date=str(end_date),
        latest_loaded=latest_loaded,
        window_reason=window.reason,
        catchup_days=(end_date - start_date).days,
    )

    try:
        rows = _fetch_ecb_rates(config.currencies, str(start_date), str(end_date), sleep=sleep)
    except EcbFetchFailed as exc:
        return _fall_back_to_stored_rates(
            exc,
            latest_loaded,
            end_date,
            config,
            notifier or (lambda text: send_ops_message(text, event="ecb_fx_fallback_telegram")),
        )

    if not rows:
        emit_log("ecb_fx_refresh_no_new_rates", level="WARNING")
        return EcbFxRefreshResult(rows_fetched=0, rows_loaded=0, date_range=None)

    dates = sorted(set(r["report_date"] for r in rows))
    min_date, max_date = dates[0], dates[-1]

    # Delete existing rows in the date range for idempotent upsert
    delete_sql = f"""
    DELETE FROM `{config.full_table}`
    WHERE report_date BETWEEN '{min_date}' AND '{max_date}'
      AND currency IN ({", ".join(f"'{c}'" for c in config.currencies)})
    """
    bq_client.query(delete_sql).result()

    # Load new rows
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("currency", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("report_date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("ecb_rate", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("eur_exchange_rate", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("rate_source", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    ndjson = "\n".join(json.dumps(r) for r in rows)
    job = bq_client.load_table_from_file(
        io.BytesIO(ndjson.encode("utf-8")),
        config.full_table,
        job_config=job_config,
    )
    job.result()

    emit_log(
        "ecb_fx_refresh_completed",
        rows_fetched=len(rows),
        rows_loaded=len(rows),
        date_range=(min_date, max_date),
    )

    return EcbFxRefreshResult(
        rows_fetched=len(rows),
        rows_loaded=len(rows),
        date_range=(min_date, max_date),
    )
