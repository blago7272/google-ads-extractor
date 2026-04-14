#!/usr/bin/env python3
"""Daily ECB exchange rate loader.

Fetches the latest ECB daily reference rates and appends them to BigQuery.
Designed to run as a Cloud Function or Cloud Run Job on a daily schedule
(e.g., 17:00 CET, after the ECB publishes new rates around 16:00 CET).

Usage:
  python scripts/fx_rates_daily.py [--lookback-days 5]

The --lookback-days flag re-fetches recent days to fill any gaps from weekends
or holidays. Existing rows for the same dates are replaced (idempotent).
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from fx_rates_backfill import (
    CURRENCIES,
    PROJECT_ID,
    ensure_table,
    fetch_ecb_rates,
    load_rates,
)
from google.cloud import bigquery


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily ECB rate loader")
    parser.add_argument("--lookback-days", type=int, default=5,
                        help="Number of days to look back and re-fetch (default: 5)")
    args = parser.parse_args()

    end_date = date.today()
    start_date = end_date - timedelta(days=args.lookback_days)

    rows = fetch_ecb_rates(CURRENCIES, str(start_date), str(end_date))

    if not rows:
        print("No new rates available (likely weekend/holiday). Nothing to load.")
        return

    client = bigquery.Client(project=PROJECT_ID)
    ensure_table(client)
    load_rates(client, rows)
    print("Daily rate update complete.")


if __name__ == "__main__":
    main()
