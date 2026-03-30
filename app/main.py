from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import (
    UserSession,
    build_google_auth_url,
    create_session_serializer,
    decode_session,
    encode_session,
    exchange_code_for_id_token,
    lookup_user_grants,
)
from app.service import BigQueryReportingService, get_reporting_service
from app.settings import ReportingAppSettings, get_settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

REPORT_PAGES = {
    "overview": {
        "title": "High-Level Overview",
        "subtitle": "KPI trend, campaign mix, and competitive context.",
    },
    "ga4-overview": {
        "title": "GA4 Overview",
        "subtitle": "Commerce KPIs, source mix, campaign mix, and product leaders from the GA4 historical export, enriched with ERP categories and GA4 brand signals.",
    },
    "ga4-impact": {
        "title": "GA4 Impact",
        "subtitle": "How source/medium and campaign shape products, categories, and brands.",
    },
    "ga4-funnel": {
        "title": "GA4 Funnel",
        "subtitle": "Views, add-to-cart, and purchase progression by channel and source.",
    },
    "ga4-timing": {
        "title": "GA4 Timing",
        "subtitle": "Hour-of-day performance and date-by-hour matrices from the GA4 export.",
    },
    "auction": {
        "title": "Auction Insights",
        "subtitle": "Daily, weekly, and monthly auction-share tables from the source export.",
    },
    "keywords": {
        "title": "Keyword and Query Audit",
        "subtitle": "Keyword issues, search terms, and spend-without-return analysis.",
    },
    "timing": {
        "title": "Timing Analysis",
        "subtitle": "Hour-of-day, day-of-week, daypart, and budget pacing patterns.",
    },
    "alerts": {
        "title": "Action Queue",
        "subtitle": "Consolidated findings and budget flags that need review.",
    },
    "efficiency": {
        "title": "Efficiency Lab",
        "subtitle": "Zero-conversion spend, winners and losers, and concentration risk.",
    },
    "coverage": {
        "title": "Query Coverage",
        "subtitle": "Search-term coverage opportunities and negative-keyword candidates.",
    },
    "creative": {
        "title": "Creative Performance",
        "subtitle": "Ad winners and losers versus the previous period.",
    },
}

app = FastAPI(title="Google Ads Signal Board")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

SOURCE_LOCAL_REPORTS = {"auction", "ga4-overview", "ga4-impact", "ga4-funnel", "ga4-timing"}
GA4_REPORTS = {"ga4-overview", "ga4-impact", "ga4-funnel", "ga4-timing"}

SESSION_COOKIE_NAME = "session"

# Paths that do not require authentication
PUBLIC_PATHS = {"/auth/login", "/auth/callback", "/auth/denied", "/healthz"}


# --- Auth middleware ---

class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to /auth/login."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths, static assets
        if path in PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)

        settings = get_settings()

        # If OAuth is not configured, bypass auth (dev convenience)
        if not settings.oauth_client_id or not settings.oauth_client_secret:
            request.state.user = None
            return await call_next(request)

        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        if not cookie:
            return RedirectResponse(url="/auth/login")

        serializer = create_session_serializer(settings.session_secret_key)
        user = decode_session(cookie, serializer, settings.session_max_age_seconds)
        if user is None:
            response = RedirectResponse(url="/auth/login")
            response.delete_cookie(SESSION_COOKIE_NAME)
            return response

        request.state.user = user
        return await call_next(request)


app.add_middleware(AuthMiddleware)


def _get_current_user(request: Request) -> UserSession | None:
    """Extract the current user from request state. Returns None if auth is bypassed."""
    return getattr(request.state, "user", None)


# --- Auth routes ---

@app.get("/auth/login")
def auth_login(settings: ReportingAppSettings = Depends(get_settings)):
    auth_url, state = build_google_auth_url(settings)
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str = Query(default=""),
    settings: ReportingAppSettings = Depends(get_settings),
):
    if not code:
        return RedirectResponse(url="/auth/login")

    try:
        id_info = exchange_code_for_id_token(code, settings)
    except Exception:
        logger.exception("OAuth token exchange failed")
        return RedirectResponse(url="/auth/login")

    email = id_info.get("email", "").lower()
    if not email:
        return RedirectResponse(url="/auth/denied")

    user = lookup_user_grants(email, settings)
    if user is None:
        return RedirectResponse(url=f"/auth/denied?email={email}")

    serializer = create_session_serializer(settings.session_secret_key)
    cookie_value = encode_session(user, serializer)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@app.get("/auth/denied", response_class=HTMLResponse)
