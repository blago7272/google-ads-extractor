#!/usr/bin/env python3
"""Safely plan or submit one newest-first PMax historical date at a time."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.cloud import bigquery_datatransfer_v1

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.pmax_historical_backfill import (  # noqa: E402
    HistoryPolicy,
    LedgerRecord,
    next_eligible_dates,
)


LEDGER_SCHEMA = (
    bigquery.SchemaField("source_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("attempt_count", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("transfer_run_name", "STRING"),
    bigquery.SchemaField("submitted_at", "TIMESTAMP"),
    bigquery.SchemaField("completed_at", "TIMESTAMP"),
    bigquery.SchemaField("last_error", "STRING"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD.") from exc


def policy_from_config(config: dict[str, Any]) -> HistoryPolicy:
    return HistoryPolicy(
        start_date=parse_date(config["start_date"]),
        rolling_boundary=parse_date(config["rolling_boundary"]),
        attempt_cap=int(config["attempt_cap"]),
        retry_delay=timedelta(hours=int(config["retry_delay_hours"])),
    )


def table_id(config: dict[str, Any]) -> str:
    return f"{config['project_id']}.{config['target_dataset']}.{config['ledger_table']}"


def state_name(value: Any) -> str:
    if hasattr(value, "name"):
        return value.name
    try:
        return bigquery_datatransfer_v1.TransferState(value).name
    except (TypeError, ValueError):
        return str(value).rsplit(".", maxsplit=1)[-1]


def rolling_transfer_active_run_count(
    client: bigquery_datatransfer_v1.DataTransferServiceClient, config: dict[str, Any]
) -> int:
    """Count active rolling runs before permitting a history submission.

    A read failure deliberately propagates: a scheduler must not fail open and
    compete with the daily rolling refresh when its state cannot be determined.
    """
    active_states = frozenset(config["rolling_active_states"])
    request = bigquery_datatransfer_v1.ListTransferRunsRequest(
        parent=config["rolling_transfer_config"],
        states=[getattr(bigquery_datatransfer_v1.TransferState, state) for state in active_states],
    )
    return sum(
        state_name(run.state) in active_states
        for run in client.list_transfer_runs(request=request)
    )


def find_history_transfer(
    client: bigquery_datatransfer_v1.DataTransferServiceClient, config: dict[str, Any]
) -> Any:
    parent = (
        f"projects/{config['transfer_project_number']}"
        f"/locations/{config['transfer_location']}"
    )
    matches = [
        transfer
        for transfer in client.list_transfer_configs(parent=parent)
        if transfer.display_name == config["display_name"]
        and transfer.data_source_id == config["data_source"]
        and transfer.destination_dataset_id == config["target_dataset"]
    ]
    if not matches:
        raise RuntimeError(
            "The historical transfer is not deployed. Obtain approval and run "
            "scripts/deploy_pmax_historical_transfer.sh --apply first."
        )
    if len(matches) != 1:
        raise RuntimeError("Multiple transfers match the historical-transfer identity.")
    transfer = matches[0]
    if getattr(transfer, "schedule", ""):
        raise RuntimeError("Refusing a historical transfer that has automatic scheduling enabled.")
    return transfer


def ensure_ledger_table(client: bigquery.Client, config: dict[str, Any]) -> None:
    identifier = table_id(config)
    table = bigquery.Table(identifier, schema=LEDGER_SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(field="source_date")
    client.create_table(table, exists_ok=True)


def load_ledger_records(
    client: bigquery.Client, config: dict[str, Any], policy: HistoryPolicy
) -> dict[date, LedgerRecord]:
    query = f"""
        SELECT source_date, status, attempt_count, updated_at, transfer_run_name
        FROM `{table_id(config)}`
        WHERE source_date >= @start_date
          AND source_date < @rolling_boundary
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", policy.start_date),
            bigquery.ScalarQueryParameter(
                "rolling_boundary", "DATE", policy.rolling_boundary
            ),
        ]
    )
    return {
        row.source_date: LedgerRecord(
            source_date=row.source_date,
            status=row.status,
            attempt_count=row.attempt_count,
            updated_at=row.updated_at,
            transfer_run_name=row.transfer_run_name,
        )
        for row in client.query(query, job_config=job_config).result()
    }


