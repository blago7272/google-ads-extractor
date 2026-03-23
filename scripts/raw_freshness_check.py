#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.logging_utils import emit_log
from orchestration.raw_freshness import (  # noqa: E402
    failing_accounts_payload,
    parse_timestamp,
    run_raw_freshness_probe,
    RawFreshnessConfig,
)


def main() -> int:
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Check raw Google Ads freshness for active accounts.")
    parser.add_argument("--project-id", default="gads-export-all")
    parser.add_argument("--cfg-dataset", default="gads_reporting_cfg")
    parser.add_argument("--cfg-accounts-table", default="cfg_accounts")
    parser.add_argument("--raw-dataset", default="gads_raw")
    parser.add_argument("--raw-account-stats-pattern", default="p_ads_AccountStats_*")
    parser.add_argument("--max-allowed-lag-days", type=int, default=0)
    parser.add_argument("--execution-ts", help="Optional ISO-8601 timestamp override.")
    parser.add_argument("--verbose", action="store_true", help="Emit per-account results.")
    args = parser.parse_args()

    execution_ts = (
        parse_timestamp(args.execution_ts)
        if args.execution_ts
        else datetime.now(timezone.utc)
    )
    config = RawFreshnessConfig(
        project_id=args.project_id,
        cfg_dataset=args.cfg_dataset,
        cfg_accounts_table=args.cfg_accounts_table,
        raw_dataset=args.raw_dataset,
        raw_account_stats_pattern=args.raw_account_stats_pattern,
        max_allowed_lag_days=args.max_allowed_lag_days,
        execution_ts=execution_ts,
    )

    results, summary = run_raw_freshness_probe(config)
    emit_log(
        "raw_freshness_check_completed",
        account_count=summary.account_count,
        ready_count=summary.ready_count,
        failing_count=summary.failing_count,
        max_allowed_lag_days=summary.max_allowed_lag_days,
        checked_at=summary.checked_at,
    )

    if args.verbose:
        for result in results:
            emit_log(
                "raw_freshness_account",
                client_id=result.client_id,
                account_id=result.account_id,
                account_timezone=result.account_timezone,
                expected_last_date=result.expected_last_date,
                last_raw_date=result.last_raw_date,
                days_lag=result.days_lag,
                freshness_status=result.freshness_status,
            )

    if summary.is_ready:
        return 0

    emit_log(
        "raw_freshness_check_failed",
        level="ERROR",
        failing_accounts=failing_accounts_payload(results),
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
