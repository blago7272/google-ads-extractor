#!/usr/bin/env python3
"""Diagnostic script: check raw + mart data freshness for all active accounts.

Usage:
  python scripts/check_freshness.py

Requires:
  - google-cloud-bigquery
  - Authenticated gcloud session (gcloud auth application-default login)
"""

from __future__ import annotations

from datetime import datetime, timezone
from google.cloud import bigquery

PROJECT = "gads-export-all"
RAW_DATASET = "gads_raw"
CFG_DATASET = "gads_reporting_cfg"
MART_DATASET = "gads_reporting_mart"

QUERY = f"""
with active_accounts as (
  select
    client_id,
    cast(account_id as string) as account_id,
    account_name,
    timezone as account_timezone,
    currency
  from `{PROJECT}.{CFG_DATASET}.cfg_accounts`
  where is_active = true
),
raw_max_dates as (
  select
    cast(customer_id as string) as account_id,
    max(segments_date) as last_raw_date
  from `{PROJECT}.{RAW_DATASET}.p_ads_AccountStats_*`
  group by 1
),
mart_max_dates as (
  select
    account_id,
    max(report_date) as last_mart_date
  from `{PROJECT}.{MART_DATASET}.mart_ads_overview_daily`
  group by 1
)
select
  a.client_id,
  a.account_id,
  a.account_name,
  a.account_timezone,
  a.currency,
  r.last_raw_date,
  m.last_mart_date,
  date_diff(current_date(), r.last_raw_date, day) as raw_lag_days,
  date_diff(current_date(), m.last_mart_date, day) as mart_lag_days,
  case
    when r.last_raw_date is null then 'NO_RAW_DATA'
    when m.last_mart_date is null then 'RAW_OK_MART_MISSING'
    when r.last_raw_date > m.last_mart_date then 'RAW_AHEAD_OF_MART'
    when date_diff(current_date(), r.last_raw_date, day) > 3 then 'RAW_STALE'
    else 'OK'
  end as diagnosis
from active_accounts a
left join raw_max_dates r using (account_id)
left join mart_max_dates m using (account_id)
order by
  case
    when r.last_raw_date is null then 0
    when m.last_mart_date is null then 1
    when r.last_raw_date > m.last_mart_date then 2
    when date_diff(current_date(), r.last_raw_date, day) > 3 then 3
    else 4
  end,
  a.client_id, a.account_name
"""


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    print(f"Checking freshness at {datetime.now(timezone.utc).isoformat()} ...")
    print(f"{'Client':<12} {'Account Name':<35} {'Currency':<5} {'Last Raw':<12} {'Last Mart':<12} {'Raw Lag':<8} {'Mart Lag':<9} {'Diagnosis'}")
    print("-" * 140)

    rows = list(client.query(QUERY).result())
    issues = []
    for row in rows:
        raw_date = str(row["last_raw_date"] or "N/A")
        mart_date = str(row["last_mart_date"] or "N/A")
        raw_lag = str(row["raw_lag_days"]) if row["raw_lag_days"] is not None else "N/A"
        mart_lag = str(row["mart_lag_days"]) if row["mart_lag_days"] is not None else "N/A"
        diagnosis = row["diagnosis"]
        marker = " <<<" if diagnosis != "OK" else ""

        print(
            f"{row['client_id']:<12} {row['account_name'][:35]:<35} {row['currency']:<5} "
            f"{raw_date:<12} {mart_date:<12} {raw_lag:<8} {mart_lag:<9} {diagnosis}{marker}"
        )
        if diagnosis != "OK":
            issues.append(row)

    print("-" * 140)
    print(f"\nTotal active accounts: {len(rows)}")
    print(f"Accounts with issues:  {len(issues)}")

    if issues:
        print("\n--- ISSUE SUMMARY ---")
        diag_counts: dict[str, int] = {}
        for r in issues:
            d = r["diagnosis"]
            diag_counts[d] = diag_counts.get(d, 0) + 1
        for d, c in sorted(diag_counts.items()):
            print(f"  {d}: {c} account(s)")


if __name__ == "__main__":
    main()
