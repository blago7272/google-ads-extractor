"""Refresh ECB daily exchange rates as part of the release pipeline.

Fetches the latest ECB reference rates for the configured currencies and
upserts them into the `ecb_exchange_rates_daily` table in BigQuery.
Uses a 7-day lookback window to fill any gaps from weekends or holidays.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from google.cloud import bigquery

from orchestration.logging_utils import emit_log

ECB_API_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"
)


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


def _fetch_ecb_rates(
    currencies: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    currency_key = "+".join(currencies)
    url = ECB_API_URL.format(currencies=currency_key)
    params = {
        "format": "csvdata",
        "startPeriod": start_date,
        "endPeriod": end_date,
    }
    headers = {"User-Agent": "gads-fx-refresh/1.0"}

    resp = requests.get(url, params=params, headers=headers, timeout=60)
    resp.raise_for_status()

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


def run_ecb_fx_refresh(
    config: EcbFxRefreshConfig,
    *,
    client: bigquery.Client | None = None,
) -> EcbFxRefreshResult:
    """Fetch latest ECB rates and upsert into BigQuery."""
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

    rows = _fetch_ecb_rates(config.currencies, str(start_date), str(end_date))

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
