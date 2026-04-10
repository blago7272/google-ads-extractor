from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ReportingAppSettings:
    project_id: str = os.getenv("REPORTING_PROJECT_ID", os.getenv("DBT_PROJECT_ID", "gads-export-all"))
    mart_dataset: str = os.getenv("REPORTING_MART_DATASET", "gads_reporting_mart")
    cfg_dataset: str = os.getenv("REPORTING_CFG_DATASET", "gads_reporting_cfg")
    auth_cfg_dataset: str = os.getenv("REPORTING_AUTH_CFG_DATASET", "gads_reporting_cfg")
    default_window_days: int = int(os.getenv("REPORTING_DEFAULT_WINDOW_DAYS", "30"))
    app_title: str = os.getenv("REPORTING_APP_TITLE", "Google Ads Signal Board")
    options_cache_ttl_seconds: int = int(os.getenv("REPORTING_OPTIONS_CACHE_TTL_SECONDS", "3600"))
    freshness_cache_ttl_seconds: int = int(os.getenv("REPORTING_FRESHNESS_CACHE_TTL_SECONDS", "300"))
    query_cache_ttl_seconds: int = int(os.getenv("REPORTING_QUERY_CACHE_TTL_SECONDS", "900"))
    query_cache_max_entries: int = int(os.getenv("REPORTING_QUERY_CACHE_MAX_ENTRIES", "256"))
    oauth_client_id: str = os.getenv("OAUTH_CLIENT_ID", "")
    oauth_client_secret: str = os.getenv("OAUTH_CLIENT_SECRET", "")
    oauth_redirect_uri: str = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    session_secret_key: str = os.getenv("SESSION_SECRET_KEY", "change-me-in-production")
    session_max_age_seconds: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "86400"))


@lru_cache(maxsize=1)
def get_settings() -> ReportingAppSettings:
    return ReportingAppSettings()
