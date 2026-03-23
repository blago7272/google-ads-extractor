from __future__ import annotations

import argparse
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from orchestration.dbt_cli import DbtRuntimeConfig, parse_select_tokens, run_dbt_build, run_dbt_seeds, run_dbt_tests
from orchestration.logging_utils import emit_log
from orchestration.raw_freshness import (
    AccountFreshnessResult,
    RawFreshnessConfig,
    RawFreshnessGateFailed,
    RawFreshnessSummary,
    failing_accounts_payload,
    parse_timestamp,
    run_raw_freshness_probe,
)
from orchestration.schema_mapping import resolve_schema_name


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ReleaseOrchestratorConfig:
    raw_freshness: RawFreshnessConfig
    dbt_runtime: DbtRuntimeConfig
    stage_target: str = "stage"
    prod_target: str = "prod"
    skip_prod: bool = False
    stop_after_step: str | None = None


@dataclass(frozen=True)
class ReleaseOutcome:
    completed_steps: tuple[str, ...]
    freshness_summary: RawFreshnessSummary
    prod_skipped: bool


class ReleaseStepFailed(RuntimeError):
    def __init__(self, step_name: str, reason: str):
        super().__init__(f"{step_name} failed: {reason}")
        self.step_name = step_name
        self.reason = reason


