from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MovedPaths:
    """Paths whose pages now live on another host, e.g. a client's own reporting app.

    ``exact`` paths and ``prefixes`` redirect to ``origin`` with the path and
    query string unchanged.
    """

    origin: str
    exact: frozenset[str]
    prefixes: tuple[str, ...]

    def target_for(self, path: str) -> str | None:
        if path in self.exact or path.startswith(self.prefixes):
            return self.origin + path
        return None


def parse_moved_paths(raw: str) -> tuple[MovedPaths, ...]:
    """Parse ``MOVED_PATHS_JSON``: ``{"https://new.host": ["/path", "/prefix/*"], ...}``.

    A value that is not valid is logged and ignored rather than failing startup:
    a typo here must not take the whole reporting app down.
    """

    if not raw.strip():
        return ()
    try:
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError("expected a JSON object of origin -> list of paths")
        rules = []
        for origin, paths in config.items():
            parts = urlsplit(origin)
            if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path not in {"", "/"}:
                raise ValueError(f"{origin!r} is not a bare http(s) origin")
            if not isinstance(paths, list) or not all(isinstance(p, str) and p.startswith("/") for p in paths):
                raise ValueError(f"paths for {origin!r} must be a list of strings starting with '/'")
            rules.append(
                MovedPaths(
                    origin=origin.rstrip("/"),
                    exact=frozenset(p for p in paths if not p.endswith("*")),
                    prefixes=tuple(p[:-1] for p in paths if p.endswith("*")),
                )
            )
        return tuple(rules)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        logger.error("Ignoring MOVED_PATHS_JSON: %s", exc)
        return ()


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
    # Pages that moved to another host (for example a client's own reporting
    # app). Configured per deployment; empty by default. See parse_moved_paths.
    moved_paths: tuple[MovedPaths, ...] = field(
        default_factory=lambda: parse_moved_paths(os.getenv("MOVED_PATHS_JSON", ""))
    )

    def moved_path_target(self, path: str) -> str | None:
        for rule in self.moved_paths:
            target = rule.target_for(path)
            if target:
                return target
        return None


@lru_cache(maxsize=1)
def get_settings() -> ReportingAppSettings:
    return ReportingAppSettings()
