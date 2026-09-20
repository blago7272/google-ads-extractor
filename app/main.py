from __future__ import annotations

import json
import logging
import re
import secrets
from calendar import month_abbr, monthrange
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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

SEXWELL_CLIENT_ID = "sexwell"
SEXWELL_BUSINESS_REPORTS_DIR = BASE_DIR / "private_reports" / SEXWELL_CLIENT_ID
SEXWELL_BUSINESS_REPORTS = {
    "dashboard": "dashboard.html",
    "sexwell_order_value_tiers_2026-09-17_v04.html": "sexwell_order_value_tiers_2026-09-17_v04.html",
    "sexwell_category_dynamics_2026-09-17_v11.html": "sexwell_category_dynamics_2026-09-17_v11.html",
    "sexwell_product_revenue_concentration_2026-09-17_v06.html": "sexwell_product_revenue_concentration_2026-09-17_v06.html",
}
SEXWELL_DISCOUNT_SERIES_PATTERN = re.compile(
    r"const ORDER_EXPORT_DISCOUNTED_ORDER_RATE=(\{.*?\});",
    re.DOTALL,
)

app = FastAPI(title="Google Ads Signal Board")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

SOURCE_LOCAL_REPORTS = {"auction", "ga4-overview", "ga4-impact", "ga4-funnel", "ga4-timing"}
GA4_REPORTS = {"ga4-overview", "ga4-impact", "ga4-funnel", "ga4-timing"}
SESSION_COOKIE_NAME = "session"
OAUTH_STATE_COOKIE_NAME = "oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 600
PUBLIC_PATHS = {"/auth/login", "/auth/callback", "/auth/denied", "/healthz"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)

        settings = get_settings()

        # Local/dev convenience: if OAuth is not configured, bypass auth.
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
    return getattr(request.state, "user", None)


def _base_context(request: Request, settings: ReportingAppSettings, **extra) -> dict[str, object]:
    user = _get_current_user(request)
    context: dict[str, object] = {
        "app_title": settings.app_title,
        "report_pages": REPORT_PAGES,
        "user_email": user.email if user else None,
        "user_role": user.role if user else None,
        "is_admin": user.is_admin if user else False,
        "sexwell_home_url": "/clients/sexwell"
        if user and user.can_access_client(SEXWELL_CLIENT_ID)
        else None,
    }
    context.update(extra)
    return context


def _is_dedicated_sexwell_user(request: Request) -> bool:
    """Give single-client SexWell users a focused post-login entry point."""

    user = _get_current_user(request)
    return bool(
        user
        and not user.is_admin
        and user.allowed_clients == [SEXWELL_CLIENT_ID]
        and user.can_access_client(SEXWELL_CLIENT_ID)
    )


def _require_sexwell_access(request: Request) -> None:
    """Use the same client scope boundary as the reporting API."""

    user = _get_current_user(request)
    if user is not None and not user.can_access_client(SEXWELL_CLIENT_ID):
        raise HTTPException(status_code=403, detail="Access denied to this client")


def _render_ads_hub(request: Request, settings: ReportingAppSettings) -> HTMLResponse:
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


def _json_literal_span(
    html: str,
    marker: str,
) -> tuple[object, int, int] | None:
    marker_start = html.find(marker)
    if marker_start < 0:
        return None
    value_start = marker_start + len(marker)
    try:
        value, value_length = json.JSONDecoder().raw_decode(html[value_start:])
    except json.JSONDecodeError:
        return None
    return value, value_start, value_start + value_length


def _replace_json_literal(html: str, marker: str, value: object) -> str:
    located = _json_literal_span(html, marker)
    if located is None:
        return html
    _, start, end = located
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return html[:start] + payload + html[end:]


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_day(value: date) -> str:
    return f"{month_abbr[value.month]} {value.day}"


