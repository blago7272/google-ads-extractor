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

    def _overview_payload(self) -> dict[str, object]:
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
            "competition": [{"report_month": "2026-03-01", "competitor_domain": "sexshop.bg", "impression_share": 0.21}],
            "status_cards": [{"title": "Budget", "tone": "positive", "detail": "No budget exhaustion"}],
        }

    def get_hub_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._overview_payload()["scope"],
            "summary": self._overview_payload()["summary"],
            "previous_summary": self._overview_payload()["previous_summary"],
            "management_conclusions": [{"title": "Efficiency trend", "detail": "ROAS is stable."}],
            "status_cards": [{"title": "Competition", "tone": "warning", "detail": "sexshop.bg is rising."}],
            "report_cards": [{"report_name": "overview", "title": "High-level overview", "description": "KPI trend", "meta": "10 campaigns"}],
            "trend": [{"report_date": "2026-03-22", "cost_eur": 100.0, "conversion_value_eur": 200.0}],
            "top_alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
        }

    def get_overview_data(self, **_: object) -> dict[str, object]:
        return self._overview_payload()

    def get_keywords_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._overview_payload()["scope"],
            "summary": self._overview_payload()["summary"],
            "previous_summary": self._overview_payload()["previous_summary"],
            "keywords": [{"keyword_text": "sexwell", "audit_reason": "ok", "cost_eur": 50.0}],
            "search_terms": [{"search_term": "sexwell", "cost_eur": 12.0, "conversions": 0.0}],
            "alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
        }

    def get_timing_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._overview_payload()["scope"],
            "summary": self._overview_payload()["summary"],
            "previous_summary": self._overview_payload()["previous_summary"],
            "hour_of_day": [{"report_hour": 22, "conversion_value_eur": 300.0, "roas": 3.5}],
            "weekday_profile": [{"weekday_name": "Monday", "conversion_value_eur": 600.0, "roas": 2.8}],
            "daypart": [{"daypart": "night", "cost_eur": 100.0, "conversions": 5.0}],
            "daypart_ad_groups": [{"ad_group_name": "Brand Core", "daypart": "day", "cost_eur": 150.0, "roas": 4.1}],
            "budget_flags": [{"campaign_name": "Brand", "budget_exhausted_flag": False, "report_date": "2026-03-22"}],
            "timing_highlights": [{"title": "Best hour", "detail": "22:00 performs best."}],
        }

    def get_alerts_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._overview_payload()["scope"],
            "summary": self._overview_payload()["summary"],
            "previous_summary": self._overview_payload()["previous_summary"],
            "alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
            "budget_flags": [{"campaign_name": "Brand", "budget_exhausted_flag": False, "report_date": "2026-03-22"}],
        }

    def get_report_data(self, report_name: str, **_: object) -> dict[str, object]:
        if report_name == "overview":
            return self.get_overview_data()
        if report_name == "keywords":
            return self.get_keywords_data()
        if report_name == "timing":
            return self.get_timing_data()
        if report_name == "alerts":
            return self.get_alerts_data()
        raise ValueError("Unknown report")

    def get_dashboard_data(self, **_: object) -> dict[str, object]:
        return self.get_overview_data()


client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_reporting_service] = lambda: FakeReportingService()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_index_renders_hub_shell() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Google Ads Signal Board" in response.text
    assert "Detailed reports" in response.text


def test_timing_page_renders() -> None:
    response = client.get("/reports/timing")
    assert response.status_code == 200
    assert "Timing Analysis" in response.text
    assert "Day of week" in response.text
    assert "Ad group timing" in response.text


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


def test_hub_endpoint_works() -> None:
    response = client.get("/api/hub")
    assert response.status_code == 200
    payload = response.json()
    assert payload["report_cards"][0]["report_name"] == "overview"


def test_timing_endpoint_works() -> None:
    response = client.get("/api/reports/timing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hour_of_day"][0]["report_hour"] == 22
    assert payload["daypart_ad_groups"][0]["ad_group_name"] == "Brand Core"


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
