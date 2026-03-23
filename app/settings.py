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
    options_cache_ttl_seconds: int = int(os.getenv("REPORTING_OPTIONS_CACHE_TTL_SECONDS", "3600"))
    query_cache_ttl_seconds: int = int(os.getenv("REPORTING_QUERY_CACHE_TTL_SECONDS", "900"))
    query_cache_max_entries: int = int(os.getenv("REPORTING_QUERY_CACHE_MAX_ENTRIES", "256"))


@lru_cache(maxsize=1)
def get_settings() -> ReportingAppSettings:
    return ReportingAppSettings()