def auth_denied(request: Request, email: str = Query(default="")):
    return templates.TemplateResponse(
        name="denied.html",
        request=request,
        context={"email": email},
    )


@app.get("/auth/logout")
def auth_logout():
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# --- Helper to build template context with user info ---

def _base_context(request: Request, settings: ReportingAppSettings, **extra) -> dict:
    user = _get_current_user(request)
    ctx = {
        "app_title": settings.app_title,
        "report_pages": REPORT_PAGES,
        "user_email": user.email if user else None,
        "user_role": user.role if user else None,
        "is_admin": user.is_admin if user else False,
    }
    ctx.update(extra)
    return ctx


# --- Page routes ---

@app.get("/", response_class=HTMLResponse)
def hub(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="hub.html",
        request=request,
        context=_base_context(
            request,
            settings,
            page_kind="hub",
            page_title=settings.app_title,
            page_subtitle="Management hub with conclusions, high-level status, and links to deeper analysis modules.",
            active_label="Main hub",
            report_name=None,
            is_source_local_report=False,
            is_ga4_report=False,
        ),
    )


@app.get("/reports/{report_name}", response_class=HTMLResponse)
def report_page(
    report_name: str,
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    if report_name not in REPORT_PAGES:
        raise HTTPException(status_code=404, detail="Unknown report page")
    return templates.TemplateResponse(
        name="report_page.html",
        request=request,
        context=_base_context(
            request,
            settings,
            page_kind="detail",
            page_title=REPORT_PAGES[report_name]["title"],
            page_subtitle=REPORT_PAGES[report_name]["subtitle"],
            active_label=REPORT_PAGES[report_name]["title"],
            report_name=report_name,
            report_title=REPORT_PAGES[report_name]["title"],
            report_subtitle=REPORT_PAGES[report_name]["subtitle"],
            is_source_local_report=report_name in SOURCE_LOCAL_REPORTS,
            is_ga4_report=report_name in GA4_REPORTS,
        ),
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# --- API routes (with auth-aware scope enforcement) ---

def _enforce_scope(request: Request, client_id: str | None, account_id: str | None) -> tuple[str | None, str | None]:
    """Enforce that the user can only query data they are authorized to see.

    For admins: pass through whatever the UI sends.
    For viewers: override client_id/account_id to their allowed values.
    If auth is bypassed (no OAuth configured): pass through.
    """
    user = _get_current_user(request)
    if user is None:
        # Auth not configured — pass through for dev
        return client_id, account_id

    if user.is_admin:
        return client_id, account_id

    # Viewer: restrict to their allowed clients
    if client_id and not user.can_access_client(client_id):
        raise HTTPException(status_code=403, detail="Access denied to this client")

    if not client_id:
        # Default to viewer's first allowed client
        if user.allowed_clients:
            client_id = user.allowed_clients[0]

    if client_id and account_id and not user.can_access_account(client_id, account_id):
        raise HTTPException(status_code=403, detail="Access denied to this account")

    return client_id, account_id


@app.get("/api/options")
def filter_options(
    request: Request,
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    try:
        options = service.get_filter_options()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    user = _get_current_user(request)
    if user is None or user.is_admin:
        return options

    # Filter options to only show what the viewer can access
    filtered_accounts = [
        acc for acc in options.get("accounts", [])
        if user.can_access_client(acc["client_id"])
        and user.can_access_account(acc["client_id"], acc["account_id"])
    ]
    filtered_clients = []
    seen = set()
    for acc in filtered_accounts:
        if acc["client_id"] not in seen:
            seen.add(acc["client_id"])
            filtered_clients.append({"client_id": acc["client_id"]})

    options = dict(options)
    options["clients"] = filtered_clients
    options["accounts"] = filtered_accounts

    if filtered_accounts:
        options["defaults"] = dict(options["defaults"])
        options["defaults"]["client_id"] = filtered_accounts[0]["client_id"]
        options["defaults"]["account_id"] = filtered_accounts[0]["account_id"]

    return options


@app.get("/api/hub")
def hub_data(
    request: Request,
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    client_id, account_id = _enforce_scope(request, client_id, account_id)
    try:
        return service.get_hub_data(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports/{report_name}")
def report_data(
    report_name: str,
    request: Request,
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    campaign_regex: str | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    client_id, account_id = _enforce_scope(request, client_id, account_id)
    try:
        return service.get_report_data(
            report_name,
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            campaign_regex=campaign_regex,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/dashboard")
def dashboard_alias(
    request: Request,
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    campaign_regex: str | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    client_id, account_id = _enforce_scope(request, client_id, account_id)
    try:
        return service.get_overview_data(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            campaign_regex=campaign_regex,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
