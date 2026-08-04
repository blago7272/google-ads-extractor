from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

from google.cloud import bigquery_datatransfer_v1

from scripts.manage_pmax_historical_backfill import (
    main,
    rolling_transfer_active_run_count,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_CONFIG_PATH = REPO_ROOT / "scripts" / "pmax_historical_backfill.config.json"
RUNTIME_CONFIG_PATH = REPO_ROOT / "deploy" / "cloud_run" / "pmax_historical_backfill.config.json"
JOB_SCRIPT = REPO_ROOT / "deploy" / "cloud_run" / "deploy_pmax_historical_backfill.sh"
SCHEDULER_SCRIPT = REPO_ROOT / "deploy" / "cloud_run" / "create_pmax_historical_scheduler.sh"


class FakeTransferClient:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self.runs = runs
        self.request = None

    def list_transfer_runs(self, *, request: object) -> list[SimpleNamespace]:
        self.request = request
        return self.runs


class PmaxHistoricalSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.history_config = json.loads(HISTORY_CONFIG_PATH.read_text())
        self.runtime_config = json.loads(RUNTIME_CONFIG_PATH.read_text())

    def test_active_rolling_transfer_blocks_historical_submission(self) -> None:
        client = FakeTransferClient(
            [
                SimpleNamespace(state=bigquery_datatransfer_v1.TransferState.SUCCEEDED),
                SimpleNamespace(state=bigquery_datatransfer_v1.TransferState.RUNNING),
            ]
        )
        self.assertEqual(rolling_transfer_active_run_count(client, self.history_config), 1)
        self.assertEqual(client.request.parent, self.history_config["rolling_transfer_config"])
        self.assertEqual(
            {bigquery_datatransfer_v1.TransferState(value).name for value in client.request.states},
            {"PENDING", "RUNNING"},
        )

    def test_terminal_rolling_runs_do_not_block_history(self) -> None:
        client = FakeTransferClient(
            [SimpleNamespace(state=bigquery_datatransfer_v1.TransferState.SUCCEEDED)]
        )
        self.assertEqual(rolling_transfer_active_run_count(client, self.history_config), 0)

    def test_apply_exits_before_ledger_or_history_run_when_rolling_is_active(self) -> None:
        with (
            patch("scripts.manage_pmax_historical_backfill.bigquery.Client"),
            patch("scripts.manage_pmax_historical_backfill.bigquery_datatransfer_v1.DataTransferServiceClient"),
            patch("scripts.manage_pmax_historical_backfill.find_history_transfer"),
            patch(
                "scripts.manage_pmax_historical_backfill.rolling_transfer_active_run_count",
                return_value=2,
            ),
            patch("scripts.manage_pmax_historical_backfill.ensure_ledger_table") as ensure_ledger,
            patch("scripts.manage_pmax_historical_backfill.load_ledger_records") as load_ledger,
            patch.object(
                sys,
                "argv",
                [
                    "manage_pmax_historical_backfill.py",
                    "--apply",
                    "--confirm-submit-one-date",
                ],
            ),
        ):
            self.assertEqual(main(), 0)

        ensure_ledger.assert_not_called()
        load_ledger.assert_not_called()

    def test_scheduler_is_off_peak_and_single_flight(self) -> None:
        self.assertEqual(self.runtime_config["schedule"], "15 2-7 * * *")
        self.assertEqual(self.runtime_config["time_zone"], "Etc/UTC")
        self.assertEqual(self.runtime_config["tasks"], 1)
        self.assertEqual(self.runtime_config["parallelism"], 1)
        self.assertEqual(self.runtime_config["max_retries"], 0)
        self.assertEqual(
            self.runtime_config["container_args"],
            [
                "scripts/manage_pmax_historical_backfill.py",
                "--apply",
                "--confirm-submit-one-date",
            ],
        )

    def test_deployment_scripts_are_syntactically_valid_and_inert_by_default(self) -> None:
        for script in (JOB_SCRIPT, SCHEDULER_SCRIPT):
            syntax_check = subprocess.run(
                ["bash", "-n", str(script)], check=False, capture_output=True, text=True
            )
            self.assertEqual(syntax_check.returncode, 0, syntax_check.stderr)
            help_result = subprocess.run(
                [str(script), "--help"], check=False, capture_output=True, text=True
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("does not create the historical transfer", subprocess.run(
            [str(JOB_SCRIPT), "--help"], check=False, capture_output=True, text=True
        ).stdout)
        self.assertIn("02:15 through 07:15 UTC", subprocess.run(
            [str(SCHEDULER_SCRIPT), "--help"], check=False, capture_output=True, text=True
        ).stdout)


if __name__ == "__main__":
    unittest.main()
