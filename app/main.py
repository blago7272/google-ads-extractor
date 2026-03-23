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

app = FastAPI(title="Google Ads Signal Board")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    settings: ReportingAppSettings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="dashboard.html",
        request=request,
        context={
            "app_title": settings.app_title,
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


@app.get("/api/dashboard")
def dashboard_data(
    client_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: BigQueryReportingService = Depends(get_reporting_service),
) -> dict[str, object]:
    try:
        return service.get_dashboard_data(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