def _inject_sexwell_live_data(
    html: str,
    discount_rows: list[dict[str, object]],
    ads_rows: list[dict[str, object]],
) -> str:
    """Refresh compatible report literals while preserving the approved UI."""

    mon_located = _json_literal_span(html, "const MON=")
    daily_located = _json_literal_span(html, "DAILY_CPT=")
    if mon_located is None or daily_located is None:
        return html

    monthly = mon_located[0]
    daily = daily_located[0]
    if not isinstance(monthly, list) or not isinstance(daily, list):
        return html

    discount_by_month: dict[tuple[int, int], dict[str, object]] = {}
    discount_dates: list[date] = []
    for row in discount_rows:
        try:
            key = (int(row["year"]), int(row["month"]))
        except (KeyError, TypeError, ValueError):
            continue
        discount_by_month[key] = row
        data_through = _coerce_date(row.get("data_through"))
        if data_through is not None:
            discount_dates.append(data_through)

    ads_by_date: dict[date, dict[str, object]] = {}
    for row in ads_rows:
        report_date = _coerce_date(row.get("report_date"))
        if report_date is None or row.get("cost_eur") is None:
            continue
        ads_by_date[report_date] = row

    ads_by_month: dict[tuple[int, int], list[tuple[date, dict[str, object]]]] = {}
    for report_date, row in ads_by_date.items():
        ads_by_month.setdefault((report_date.year, report_date.month), []).append(
            (report_date, row)
        )
    for rows in ads_by_month.values():
        rows.sort(key=lambda item: item[0])

    latest_ads_date = max(ads_by_date, default=None)
    latest_discount_date = max(discount_dates, default=None)
    erp_dates = [
        parsed
        for row in daily
        if isinstance(row, dict)
        for parsed in [_coerce_date(row.get("date"))]
        if parsed is not None
    ]
    erp_data_through = max(erp_dates, default=None)

    monthly_by_key = {
        (int(row["year"]), int(row["month"])): row
        for row in monthly
        if isinstance(row, dict) and "year" in row and "month" in row
    }
    for key, row in monthly_by_key.items():
        discount = discount_by_month.get(key)
        if discount is not None and discount.get("discounted_order_share_pct") is not None:
            row["disc_rate"] = round(float(discount["discounted_order_share_pct"]), 4)

        month_ads = ads_by_month.get(key)
        if not month_ads or latest_ads_date is None:
            continue
        dates = [item[0] for item in month_ads]
        expected_days = monthrange(key[0], key[1])[1]
        complete_month = (
            dates[0].day == 1
            and dates[-1].day == expected_days
            and len(set(dates)) == expected_days
        )
        latest_month = key == (latest_ads_date.year, latest_ads_date.month)
        if not complete_month and not latest_month:
            continue

        row["ad_spend"] = round(sum(float(item[1]["cost_eur"]) for item in month_ads), 2)
        matched_ads = month_ads
        if erp_data_through is not None and key == (erp_data_through.year, erp_data_through.month):
            matched_ads = [item for item in month_ads if item[0] <= erp_data_through]
        matched_spend = sum(float(item[1]["cost_eur"]) for item in matched_ads)
        if matched_spend and row.get("net_merch_rev") is not None:
            row["roas"] = round(float(row["net_merch_rev"]) / matched_spend, 2)

    for row in daily:
        if not isinstance(row, dict):
            continue
        report_date = _coerce_date(row.get("date"))
        ad = ads_by_date.get(report_date) if report_date is not None else None
        if ad is None:
            continue
        spend = round(float(ad["cost_eur"]), 2)
        row["ad_spend"] = spend
        row["impressions"] = int(ad["impressions"])
        row["clicks"] = int(ad["clicks"])
        gross_transactions = row.get("gross_txn")
        row["cost_per_gross_txn"] = (
            round(spend / float(gross_transactions), 2) if gross_transactions else None
        )

    sep_key = (2026, 9)
    sep_monthly = monthly_by_key.get(sep_key)
    mtd_located = _json_literal_span(html, "MTDSEP=")
    mtd = mtd_located[0] if mtd_located is not None else None
    if isinstance(mtd, dict) and sep_monthly is not None:
        for field in ("disc_rate", "ad_spend", "roas"):
            if field in sep_monthly:
                mtd[field] = sep_monthly[field]

    projection_located = _json_literal_span(html, "PROJSEP=")
    projection = projection_located[0] if projection_located is not None else None
    if (
        isinstance(projection, dict)
        and sep_monthly is not None
        and latest_ads_date is not None
        and (latest_ads_date.year, latest_ads_date.month) == sep_key
    ):
        projection["ad_spend"] = round(
            float(sep_monthly["ad_spend"])
            * monthrange(latest_ads_date.year, latest_ads_date.month)[1]
            / latest_ads_date.day,
            2,
        )
        projection["roas"] = sep_monthly.get("roas")

    html = _replace_json_literal(html, "const MON=", monthly)
    html = _replace_json_literal(html, "MTDSEP=", mtd) if isinstance(mtd, dict) else html
    html = (
        _replace_json_literal(html, "PROJSEP=", projection)
        if isinstance(projection, dict)
        else html
    )
    html = _replace_json_literal(html, "DAILY_CPT=", daily)

    match = SEXWELL_DISCOUNT_SERIES_PATTERN.search(html)
    if match is not None and discount_by_month:
        series = json.loads(match.group(1))
        for (year, month), row in discount_by_month.items():
            year_key = str(year)
            month_index = month - 1
            share = row.get("discounted_order_share_pct")
            if (
                share is None
                or year_key not in series
                or month_index < 0
                or month_index >= len(series[year_key])
            ):
                continue
            series[year_key][month_index] = round(float(share), 4)
        replacement = (
            "const ORDER_EXPORT_DISCOUNTED_ORDER_RATE="
            + json.dumps(series, ensure_ascii=False, separators=(",", ":"))
            + ";"
        )
        html = html[: match.start()] + replacement + html[match.end() :]

    if discount_by_month:
        html = html.replace(
            "The discount series shows the WebSite export’s ",
            "The discount series combines Site Admin history through March 2026 with ID Consult API data from April 2026 and shows the ",
        )
        html = html.replace(
            "Validated Orders export: Discount > 0 OR Subtotal discount > 0",
            "Site Admin history; ID Consult API from Apr 2026: Discount > 0 OR Subtotal discount > 0",
        )

    if (
        latest_ads_date is not None
        and latest_discount_date is not None
        and erp_data_through is not None
        and latest_ads_date.year == latest_discount_date.year == erp_data_through.year == 2026
        and latest_ads_date.month == latest_discount_date.month == erp_data_through.month == 9
    ):
        ads_label = _month_day(latest_ads_date)
        discount_label = _month_day(latest_discount_date)
        erp_label = _month_day(erp_data_through)
        old_caveat = (
            "Google Ads, Selmatic sales and completed-order discount share use the same September actual-to-date window through Sep 16; "
            "the separate September run-rate estimates sales and Google Ads spend linearly. "
            "Daily cost-per-transaction is available for Jul 1–28 and Aug 1–31."
        )
        new_caveat = (
            f"September data cutoffs are metric-specific: Google Ads spend through {ads_label}; "
            f"Selmatic sales and ROAS through {erp_label}; completed-order discount share through {discount_label}. "
            f"The separate September run-rate estimates sales from {erp_data_through.day} observed days and Google Ads spend from {latest_ads_date.day} observed days. "
            f"Daily cost-per-transaction remains matched to ERP and is available for Jul 1–28, Aug 1–31 and Sep 1–{erp_data_through.day}."
        )
        html = html.replace(old_caveat, new_caveat)
        html = html.replace(
            "<b>September estimate:</b> sales, order-volume and Google Ads spend are extrapolated from 16 observed days. AOV, items per order, discount share and ROAS retain the matched Sep 1–16 level.",
            f"<b>September estimate:</b> sales and order-volume are extrapolated from {erp_data_through.day} observed days; Google Ads spend is extrapolated from {latest_ads_date.day} observed days. AOV, items per order and ROAS retain the matched Sep 1–{erp_data_through.day} level; discount share is actual through {discount_label}.",
        )
        html = html.replace(
            "September sales, completed-order discount share, Google Ads spend and ROAS use the matched Sep 1–16 window.",
            f"September Selmatic sales and ROAS use the matched Sep 1–{erp_data_through.day} window; completed-order discount share is current through {discount_label}, and Google Ads spend through {ads_label}.",
        )
        html = html.replace(
            "function actualCutoff(key,y,m){if(m===9)return 16;",
            f"function actualCutoff(key,y,m){{if(m===9){{if(key==='ad_spend')return {latest_ads_date.day};if(key==='disc_rate')return {latest_discount_date.day};return {erp_data_through.day};}}",
        )
        html = html.replace(
            "r.year===2026&&r.month===9?' (actual through Sep 16)':sp?",
            "r.year===2026&&r.month===9?' (actual through Sep '+actualCutoff(kpi.key,r.year,r.month)+')':sp?",
        )
        html = html.replace(
            "2026-09 (linear sales and Google Ads run-rate estimate from Sep 1–16)",
            f"2026-09 (sales estimate from Sep 1–{erp_data_through.day}; Google Ads run-rate from Sep 1–{latest_ads_date.day})",
        )
        html = html.replace(
            "r.year===2026&&r.month===9?' (actual through Sep 16; Google Ads actual)'",
            f"r.year===2026&&r.month===9?' (sales/ROAS through Sep {erp_data_through.day}; discount through Sep {latest_discount_date.day}; Google Ads through Sep {latest_ads_date.day})'",
        )

    return html


