from __future__ import annotations

from datetime import datetime, timezone
import unittest

from orchestration.dbt_cli import DbtRuntimeConfig
from orchestration.raw_freshness import RawFreshnessConfig, RawFreshnessSummary
from orchestration.release_orchestrator import ReleaseOrchestratorConfig, run_release


class ReleaseOrchestratorTest(unittest.TestCase):
    def _config(self, **overrides: object) -> ReleaseOrchestratorConfig:
        config = ReleaseOrchestratorConfig(
            raw_freshness=RawFreshnessConfig(
                project_id="gads-export-all",
                execution_ts=datetime(2026, 3, 23, 6, 30, tzinfo=timezone.utc),
            ),
            dbt_runtime=DbtRuntimeConfig(bootstrap_missing_seeds=False),
        )
        data = {
            "raw_freshness": config.raw_freshness,
            "dbt_runtime": config.dbt_runtime,
            "stage_target": config.stage_target,
            "prod_target": config.prod_target,
            "skip_prod": config.skip_prod,
            "include_stage": config.include_stage,
            "stop_after_step": config.stop_after_step,
        }
        data.update(overrides)
        return ReleaseOrchestratorConfig(**data)

    def test_daily_release_skips_stage_and_goes_straight_to_prod(self) -> None:
        calls: list[tuple[str, str]] = []
        summary = RawFreshnessSummary(
            account_count=1,
            ready_count=1,
            failing_count=0,
            max_allowed_lag_days=0,
            checked_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
            failing_accounts=(),
        )

        def fake_probe(_config: RawFreshnessConfig):
            return [], summary

        def fake_build(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("build", target))

        def fake_test(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("test", target))

        def fake_alert(*_args: object, **_kwargs: object) -> None:
            calls.append(("alert", "freshness"))

        outcome = run_release(
            self._config(),
            freshness_probe=fake_probe,
            dbt_build_runner=fake_build,
            dbt_test_runner=fake_test,
            skipped_accounts_alert_runner=fake_alert,
        )

        self.assertEqual(
            calls,
            [("alert", "freshness"), ("build", "prod"), ("test", "prod")],
        )
        self.assertEqual(
            outcome.completed_steps,
            (
                "raw_freshness_gate",
                "skipped_accounts_alert",
                "ecb_fx_refresh",
                "prod_build",
                "prod_test",
            ),
        )
        self.assertFalse(outcome.prod_skipped)

    def test_release_does_not_block_on_stale_accounts(self) -> None:
        # Soft freshness gate: a stale account must NOT fail the release.
        # Stale accounts are excluded at the mart layer by the selective-freshness
        # models and auto-rejoin once their raw data resumes, so the pipeline
        # proceeds through every step instead of blocking everyone.
        calls: list[tuple[str, str]] = []
        summary = RawFreshnessSummary(
            account_count=2,
            ready_count=1,
            failing_count=1,
            max_allowed_lag_days=3,
            checked_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
            failing_accounts=(),
        )

        def fake_probe(_config: RawFreshnessConfig):
            return [], summary

        def fake_build(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("build", target))

        def fake_test(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("test", target))

        def fake_alert(*_args: object, **_kwargs: object) -> None:
            calls.append(("alert", "freshness"))

        outcome = run_release(
            self._config(),
            freshness_probe=fake_probe,
            dbt_build_runner=fake_build,
            dbt_test_runner=fake_test,
            skipped_accounts_alert_runner=fake_alert,
        )

        self.assertEqual(
            outcome.completed_steps,
            (
                "raw_freshness_gate",
                "skipped_accounts_alert",
                "ecb_fx_refresh",
                "prod_build",
                "prod_test",
            ),
        )
        self.assertEqual(
            calls,
            [("alert", "freshness"), ("build", "prod"), ("test", "prod")],
        )
        self.assertFalse(outcome.prod_skipped)

    def test_release_can_stop_after_stage_test(self) -> None:
        calls: list[tuple[str, str]] = []
        summary = RawFreshnessSummary(
            account_count=1,
            ready_count=1,
            failing_count=0,
            max_allowed_lag_days=0,
            checked_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
            failing_accounts=(),
        )

        def fake_probe(_config: RawFreshnessConfig):
            return [], summary

        def fake_build(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("build", target))

        def fake_test(target: str, _runtime: DbtRuntimeConfig) -> None:
            calls.append(("test", target))

        def fake_alert(*_args: object, **_kwargs: object) -> None:
            calls.append(("alert", "freshness"))

        outcome = run_release(
            self._config(stop_after_step="stage_test"),
            freshness_probe=fake_probe,
            dbt_build_runner=fake_build,
            dbt_test_runner=fake_test,
            skipped_accounts_alert_runner=fake_alert,
        )

        self.assertEqual(calls, [("alert", "freshness"), ("build", "stage"), ("test", "stage")])
        self.assertEqual(outcome.completed_steps, (
                "raw_freshness_gate",
                "skipped_accounts_alert",
                "ecb_fx_refresh",
                "stage_build",
                "stage_test",
            ))
        self.assertTrue(outcome.prod_skipped)

    def _run(self, **overrides: object) -> tuple[list[tuple[str, str]], object]:
        calls: list[tuple[str, str]] = []
        summary = RawFreshnessSummary(
            account_count=1,
            ready_count=1,
            failing_count=0,
            max_allowed_lag_days=0,
            checked_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
            failing_accounts=(),
        )
        outcome = run_release(
            self._config(**overrides),
            freshness_probe=lambda _c: ([], summary),
            dbt_build_runner=lambda target, _r: calls.append(("build", target)),
            dbt_test_runner=lambda target, _r: calls.append(("test", target)),
            skipped_accounts_alert_runner=lambda *_a, **_k: None,
        )
        return calls, outcome

    def test_include_stage_runs_stage_before_prod(self) -> None:
        calls, outcome = self._run(include_stage=True)

        self.assertEqual(
            calls,
            [("build", "stage"), ("test", "stage"), ("build", "prod"), ("test", "prod")],
        )
        self.assertIn("stage_build", outcome.completed_steps)
        self.assertFalse(outcome.prod_skipped)

    def test_skip_prod_still_runs_stage_for_ci(self) -> None:
        # A stage-only CI run must not become a no-op just because stage is now
        # off by default -- skip_prod implies the stage half.
        calls, outcome = self._run(skip_prod=True)

        self.assertEqual(calls, [("build", "stage"), ("test", "stage")])
        self.assertEqual(outcome.completed_steps[-2:], ("stage_build", "stage_test"))
        self.assertTrue(outcome.prod_skipped)

    def test_stage_datasets_are_untouched_on_the_daily_path(self) -> None:
        calls, _ = self._run()

        self.assertNotIn("stage", [target for _action, target in calls])


if __name__ == "__main__":
    unittest.main()
