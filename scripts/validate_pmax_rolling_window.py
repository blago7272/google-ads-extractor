#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from google.cloud import bigquery
from google.cloud import bigquery_datatransfer_v1

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.pmax_rolling_validation import (  # noqa: E402
    latest_state_by_run_date,
    rolling_window_dates,
    window_state_summary,
)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD.") from exc


def expected_view_dates(
    client: bigquery.Client,
    project_id: str,
    dataset: str,
    view_name: str,
    window_start: date,
    window_end_exclusive: date,
) -> set[date]:
    query = f"""
        SELECT DISTINCT segments_date
        FROM `{project_id}.{dataset}.{view_name}`
        WHERE segments_date >= @window_start
          AND segments_date < @window_end_exclusive
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("window_start", "DATE", window_start),
            bigquery.ScalarQueryParameter(
                "window_end_exclusive", "DATE", window_end_exclusive
            ),
        ]
    )
    return {row.segments_date for row in client.query(query, job_config=job_config).result()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a completed 30-day isolated PMax rolling window."
    )
    parser.add_argument(
        "--window-end-exclusive",
        type=parse_date,
        help="UTC date after the final expected source date; defaults to UTC today.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "scripts" / "pmax_rolling_refresh.config.json",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    window_end_exclusive = args.window_end_exclusive or datetime.now(timezone.utc).date()
    expected_dates = rolling_window_dates(
        window_end_exclusive, int(config["refresh_window_days"])
    )

    transfer_client = bigquery_datatransfer_v1.DataTransferServiceClient()
    runs = transfer_client.list_transfer_runs(parent=config["transfer_config"])
    states = latest_state_by_run_date(runs)
    succeeded, incomplete, failed = window_state_summary(expected_dates, states)

    print(
        "Rolling run states: "
        f"{len(succeeded)} succeeded, {len(incomplete)} incomplete, {len(failed)} failed."
    )
    if incomplete:
        print("Incomplete dates: " + ", ".join(value.isoformat() for value in incomplete))
    if failed:
        print("Failed dates: " + ", ".join(value.isoformat() for value in failed))
    if incomplete or failed:
        return 1

    table_client = bigquery.Client(project=config["project_id"])
    expected_set = set(expected_dates)
    missing_by_view: dict[str, set[date]] = {}
    for view_name in config["report_views"]:
        actual_dates = expected_view_dates(
            table_client,
            config["project_id"],
            config["destination_dataset"],
            view_name,
            expected_dates[0],
            window_end_exclusive,
        )
        missing_dates = expected_set - actual_dates
        if missing_dates:
            missing_by_view[view_name] = missing_dates

    if missing_by_view:
        for view_name, missing_dates in missing_by_view.items():
            print(
                f"{view_name} missing dates: "
                + ", ".join(value.isoformat() for value in sorted(missing_dates))
            )
        return 1

    print(
        f"Accepted rolling window: {expected_dates[0].isoformat()} through "
        f"{expected_dates[-1].isoformat()} across {len(config['report_views'])} views."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