def _request_uses_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _set_oauth_state_cookie(response: RedirectResponse, request: Request, state: str) -> None:
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_request_uses_https(request),
        path="/auth/callback",
    )


def _clear_oauth_state_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/auth/callback")


@app.get("/auth/login")
def auth_login(request: Request, settings: ReportingAppSettings = Depends(get_settings)):
    auth_url, state = build_google_auth_url(settings)
    response = RedirectResponse(url=auth_url)
    _set_oauth_state_cookie(response, request, state)
    return response


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    settings: ReportingAppSettings = Depends(get_settings),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME, "")
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        response = RedirectResponse(url="/auth/login")
        _clear_oauth_state_cookie(response)
        return response

    if not code:
        response = RedirectResponse(url="/auth/login")
        _clear_oauth_state_cookie(response)
        return response

    try:
        id_info = exchange_code_for_id_token(code, settings)
        email = id_info.get("email", "").lower()
        if not email:
            response = RedirectResponse(url="/auth/denied")
            _clear_oauth_state_cookie(response)
            return response
        user = lookup_user_grants(email, settings)
        if user is None:
            response = RedirectResponse(url=f"/auth/denied?email={email}")
            _clear_oauth_state_cookie(response)
            return response
    except Exception:
        logger.exception("OAuth login failed")
        response = RedirectResponse(url="/auth/login")
        _clear_oauth_state_cookie(response)
        return response

    serializer = create_session_serializer(settings.session_secret_key)
    cookie_value = encode_session(user, serializer)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=_request_uses_https(request),
    )
    _clear_oauth_state_cookie(response)
    return response


