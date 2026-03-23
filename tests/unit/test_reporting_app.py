from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.service import get_reporting_service, resolve_date_window


class FakeReportingService:
    def get_filter_options(self) -> dict[str, object]:
        return {
            "clients": [{"client_id": "sexwell"}],
            "accounts": [
                {
                    "client_id": "sexwell",
                    "account_id": "1200697994",
                    "account_name": "Sexwell.bg (EUR)",
                    "timezone": "Europe/Sofia",
                    "currency": "EUR",
                    "min_report_date": "2025-09-02",
                    "max_report_date": "2026-03-22",
                }
            ],
            "date_bounds": {
                "min_report_date": "2025-09-02",
                "max_report_date": "2026-03-22",
            },
            "defaults": {
                "client_id": "sexwell",
                "account_id": "1200697994",
                "date_from": "2026-02-22",
                "date_to": "2026-03-22",
            },
        }

    def get_dashboard_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": {
                "client_id": "sexwell",
                "account_id": "1200697994",
                "date_from": "2026-02-22",
                "date_to": "2026-03-22",
                "previous_date_from": "2026-01-24",
                "previous_date_to": "2026-02-21",
            },
            "summary": {
                "report_date_start": "2026-02-22",
                "report_date_end": "2026-03-22",
                "cost_eur": 1000.0,
                "conversion_value_eur": 2500.0,
                "conversions": 45.5,
                "roas": 2.5,
                "clicks": 4000,
                "impressions": 40000,
                "ctr": 0.1,
                "cpa_eur": 21.98,
            },
            "previous_summary": {
                "cost_eur": 900.0,
                "conversion_value_eur": 2000.0,
                "conversions": 40.0,
                "roas": 2.2,
                "clicks": 3500,
                "impressions": 39000,
                "ctr": 0.0897,
                "cpa_eur": 22.5,
            },
            "trend": [{"report_date": "2026-03-22", "cost_eur": 100.0, "conversion_value_eur": 200.0}],
            "campaigns": [{"campaign_name": "Brand", "cost_eur": 200.0, "conversions": 10.0, "roas": 4.0}],
            "keywords": [{"keyword_text": "sexwell", "audit_reason": "ok", "cost_eur": 50.0}],
            "search_terms": [{"search_term": "sexwell", "cost_eur": 12.0, "conversions": 0.0}],
            "alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
        }


client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_reporting_service] = lambda: FakeReportingService()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_index_renders_dashboard_shell() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Google Ads Signal Board" in response.text
    assert "Campaign explorer" in response.text


def test_filter_options_endpoint_works() -> None:
    response = client.get("/api/options")
    assert response.status_code == 200
    payload = response.json()
    assert payload["defaults"]["account_id"] == "1200697994"


def test_dashboard_endpoint_works() -> None:
    response = client.get(
        "/api/dashboard",
        params={
            "client_id": "sexwell",
            "account_id": "1200697994",
            "date_from": "2026-02-22",
            "date_to": "2026-03-22",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["cost_eur"] == 1000.0
    assert payload["campaigns"][0]["campaign_name"] == "Brand"


def test_resolve_date_window_uses_default_range() -> None:
    resolved_from, resolved_to = resolve_date_window(
        min_date=date(2026, 1, 1),
        max_date=date(2026, 3, 22),
        requested_from=None,
        requested_to=None,
        default_window_days=30,
    )
    assert resolved_from == date(2026, 2, 21)
    assert resolved_to == date(2026, 3, 22)


def test_resolve_date_window_rejects_inverted_ranges() -> None:
    try:
        resolve_date_window(
            min_date=date(2026, 1, 1),
            max_date=date(2026, 3, 22),
            requested_from=date(2026, 3, 22),
            requested_to=date(2026, 3, 1),
            default_window_days=30,
        )
    except ValueError as exc:
        assert "date_from" in str(exc)
    else:
        raise AssertionError("Expected ValueError for inverted date range")
