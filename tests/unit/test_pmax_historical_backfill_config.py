from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "scripts" / "pmax_historical_backfill.config.json"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_pmax_historical_transfer.sh"
MANAGER_SCRIPT = REPO_ROOT / "scripts" / "manage_pmax_historical_backfill.py"


class PmaxHistoricalBackfillConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG_PATH.read_text())

    def test_isolated_manual_only_history_configuration(self) -> None:
        self.assertEqual(self.config["project_id"], "gads-export-all")
        self.assertEqual(self.config["target_dataset"], "gads_pmax_creative_history")
        self.assertFalse(self.config["auto_scheduling"])
        self.assertEqual(self.config["start_date"], "2025-01-01")
        self.assertEqual(self.config["rolling_boundary"], "2026-07-03")
        self.assertEqual(self.config["max_dates_per_submission"], 1)
        self.assertEqual(self.config["max_in_flight_runs"], 1)
        self.assertEqual(self.config["attempt_cap"], 3)
        self.assertEqual(len(self.config["custom_reports"]), 3)
        self.assertNotIn("performance_label", json.dumps(self.config))

    def test_scripts_are_safe_and_dry_run_is_local(self) -> None:
        syntax_check = subprocess.run(
            ["bash", "-n", str(DEPLOY_SCRIPT)], check=False, capture_output=True, text=True
        )
        self.assertEqual(syntax_check.returncode, 0, syntax_check.stderr)
        deploy_help = subprocess.run(
            [str(DEPLOY_SCRIPT), "--help"], check=False, capture_output=True, text=True
        )
        self.assertEqual(deploy_help.returncode, 0, deploy_help.stderr)
        self.assertIn("manual-only", deploy_help.stdout)
        result = subprocess.run(
            ["python3", str(MANAGER_SCRIPT), "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Next newest-first candidate: 2026-07-02", result.stdout)

    def test_apply_requires_a_second_explicit_flag(self) -> None:
        result = subprocess.run(
            ["python3", str(MANAGER_SCRIPT), "--apply"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--confirm-submit-one-date", result.stderr)


if __name__ == "__main__":
    unittest.main()
