#!/usr/bin/env python3
"""Backfill ECB daily exchange rates into BigQuery.

Fetches historical daily reference rates from the ECB Statistical Data Warehouse
for USD, GBP, RON, MXN and loads them into a BigQuery table.

Usage:
  python scripts/fx_rates_backfill.py [--start-date 2020-01-01] [--dry-run]

The ECB rate is quoted as: 1 EUR = X foreign currency units.
We store the inverse: eur_exchange_rate = 1/X (i.e., how many EUR per 1 unit of
foreign currency), matching the existing cfg_exchange_rates convention.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date, datetime, timezone
from typing import Any

import requests
from google.cloud import bigquery

PROJECT_ID = "gads-export-all"
DATASET_ID = "gads_reporting_cfg"
TABLE_ID = "ecb_exchange_rates_daily"
FULL_TABLE = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# Currencies to fetch (exclude EUR which is base=1.0, and BGN which is a fixed peg)
CURRENCIES = ["USD", "GBP", "RON", "MXN"]

ECB_API_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"
)

SCHEMA = [
    bigquery.SchemaField("currency", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("report_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("ecb_rate", "FLOAT64", mode="REQUIRED",
                         description="ECB reference rate: 1 EUR = X units of currency"),
    bigquery.SchemaField("eur_exchange_rate", "FLOAT64", mode="REQUIRED",
                         description="Inverse rate: 1 unit of currency = X EUR"),
    bigquery.SchemaField("rate_source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
]


def fetch_ecb_rates(
    currencies: list[str],
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Fetch daily exchange rates from the ECB SDMX REST API."""
    currency_key = "+".join(currencies)
    url = ECB_API_URL.format(currencies=currency_key)
    params = {
        "format": "csvdata",
        "startPeriod": start_date,
        "endPeriod": end_date,
    }
    headers = {"User-Agent": "gads-fx-backfill/1.0"}

    print(f"Fetching ECB rates for {currency_key} from {start_date} to {end_date} ...")
    resp = requests.get(url, params=params, headers=headers, timeout=120)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    now = datetime.now(timezone.utc)

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

    print(f"  Parsed {len(rows)} rate records.")
    return rows


def ensure_table(client: bigquery.Client) -> None:
    """Create the target table if it doesn't exist."""
    table_ref = bigquery.Table(FULL_TABLE, schema=SCHEMA)
    table_ref.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="report_date",
    )
    table_ref.clustering_fields = ["currency"]

    try:
        client.get_table(FULL_TABLE)
        print(f"Table {FULL_TABLE} already exists.")
    except Exception:
        client.create_table(table_ref)
        print(f"Created table {FULL_TABLE}.")


def load_rates(client: bigquery.Client, rows: list[dict[str, Any]]) -> None:
    """Load rate rows into BigQuery, replacing any existing data for the same dates."""
    if not rows:
        print("No rows to load.")
        return

    # Find date range in the batch
    dates = sorted(set(r["report_date"] for r in rows))
    min_date, max_date = dates[0], dates[-1]

    # Delete existing rows in this date range to allow idempotent re-runs
    delete_sql = f"""
    DELETE FROM `{FULL_TABLE}`
    WHERE report_date BETWEEN '{min_date}' AND '{max_date}'
      AND currency IN ({", ".join(f"'{c}'" for c in CURRENCIES)})
    """
    print(f"Clearing existing rows for {min_date} to {max_date} ...")
    client.query(delete_sql).result()

    # Insert new rows
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    import json
    ndjson = "\n".join(json.dumps(r) for r in rows)
    job = client.load_table_from_file(
        io.BytesIO(ndjson.encode("utf-8")),
        FULL_TABLE,
        job_config=job_config,
    )
    job.result()
    print(f"Loaded {len(rows)} rows into {FULL_TABLE}.")


def add_static_rates(client: bigquery.Client) -> None:
    """Add EUR (base) and BGN (fixed peg) as static rows if not present."""
    check_sql = f"SELECT count(*) as cnt FROM `{FULL_TABLE}` WHERE currency = 'EUR' LIMIT 1"
    result = list(client.query(check_sql).result())
    if result[0].cnt > 0:
        print("Static EUR/BGN rows already present, skipping.")
        return

    # Generate one row per business day for EUR and BGN across the full date range
    insert_sql = f"""
    INSERT INTO `{FULL_TABLE}` (currency, report_date, ecb_rate, eur_exchange_rate, rate_source, loaded_at)
    WITH date_spine AS (
      SELECT report_date
      FROM (SELECT DISTINCT report_date FROM `{FULL_TABLE}`)
    )
    SELECT 'EUR', report_date, 1.0, 1.0, 'base_currency', CURRENT_TIMESTAMP()
    FROM date_spine
    UNION ALL
    SELECT 'BGN', report_date, 1.95583, 0.5112918811962185, 'fixed_peg', CURRENT_TIMESTAMP()
    FROM date_spine
    """
    print("Adding static EUR and BGN rows ...")
    client.query(insert_sql).result()
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ECB exchange rates into BigQuery")
    parser.add_argument("--start-date", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=str(date.today()), help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch rates but don't load")
    args = parser.parse_args()

    rows = fetch_ecb_rates(CURRENCIES, args.start_date, args.end_date)

    if args.dry_run:
        print("\n--- DRY RUN: sample rows ---")
        for r in rows[:10]:
            print(f"  {r['report_date']}  {r['currency']}  ecb={r['ecb_rate']:.4f}  eur={r['eur_exchange_rate']:.6f}")
        print(f"  ... ({len(rows)} total rows)")
        return

    client = bigquery.Client(project=PROJECT_ID)
    ensure_table(client)
    load_rates(client, rows)
    add_static_rates(client)

    # Final summary
    summary_sql = f"""
    SELECT currency, count(*) as days, min(report_date) as first_date, max(report_date) as last_date
    FROM `{FULL_TABLE}`
    GROUP BY 1 ORDER BY 1
    """
    print("\n--- TABLE SUMMARY ---")
    for row in client.query(summary_sql).result():
        print(f"  {row.currency}: {row.days} days ({row.first_date} to {row.last_date})")


if __name__ == "__main__":
    main()
