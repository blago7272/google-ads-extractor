from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.service import BigQueryReportingService, get_reporting_service
from app.settings import ReportingAppSettings, get_settings

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


@app.get("/", response_class=HTMLResponse)
def hub(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="hub.html",
        request=request,
        context={
            "app_title": settings.app_title,
            "page_kind": "hub",
            "page_title": settings.app_title,
            "page_subtitle": "Management hub with conclusions, high-level status, and links to deeper analysis modules.",
            "active_label": "Main hub",
            "report_name": None,
            "report_pages": REPORT_PAGES,
            "is_source_local_report": False,
            "is_ga4_report": False,
        },
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
        context={
            "app_title": settings.app_title,
            "page_kind": "detail",
            "page_title": REPORT_PAGES[report_name]["title"],
            "page_subtitle": REPORT_PAGES[report_name]["subtitle"],
            "active_label": REPORT_PAGES[report_name]["title"],
            "report_name": report_name,
            "report_title": REPORT_PAGES[report_name]["title"],
            "report_subtitle": REPORT_PAGES[report_name]["subtitle"],
            "report_pages": REPORT_PAGES,
            "is_source_local_report": report_name in SOURCE_LOCAL_REPORTS,
            "is_ga4_report": report_name in GA4_REPORTS,
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/options")
def filter_options(
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    try:
        return service.get_filter_options()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/hub")
def hub_data(
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
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
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    campaign_regex: str | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
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
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    campaign_regex: str | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
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
