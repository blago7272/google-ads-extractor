from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from orchestration.logging_utils import emit_log


DEFAULT_STAGING_SELECT = (
    "path:models/staging/google_ads",
    "path:models/staging/manual",
)
DEFAULT_MART_SELECT = ("path:models/marts/reporting",)
DEFAULT_REQUIRED_SEED_TABLES = (
    "cfg_accounts",
    "cfg_account_groups",
    "cfg_thresholds",
    "cfg_exchange_rates",
    "cfg_segments",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_select_tokens(raw_value: str | None, default: Sequence[str]) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return tuple(default)
    return tuple(shlex.split(raw_value))


@dataclass(frozen=True)
class DbtRuntimeConfig:
    dbt_bin: str = "dbt"
    project_dir: Path = field(default_factory=_repo_root)
    profiles_dir: Path | None = None
    run_seeds: bool = False
    bootstrap_missing_seeds: bool = True
    full_refresh_marts: bool = True
    staging_select: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_STAGING_SELECT))
    mart_select: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_MART_SELECT))
    test_select: tuple[str, ...] = field(default_factory=tuple)
    seed_select: tuple[str, ...] = field(default_factory=tuple)
    required_seed_tables: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_REQUIRED_SEED_TABLES))


def build_dbt_seed_command(target: str, config: DbtRuntimeConfig) -> list[str]:
    command = [config.dbt_bin, "seed", "--target", target, "--full-refresh"]
    if config.seed_select:
        command.extend(["--select", *config.seed_select])
    return command


def build_dbt_commands(target: str, config: DbtRuntimeConfig) -> list[list[str]]:
    commands: list[list[str]] = []
    if config.staging_select:
        commands.append([config.dbt_bin, "run", "--target", target, "--select", *config.staging_select])

    mart_command = [config.dbt_bin, "run", "--target", target]
    if config.full_refresh_marts:
        mart_command.append("--full-refresh")
    if config.mart_select:
        mart_command.extend(["--select", *config.mart_select])
    commands.append(mart_command)

    return commands


def build_dbt_test_command(target: str, config: DbtRuntimeConfig) -> list[str]:
    command = [config.dbt_bin, "test", "--target", target]
    if config.test_select:
        command.extend(["--select", *config.test_select])
    return command


def run_dbt_command(command: Sequence[str], config: DbtRuntimeConfig, *, step_name: str) -> None:
    env = os.environ.copy()
    if config.profiles_dir is not None:
        env["DBT_PROFILES_DIR"] = str(config.profiles_dir)

    emit_log(
        "dbt_command_started",
        step=step_name,
        command=shlex.join(command),
        project_dir=str(config.project_dir),
        profiles_dir=str(config.profiles_dir) if config.profiles_dir else None,
    )
    subprocess.run(command, cwd=config.project_dir, env=env, check=True)
    emit_log("dbt_command_completed", step=step_name, command=shlex.join(command))


def run_dbt_seeds(target: str, config: DbtRuntimeConfig) -> None:
    run_dbt_command(build_dbt_seed_command(target, config), config, step_name=f"{target}_seed")


def run_dbt_build(target: str, config: DbtRuntimeConfig) -> None:
    for index, command in enumerate(build_dbt_commands(target, config), start=1):
        run_dbt_command(command, config, step_name=f"{target}_build_command_{index}")


def run_dbt_tests(target: str, config: DbtRuntimeConfig) -> None:
    run_dbt_command(build_dbt_test_command(target, config), config, step_name=f"{target}_test")
