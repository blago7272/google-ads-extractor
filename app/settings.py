from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


# Never redirected, whatever MOVED_PATHS_JSON says: sign-in, the app's own
# assets, and health checks must keep working even with an over-broad rule.
NEVER_MOVED_PREFIXES = ("/auth/", "/static/")
NEVER_MOVED_PATHS = frozenset({"/healthz", "/_ah/health"})


def is_never_moved(path: str) -> bool:
    return path in NEVER_MOVED_PATHS or path.startswith(NEVER_MOVED_PREFIXES)


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
        if is_never_moved(path):
            return None
        if path in self.exact or path.startswith(self.prefixes):
            return self.origin + path
        return None


def _origin_problem(origin: str) -> str | None:
    """Why ``origin`` is not a bare http(s) origin, or None if it is one."""

    parts = urlsplit(origin)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "not an http(s) origin"
    if parts.username is not None or parts.password is not None:
        return "contains credentials"
    # Check the characters, not the parsed parts: "https://host?" parses with an
    # empty query but would still produce "https://host?/path".
    if "?" in origin:
        return "contains a query string"
    if "#" in origin:
        return "contains a fragment"
    if parts.path not in {"", "/"}:
        return "contains a path"
    return None


def parse_moved_paths(raw: str) -> tuple[MovedPaths, ...]:
    """Parse ``MOVED_PATHS_JSON``: ``{"https://new.host": ["/path", "/prefix/*"], ...}``.

    Nothing here fails startup: a typo must not take the reporting app down.
    Unparseable JSON, or anything but an object, is logged and ignored as a
    whole. An origin that is not a bare http(s) origin (credentials, query,
    fragment, path), or whose path list is malformed, is logged and skipped;
    the other origins still apply.
    """

    if not raw.strip():
        return ()
    try:
        config = json.loads(raw)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        logger.error("Ignoring MOVED_PATHS_JSON: %s", exc)
        return ()
    if not isinstance(config, dict):
        logger.error("Ignoring MOVED_PATHS_JSON: expected a JSON object of origin -> list of paths")
        return ()

    rules = []
    for origin, paths in config.items():
        problem = _origin_problem(origin)
        if problem:
            logger.warning("Skipping MOVED_PATHS_JSON origin %r: %s", origin, problem)
            continue
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.startswith("/") for p in paths):
            logger.warning(
                "Skipping MOVED_PATHS_JSON origin %r: paths must be a list of strings starting with '/'", origin
            )
            continue
        rule = MovedPaths(
            origin=origin.rstrip("/"),
            exact=frozenset(p for p in paths if not p.endswith("*")),
            prefixes=tuple(p[:-1] for p in paths if p.endswith("*")),
        )
        protected = (*NEVER_MOVED_PREFIXES, *NEVER_MOVED_PATHS)
        shadowed = sorted(
            {p for p in rule.exact if is_never_moved(p)}
            # A prefix rule overlaps if it lies inside, or contains, a protected path.
            | {f"{q}*" for q in rule.prefixes if is_never_moved(q) or any(n.startswith(q) for n in protected)}
        )
        if shadowed:
            logger.warning(
                "MOVED_PATHS_JSON rules %s for %r overlap paths that are never redirected (%s, %s)",
                shadowed, origin, ", ".join(NEVER_MOVED_PREFIXES), ", ".join(sorted(NEVER_MOVED_PATHS)),
            )
        rules.append(rule)
    return tuple(rules)


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
