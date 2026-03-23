from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ReportingAppSettings:
    project_id: str = os.getenv("REPORTING_PROJECT_ID", os.getenv("DBT_PROJECT_ID", "gads-export-all"))
    mart_dataset: str = os.getenv("REPORTING_MART_DATASET", "gads_reporting_mart")
    cfg_dataset: str = os.getenv("REPORTING_CFG_DATASET", "gads_reporting_cfg")
    default_window_days: int = int(os.getenv("REPORTING_DEFAULT_WINDOW_DAYS", "30"))
    app_title: str = os.getenv("REPORTING_APP_TITLE", "Google Ads Signal Board")


@lru_cache(maxsize=1)
def get_settings() -> ReportingAppSettings:
    return ReportingAppSettings()