def _run_step(step_name: str, action: Callable[[], None], completed_steps: list[str]) -> None:
    started = time.monotonic()
    emit_log("release_step_started", step=step_name)
    try:
        action()
    except Exception as exc:  # noqa: BLE001
        emit_log(
            "release_step_failed",
            level="ERROR",
            step=step_name,
            duration_seconds=round(time.monotonic() - started, 3),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise ReleaseStepFailed(step_name, str(exc)) from exc

    completed_steps.append(step_name)
    emit_log(
        "release_step_completed",
        step=step_name,
        duration_seconds=round(time.monotonic() - started, 3),
    )


def run_release(
    config: ReleaseOrchestratorConfig,
    *,
    freshness_probe: Callable[[RawFreshnessConfig], tuple[list[AccountFreshnessResult], RawFreshnessSummary]] = run_raw_freshness_probe,
    dbt_build_runner: Callable[[str, DbtRuntimeConfig], None] = run_dbt_build,
    dbt_seed_runner: Callable[[str, DbtRuntimeConfig], None] = run_dbt_seeds,
    dbt_test_runner: Callable[[str, DbtRuntimeConfig], None] = run_dbt_tests,
) -> ReleaseOutcome:
    emit_log(
        "release_started",
        stage_target=config.stage_target,
        prod_target=config.prod_target,
        skip_prod=config.skip_prod,
        stop_after_step=config.stop_after_step,
        execution_ts=config.raw_freshness.execution_ts,
    )

    completed_steps: list[str] = []
    freshness_results: list[AccountFreshnessResult] = []
    freshness_summary: RawFreshnessSummary | None = None
    bq_client = bigquery.Client(project=config.raw_freshness.project_id)

    def raw_freshness_gate() -> None:
        nonlocal freshness_results, freshness_summary
        freshness_results, freshness_summary = freshness_probe(config.raw_freshness)
        emit_log(
            "raw_freshness_summary",
            account_count=freshness_summary.account_count,
            ready_count=freshness_summary.ready_count,
            failing_count=freshness_summary.failing_count,
            max_allowed_lag_days=freshness_summary.max_allowed_lag_days,
            checked_at=freshness_summary.checked_at,
        )
        if not freshness_summary.is_ready:
            emit_log(
                "raw_freshness_gate_failed",
                level="ERROR",
                failing_accounts=failing_accounts_payload(freshness_results),
            )
            raise RawFreshnessGateFailed(freshness_summary)

    _run_step("raw_freshness_gate", raw_freshness_gate, completed_steps)
    assert freshness_summary is not None
    if config.stop_after_step == "raw_freshness_gate":
        emit_log("release_completed", completed_steps=completed_steps, prod_skipped=True)
        return ReleaseOutcome(tuple(completed_steps), freshness_summary, True)

    def ensure_seed_state(target: str) -> None:
        if config.dbt_runtime.run_seeds:
            emit_log("seed_sync_requested", target=target)
            dbt_seed_runner(target, config.dbt_runtime)
            return

        if not config.dbt_runtime.bootstrap_missing_seeds:
            return

        cfg_schema = resolve_schema_name("gads_reporting_cfg", target)
        missing_tables: list[str] = []
        for table_name in config.dbt_runtime.required_seed_tables:
            relation = f"{config.raw_freshness.project_id}.{cfg_schema}.{table_name}"
            try:
                bq_client.get_table(relation)
            except NotFound:
                missing_tables.append(table_name)

        if missing_tables:
            emit_log(
                "seed_bootstrap_required",
                target=target,
                cfg_schema=cfg_schema,
                missing_tables=missing_tables,
            )
            dbt_seed_runner(target, config.dbt_runtime)
            emit_log("seed_bootstrap_completed", target=target, cfg_schema=cfg_schema)

    ensure_seed_state(config.stage_target)

    _run_step(
        "stage_build",
        lambda: dbt_build_runner(config.stage_target, config.dbt_runtime),
        completed_steps,
    )
    if config.stop_after_step == "stage_build":
        emit_log("release_completed", completed_steps=completed_steps, prod_skipped=True)
        return ReleaseOutcome(tuple(completed_steps), freshness_summary, True)

    _run_step(
        "stage_test",
        lambda: dbt_test_runner(config.stage_target, config.dbt_runtime),
        completed_steps,
    )
    if config.stop_after_step == "stage_test":
        emit_log("release_completed", completed_steps=completed_steps, prod_skipped=True)
        return ReleaseOutcome(tuple(completed_steps), freshness_summary, True)

    if config.skip_prod:
        emit_log("prod_release_skipped", reason="skip_prod flag")
        emit_log("release_completed", completed_steps=completed_steps, prod_skipped=True)
        return ReleaseOutcome(tuple(completed_steps), freshness_summary, True)

    ensure_seed_state(config.prod_target)

    _run_step(
        "prod_build",
        lambda: dbt_build_runner(config.prod_target, config.dbt_runtime),
        completed_steps,
    )
    if config.stop_after_step == "prod_build":
        emit_log("release_completed", completed_steps=completed_steps, prod_skipped=False)
        return ReleaseOutcome(tuple(completed_steps), freshness_summary, False)

    _run_step(
        "prod_test",
        lambda: dbt_test_runner(config.prod_target, config.dbt_runtime),
        completed_steps,
    )

    emit_log("release_completed", completed_steps=completed_steps, prod_skipped=False)
    return ReleaseOutcome(tuple(completed_steps), freshness_summary, False)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the reporting release orchestration flow.")
    parser.add_argument("--project-id", default=os.getenv("DBT_PROJECT_ID", "gads-export-all"))
    parser.add_argument("--cfg-dataset", default=os.getenv("CFG_DATASET", "gads_reporting_cfg"))
    parser.add_argument("--cfg-accounts-table", default=os.getenv("CFG_ACCOUNTS_TABLE", "cfg_accounts"))
    parser.add_argument("--raw-dataset", default=os.getenv("RAW_DATASET", "gads_raw"))
    parser.add_argument(
        "--raw-account-stats-pattern",
        default=os.getenv("RAW_ACCOUNT_STATS_PATTERN", "p_ads_AccountStats_*"),
    )
    parser.add_argument(
        "--max-allowed-lag-days",
        type=int,
        default=int(os.getenv("RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS", "0")),
    )
    parser.add_argument(
        "--execution-ts",
        default=os.getenv("RELEASE_EXECUTION_TS"),
        help="Optional ISO-8601 timestamp override for release evaluation.",
    )
    parser.add_argument("--dbt-bin", default=os.getenv("DBT_BIN", "dbt"))
    parser.add_argument(
        "--dbt-project-dir",
        default=os.getenv("DBT_PROJECT_DIR", str(_repo_root())),
    )
    parser.add_argument("--dbt-profiles-dir", default=os.getenv("DBT_PROFILES_DIR"))
    parser.add_argument("--stage-target", default=os.getenv("STAGE_DBT_TARGET", "stage"))
    parser.add_argument("--prod-target", default=os.getenv("PROD_DBT_TARGET", "prod"))
    parser.add_argument("--skip-prod", action="store_true", default=_env_bool("SKIP_PROD"))
    parser.add_argument("--stop-after-step", choices=("raw_freshness_gate", "stage_build", "stage_test", "prod_build"))
    parser.add_argument("--run-seeds", action="store_true", default=_env_bool("DBT_RUN_SEEDS"))
    parser.add_argument(
        "--no-bootstrap-missing-seeds",
        action="store_true",
        default=False,
        help="Disable automatic dbt seed bootstrap when target config tables are missing.",
    )
    parser.add_argument(
        "--staging-select",
        default=os.getenv("DBT_STAGING_SELECT"),
        help="Whitespace-separated dbt select tokens for staging runs.",
    )
    parser.add_argument(
        "--mart-select",
        default=os.getenv("DBT_MART_SELECT"),
        help="Whitespace-separated dbt select tokens for mart runs.",
    )
    parser.add_argument(
        "--test-select",
        default=os.getenv("DBT_TEST_SELECT"),
        help="Whitespace-separated dbt select tokens for dbt test.",
    )
    parser.add_argument(
        "--seed-select",
        default=os.getenv("DBT_SEED_SELECT"),
        help="Whitespace-separated dbt select tokens for dbt seed.",
    )
    parser.add_argument(
        "--no-full-refresh-marts",
        action="store_true",
        default=False,
        help="Disable --full-refresh on mart builds.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    execution_ts = (
        parse_timestamp(args.execution_ts)
        if args.execution_ts
        else datetime.now(timezone.utc)
    )

    raw_freshness = RawFreshnessConfig(
        project_id=args.project_id,
        cfg_dataset=args.cfg_dataset,
        cfg_accounts_table=args.cfg_accounts_table,
        raw_dataset=args.raw_dataset,
        raw_account_stats_pattern=args.raw_account_stats_pattern,
        max_allowed_lag_days=args.max_allowed_lag_days,
        execution_ts=execution_ts,
    )
    dbt_runtime = DbtRuntimeConfig(
        dbt_bin=args.dbt_bin,
        project_dir=Path(args.dbt_project_dir),
        profiles_dir=Path(args.dbt_profiles_dir) if args.dbt_profiles_dir else None,
        run_seeds=args.run_seeds,
        bootstrap_missing_seeds=not args.no_bootstrap_missing_seeds,
        full_refresh_marts=not args.no_full_refresh_marts,
        staging_select=parse_select_tokens(args.staging_select, ("path:models/staging/google_ads", "path:models/staging/manual")),
        mart_select=parse_select_tokens(args.mart_select, ("path:models/marts/reporting",)),
        test_select=parse_select_tokens(args.test_select, ()),
        seed_select=parse_select_tokens(args.seed_select, ()),
    )
    config = ReleaseOrchestratorConfig(
        raw_freshness=raw_freshness,
        dbt_runtime=dbt_runtime,
        stage_target=args.stage_target,
        prod_target=args.prod_target,
        skip_prod=args.skip_prod,
        stop_after_step=args.stop_after_step,
    )

    try:
        run_release(config)
    except ReleaseStepFailed as exc:
        emit_log("release_failed", level="ERROR", step=exc.step_name, reason=exc.reason)
        return 1
    except subprocess.CalledProcessError as exc:
        emit_log("release_failed", level="ERROR", error_type="CalledProcessError", returncode=exc.returncode)
        return exc.returncode or 1
    except Exception as exc:  # noqa: BLE001
        emit_log("release_failed", level="ERROR", error_type=type(exc).__name__, error_message=str(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
