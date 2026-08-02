from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "scripts" / "pmax_rolling_refresh.config.json"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_pmax_rolling_refresh.sh"


class PmaxRollingRefreshConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG_PATH.read_text())

    def test_isolated_transfer_identity(self) -> None:
        self.assertEqual(self.config["project_id"], "gads-export-all")
        self.assertEqual(self.config["transfer_project_number"], "638625952730")
        self.assertEqual(self.config["data_source"], "google_ads")
        self.assertEqual(self.config["destination_dataset"], "gads_pmax_creative_test")
        self.assertEqual(
            self.config["transfer_config"],
            "projects/638625952730/locations/europe/transferConfigs/"
            "6a96a83d-0000-22b6-beb9-14223bb50dc6",
        )

    def test_native_daily_thirty_day_refresh(self) -> None:
        self.assertEqual(self.config["schedule"], "every day 08:00")
        self.assertEqual(self.config["schedule_timezone"], "UTC")
        self.assertEqual(self.config["refresh_window_days"], 30)
        self.assertIn("today-30, today-1", self.config["historical_boundary_rule"])

    def test_deployment_script_is_syntactically_valid_and_safe_by_default(self) -> None:
        syntax_check = subprocess.run(
            ["bash", "-n", str(DEPLOY_SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(syntax_check.returncode, 0, syntax_check.stderr)
        help_result = subprocess.run(
            [str(DEPLOY_SCRIPT), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--check", help_result.stdout)
        self.assertIn("--apply", help_result.stdout)
        self.assertIn("--seed-current-window", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