def upsert_ledger_record(
    client: bigquery.Client,
    config: dict[str, Any],
    record: LedgerRecord,
    submitted_at: datetime | None,
    completed_at: datetime | None,
    last_error: str | None = None,
) -> None:
    query = f"""
        MERGE `{table_id(config)}` AS target
        USING (SELECT @source_date AS source_date) AS source
        ON target.source_date = source.source_date
        WHEN MATCHED THEN UPDATE SET
          status = @status,
          attempt_count = @attempt_count,
          transfer_run_name = @transfer_run_name,
          submitted_at = @submitted_at,
          completed_at = @completed_at,
          last_error = @last_error,
          updated_at = @updated_at
        WHEN NOT MATCHED THEN INSERT
          (source_date, status, attempt_count, transfer_run_name, submitted_at,
           completed_at, last_error, updated_at)
        VALUES
          (@source_date, @status, @attempt_count, @transfer_run_name,
           @submitted_at, @completed_at, @last_error, @updated_at)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("source_date", "DATE", record.source_date),
            bigquery.ScalarQueryParameter("status", "STRING", record.status),
            bigquery.ScalarQueryParameter("attempt_count", "INT64", record.attempt_count),
            bigquery.ScalarQueryParameter(
                "transfer_run_name", "STRING", record.transfer_run_name
            ),
            bigquery.ScalarQueryParameter("submitted_at", "TIMESTAMP", submitted_at),
            bigquery.ScalarQueryParameter("completed_at", "TIMESTAMP", completed_at),
            bigquery.ScalarQueryParameter("last_error", "STRING", last_error),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", record.updated_at),
        ]
    )
    client.query(query, job_config=job_config).result()


def reconcile_active_records(
    table_client: bigquery.Client,
    transfer_client: bigquery_datatransfer_v1.DataTransferServiceClient,
    config: dict[str, Any],
    records: dict[date, LedgerRecord],
    now: datetime,
) -> dict[date, LedgerRecord]:
    """Persist terminal transfer states before considering the next submission."""
    for source_date, record in tuple(records.items()):
        if record.status.upper() not in {"PENDING", "RUNNING"} or not record.transfer_run_name:
            continue
        try:
            run = transfer_client.get_transfer_run(name=record.transfer_run_name)
        except Exception:  # A missing run is intentionally left active to avoid duplicates.
            continue
        state = state_name(run.state)
        if state in {"PENDING", "RUNNING"}:
            continue
        updated = LedgerRecord(
            source_date=source_date,
            status=state,
            attempt_count=record.attempt_count,
            updated_at=now,
            transfer_run_name=record.transfer_run_name,
        )
        error = getattr(run, "error_status", None)
        error_message = getattr(error, "message", None) if error else None
        upsert_ledger_record(
            table_client,
            config,
            updated,
            submitted_at=None,
            completed_at=now if state in {"SUCCEEDED", "FAILED", "CANCELLED"} else None,
            last_error=error_message,
        )
        records[source_date] = updated
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "scripts" / "pmax_historical_backfill.config.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the ledger and submit at most one manual historical date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly select the default local-only planning mode.",
    )
    parser.add_argument(
        "--confirm-submit-one-date",
        action="store_true",
        help="Required with --apply; prevents accidental execution.",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run cannot be used together.")

    config = json.loads(args.config.read_text())
    policy = policy_from_config(config)
    if int(config["max_dates_per_submission"]) != 1 or int(config["max_in_flight_runs"]) != 1:
        raise RuntimeError("Historical safety policy requires exactly one submitted/in-flight date.")

    now = datetime.now(timezone.utc)
    if not args.apply:
        candidate = next_eligible_dates(policy, {}, now, limit=1)
        print("Dry run only; no credentials or cloud resources were used.")
        print(f"Historical range: {policy.start_date.isoformat()} through {(policy.rolling_boundary - timedelta(days=1)).isoformat()}")
        print("Next newest-first candidate: " + (candidate[0].isoformat() if candidate else "none"))
        return 0
    if not args.confirm_submit_one_date:
        raise RuntimeError("--apply requires --confirm-submit-one-date.")

    table_client = bigquery.Client(project=config["project_id"])
    transfer_client = bigquery_datatransfer_v1.DataTransferServiceClient()
    transfer = find_history_transfer(transfer_client, config)
    active_rolling_runs = rolling_transfer_active_run_count(transfer_client, config)
    if active_rolling_runs:
        print(
            "Rolling PMax transfer has "
            f"{active_rolling_runs} active run(s); no historical date was submitted."
        )
        return 0
    ensure_ledger_table(table_client, config)
    records = load_ledger_records(table_client, config, policy)
    records = reconcile_active_records(table_client, transfer_client, config, records, now)
    if any(record.status.upper() in {"PENDING", "RUNNING"} for record in records.values()):
        print("An historical transfer is still active; no additional date was submitted.")
        return 0

    candidate = next_eligible_dates(policy, records, now, limit=1)
    if not candidate:
        print("No eligible historical date remains; inspect the ledger for capped or unknown states.")
        return 0

    source_date = candidate[0]
    response = transfer_client.start_manual_transfer_runs(
        request=bigquery_datatransfer_v1.StartManualTransferRunsRequest(
            parent=transfer.name,
            requested_run_time=datetime.combine(
                source_date, datetime.min.time(), tzinfo=timezone.utc
            ),
        )
    )
    if len(response.runs) != 1:
        raise RuntimeError("Expected exactly one transfer run for a single historical date.")
    previous = records.get(source_date)
    record = LedgerRecord(
        source_date=source_date,
        status="PENDING",
        attempt_count=(previous.attempt_count if previous else 0) + 1,
        updated_at=now,
        transfer_run_name=response.runs[0].name,
    )
    upsert_ledger_record(table_client, config, record, submitted_at=now, completed_at=None)
    print(f"Submitted historical date {source_date.isoformat()}: {record.transfer_run_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