@app.get("/auth/denied", response_class=HTMLResponse)
def auth_denied(request: Request, email: str = Query(default="")):
    return templates.TemplateResponse(name="denied.html", request=request, context={"email": email})


@app.get("/auth/logout")
def auth_logout():
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
def hub(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    if _is_dedicated_sexwell_user(request):
        return templates.TemplateResponse(
            name="sexwell_home.html",
            request=request,
            context=_base_context(
                request,
                settings,
                page_kind="client-home",
                page_title="SexWell reporting",
                page_subtitle="",
                active_label="SexWell reporting",
                report_name=None,
                is_source_local_report=False,
                is_ga4_report=False,
            ),
        )

    return _render_ads_hub(request, settings)


@app.get("/ads", response_class=HTMLResponse)
def ads_hub(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    """Keep the established Google Ads hub reachable from client workspaces."""

    return _render_ads_hub(request, settings)


@app.get("/clients/sexwell", response_class=HTMLResponse)
def sexwell_home(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    _require_sexwell_access(request)
    return templates.TemplateResponse(
        name="sexwell_home.html",
        request=request,
        context=_base_context(
            request,
            settings,
            page_kind="client-home",
            page_title="SexWell reporting",
            page_subtitle="",
            active_label="SexWell reporting",
            report_name=None,
            is_source_local_report=False,
            is_ga4_report=False,
        ),
    )


@app.get("/business-results")
def business_results(
    request: Request,
    reporting_service: BigQueryReportingService = Depends(get_reporting_service),
) -> HTMLResponse:
    """Serve the aggregate-only SexWell dashboard within the existing access scope."""

    _require_sexwell_access(request)
    dashboard = (
        SEXWELL_BUSINESS_REPORTS_DIR / SEXWELL_BUSINESS_REPORTS["dashboard"]
    ).read_text(encoding="utf-8")
    discount_rows = reporting_service.get_sexwell_discount_prevalence()
    ads_rows = reporting_service.get_sexwell_google_ads_daily()
    return HTMLResponse(
        content=_inject_sexwell_live_data(dashboard, discount_rows, ads_rows),
    )


@app.get("/business-results/assets/{report_name}")
def business_results_asset(report_name: str, request: Request):
    """Serve dashboard sub-reports only after the same SexWell access check."""

    _require_sexwell_access(request)
    file_name = SEXWELL_BUSINESS_REPORTS.get(report_name)
    if file_name is None or report_name == "dashboard":
        raise HTTPException(status_code=404, detail="Unknown business-results asset")
    return FileResponse(SEXWELL_BUSINESS_REPORTS_DIR / file_name, media_type="text/html")


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


def _enforce_scope(
    request: Request,
    client_id: str | None,
    account_id: str | None,
) -> tuple[str | None, str | None]:
    user = _get_current_user(request)
    if user is None:
        return client_id, account_id
    if user.is_admin:
        return client_id, account_id

    if client_id and not user.can_access_client(client_id):
        raise HTTPException(status_code=403, detail="Access denied to this client")

    if not client_id and user.allowed_clients:
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

    filtered_accounts = [
        acc
        for acc in options.get("accounts", [])
        if user.can_access_client(acc["client_id"])
        and user.can_access_account(acc["client_id"], acc["account_id"])
    ]

    filtered_clients = []
    seen_clients: set[str] = set()
    for acc in filtered_accounts:
        if acc["client_id"] not in seen_clients:
            seen_clients.add(acc["client_id"])
            filtered_clients.append({"client_id": acc["client_id"]})

    filtered = dict(options)
    filtered["clients"] = filtered_clients
    filtered["accounts"] = filtered_accounts
    if filtered_accounts:
        filtered["defaults"] = dict(filtered["defaults"])
        filtered["defaults"]["client_id"] = filtered_accounts[0]["client_id"]
        filtered["defaults"]["account_id"] = filtered_accounts[0]["account_id"]
    return filtered


@app.get("/api/freshness")
def freshness_data(
    request: Request,
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    client_id, account_id = _enforce_scope(request, client_id, account_id)
    try:
        return service.get_freshness_data(client_id=client_id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    timing_matrix_days: int | None = Query(default=None, ge=1, le=90),
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
            timing_matrix_days=timing_matrix_days,
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
