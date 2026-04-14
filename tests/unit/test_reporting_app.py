from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import app.main as main_module
from app.auth import UserSession
from app.main import app
from app.service import get_reporting_service, resolve_date_window
from app.settings import ReportingAppSettings, get_settings


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

    def get_freshness_data(self, *, client_id: str | None, account_id: str | None) -> dict[str, object]:
        if not account_id:
            return {
                "scope_type": "unscoped",
                "client_id": client_id,
                "account_id": None,
                "account_name": None,
                "freshness_status": None,
                "last_data_date": None,
                "hours_since_last_data": None,
                "checked_at": None,
                "message": "Select an account to see reporting freshness.",
            }
        return {
            "scope_type": "account",
            "client_id": "sexwell",
            "account_id": account_id,
            "account_name": "Sexwell.bg (EUR)",
            "freshness_status": "stale",
            "last_data_date": "2026-03-22",
            "hours_since_last_data": 44,
            "checked_at": "2026-03-23T08:15:00+00:00",
            "message": None,
        }

    def _scope(self) -> dict[str, str]:
        return {
            "client_id": "sexwell",
            "account_id": "1200697994",
            "date_from": "2026-02-22",
            "date_to": "2026-03-22",
            "previous_date_from": "2026-01-24",
            "previous_date_to": "2026-02-21",
        }

    def _summary(self) -> dict[str, float | str]:
        return {
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
        }

    def _previous_summary(self) -> dict[str, float]:
        return {
            "cost_eur": 900.0,
            "conversion_value_eur": 2000.0,
            "conversions": 40.0,
            "roas": 2.2,
            "clicks": 3500,
            "impressions": 39000,
            "ctr": 0.0897,
            "cpa_eur": 22.5,
        }

    def _auction_scope(self) -> dict[str, str | None]:
        return {
            "client_id": None,
            "account_id": None,
            "date_from": "2025-01-01",
            "date_to": "2025-03-23",
            "previous_date_from": "2024-10-09",
            "previous_date_to": "2024-12-31",
            "scope_label": "Sexwell.bg (BGN)",
        }

    def _overview_payload(self) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "trend": [
                {"report_date": "2026-03-21", "cost_eur": 90.0, "conversion_value_eur": 180.0, "conversion_rate": 0.11, "conversions": 8.0, "cpc_eur": 0.85, "clicks": 106, "impressions": 1250},
                {"report_date": "2026-03-22", "cost_eur": 100.0, "conversion_value_eur": 200.0, "conversion_rate": 0.12, "conversions": 9.0, "cpc_eur": 0.91, "clicks": 110, "impressions": 1310},
            ],
            "previous_trend": [
                {"report_date": "2026-03-19", "cost_eur": 82.0, "conversion_value_eur": 170.0, "conversion_rate": 0.1, "conversions": 7.0, "cpc_eur": 0.79, "clicks": 104, "impressions": 1210},
                {"report_date": "2026-03-20", "cost_eur": 95.0, "conversion_value_eur": 190.0, "conversion_rate": 0.11, "conversions": 8.0, "cpc_eur": 0.84, "clicks": 108, "impressions": 1260},
            ],
            "campaigns": [
                {
                    "campaign_name": "Brand",
                    "campaign_channel_type": "SEARCH",
                    "bidding_strategy_type": "MAXIMIZE_CONVERSIONS",
                    "cost_eur": 200.0,
                    "conversions": 10.0,
                    "conversion_rate": 0.15,
                    "conversion_value_eur": 800.0,
                    "cpa_eur": 20.0,
                    "roas": 4.0,
                }
            ],
            "competition": [
                {
                    "report_month": "2026-03-01",
                    "competitor_domain": "sexshop.bg",
                    "impression_share": 0.21,
                    "overlap_rate": 0.18,
                    "position_above_rate": 0.12,
                    "outranking_share": 0.04,
                }
            ],
            "campaign_filter_options": ["Brand", "Generic", "PMax"],
            "competition_note": "Monthly auction insights rows are shown only when competitor-domain data exists for the selected period.",
            "status_cards": [{"title": "Budget", "tone": "positive", "detail": "No budget exhaustion"}],
            "campaign_regex": "brand",
        }

    def get_hub_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "management_conclusions": [{"title": "Efficiency trend", "detail": "ROAS is stable."}],
            "status_cards": [{"title": "Competition", "tone": "warning", "detail": "sexshop.bg is rising."}],
            "report_cards": [{"report_name": "overview", "title": "High-level overview", "description": "KPI trend", "meta": "10 campaigns"}],
            "trend": [{"report_date": "2026-03-22", "cost_eur": 100.0, "conversion_value_eur": 200.0, "conversion_rate": 0.12, "conversions": 9.0, "cpc_eur": 0.91, "clicks": 110, "impressions": 1310}],
            "previous_trend": [{"report_date": "2026-02-21", "cost_eur": 85.0, "conversion_value_eur": 170.0, "conversion_rate": 0.1, "conversions": 7.0, "cpc_eur": 0.82, "clicks": 104, "impressions": 1280}],
            "top_alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
        }

    def get_overview_data(self, **_: object) -> dict[str, object]:
        return self._overview_payload()

    def get_keywords_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "keywords": [
                {
                    "keyword_text": "sexwell",
                    "campaign_name": "Brand",
                    "ad_group_name": "Brand Core",
                    "audit_reason": "low_qs",
                    "quality_score": 4,
                    "cost_eur": 50.0,
                    "conversions": 1.0,
                    "cpa_eur": 50.0,
                    "report_date_end": "2026-03-22",
                }
            ],
            "search_terms": [{"search_term": "sexwell", "campaign_name": "Brand", "cost_eur": 12.0, "conversions": 0.0, "roas": 0.0}],
            "alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_message": "Check budget"}],
            "alerts_definition": "Only keyword alerts are shown.",
        }

    def get_timing_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "hour_of_day": [{"report_hour": 22, "conversion_value_eur": 300.0, "roas": 3.5, "conversions": 4.0, "conversion_rate": 0.17, "cost_eur": 85.0}],
            "weekday_profile": [{"weekday_name": "Monday", "conversion_value_eur": 600.0, "roas": 2.8, "conversions": 10.0, "conversion_rate": 0.12, "cost_eur": 215.0}],
            "weekpart_comparison": [{"period_group": "Weekday", "cost_eur": 600.0, "clicks": 2200, "impressions": 21000, "conversions": 30.0, "conversion_rate": 0.14, "conversion_value_eur": 1600.0, "roas": 2.67}],
            "day_window_comparison": [{"period_group": "Business hours", "cost_eur": 520.0, "clicks": 1800, "impressions": 16000, "conversions": 25.0, "conversion_rate": 0.14, "conversion_value_eur": 1400.0, "roas": 2.69}],
            "daypart": [{"daypart": "night", "cost_eur": 100.0, "conversions": 5.0, "conversion_value_eur": 330.0, "cpa_eur": 20.0, "roas": 3.3}],
            "daypart_ad_groups": [{"ad_group_name": "Brand Core", "daypart": "day", "cost_eur": 150.0, "conversions": 6.0, "conversion_value_eur": 615.0, "cpa_eur": 25.0, "roas": 4.1}],
            "budget_flags": [{"campaign_name": "Brand", "budget_exhausted_flag": False, "report_date": "2026-03-22", "last_active_hour": 22, "total_cost_eur": 140.0}],
            "budget_flags_definition": "This is only a pacing heuristic.",
            "timing_highlights": [{"title": "Best hour", "detail": "22:00 performs best."}],
        }

    def get_efficiency_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "zero_conv_campaigns": [{"campaign_name": "Generic", "cost_eur": 80.0, "clicks": 40, "impressions": 1000, "ctr": 0.04, "conversions": 0.0}],
            "zero_conv_ad_groups": [{"campaign_name": "Generic", "ad_group_name": "Generic Core", "cost_eur": 50.0, "clicks": 20, "impressions": 600, "ctr": 0.033, "conversions": 0.0}],
            "zero_conv_keywords": [{"campaign_name": "Generic", "ad_group_name": "Generic Core", "keyword_text": "buy toy", "match_type": "PHRASE", "cost_eur": 20.0, "clicks": 10, "impressions": 200, "ctr": 0.05, "conversions": 0.0}],
            "zero_conv_search_terms": [{"search_term": "buy toy", "campaign_name": "Generic", "ad_group_name": "Generic Core", "search_term_status": "NONE", "cost_eur": 15.0, "clicks": 8, "impressions": 150, "ctr": 0.053, "conversions": 0.0}],
            "campaign_winners": [{"campaign_name": "Brand", "current_cost_eur": 200.0, "previous_cost_eur": 180.0, "current_conversions": 10.0, "previous_conversions": 7.0, "current_conversion_value_eur": 800.0, "previous_conversion_value_eur": 550.0, "current_roas": 4.0, "previous_roas": 3.06, "value_delta_eur": 250.0, "roas_delta": 0.94}],
            "campaign_losers": [{"campaign_name": "Generic", "current_cost_eur": 150.0, "previous_cost_eur": 120.0, "current_conversions": 2.0, "previous_conversions": 4.0, "current_conversion_value_eur": 180.0, "previous_conversion_value_eur": 420.0, "current_roas": 1.2, "previous_roas": 3.5, "value_delta_eur": -240.0, "roas_delta": -2.3}],
            "campaign_concentration": [{"campaign_name": "Brand", "cost_eur": 450.0, "conversion_value_eur": 1300.0, "conversions": 18.0, "spend_share": 0.45, "value_share": 0.52}],
        }

    def get_coverage_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "coverage_opportunities": [{"search_term": "sexwell promo", "campaign_name": "Brand", "ad_group_name": "Brand Core", "search_term_status": "NONE", "cost_eur": 22.0, "clicks": 15, "conversions": 2.0, "conversion_rate": 0.133, "conversion_value_eur": 170.0, "roas": 7.73}],
            "negative_candidates": [{"search_term": "free toy", "campaign_name": "Generic", "ad_group_name": "Generic Core", "search_term_status": "NONE", "cost_eur": 18.0, "clicks": 12, "impressions": 200, "ctr": 0.06, "conversions": 0.0}],
        }

    def get_auction_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._auction_scope(),
            "summary": {
                "report_date_start": "2025-01-01",
                "report_date_end": "2025-03-23",
            },
            "previous_summary": {},
            "source_cards": [
                {"title": "Accounts", "value": "1", "helper": "Distinct account_name values in scope"},
                {"title": "Campaigns", "value": "7", "helper": "Distinct campaigns in the selected window"},
            ],
            "source_note": "This report is siloed to the Auction Insights source tables.",
            "auction_daily": [
                {
                    "bucket_date": "2025-03-23",
                    "account_name": "Sexwell.bg (BGN)",
                    "campaign_name": "ROI - Search - Categories",
                    "display_url_domain": "You",
                    "search_impr_share": 35.22,
                    "search_overlap_rate": None,
                    "search_outranking_share": None,
                }
            ],
            "auction_weekly": [
                {
                    "bucket_date": "2025-03-17",
                    "account_name": "Sexwell.bg (BGN)",
                    "campaign_name": "ROI - Search - Categories",
                    "display_url_domain": "competitor.bg",
                    "search_impr_share": 40.11,
                    "search_overlap_rate": 28.42,
                    "search_outranking_share": 11.05,
                }
            ],
            "auction_monthly": [
                {
                    "bucket_date": "2025-03-01",
                    "account_name": "Sexwell.bg (BGN)",
                    "campaign_name": "ROI - Search - Categories",
                    "display_url_domain": "competitor.bg",
                    "search_impr_share": 44.98,
                    "search_overlap_rate": 31.12,
                    "search_outranking_share": 12.77,
                }
            ],
        }

    def _ga4_scope(self) -> dict[str, str | None]:
        return {
            "client_id": None,
            "account_id": None,
            "date_from": "2026-02-24",
            "date_to": "2026-03-23",
            "previous_date_from": "2026-01-27",
            "previous_date_to": "2026-02-23",
            "scope_label": "GA4 ecommerce export",
        }

    def _ga4_summary(self) -> dict[str, float | str]:
        return {
            "report_date_start": "2026-02-24",
            "report_date_end": "2026-03-23",
            "revenue": 12500.0,
            "orders": 180,
            "items_purchased": 245,
            "items_added_to_cart": 390,
            "items_viewed": 5400,
            "aov": 69.44,
            "view_to_order_rate": 0.0333,
            "atc_to_order_rate": 0.4615,
        }

    def _ga4_previous_summary(self) -> dict[str, float]:
        return {
            "revenue": 11300.0,
            "orders": 160,
            "items_purchased": 220,
            "items_added_to_cart": 360,
            "items_viewed": 5200,
            "aov": 70.63,
            "view_to_order_rate": 0.0308,
            "atc_to_order_rate": 0.4444,
        }

    def get_ga4_overview_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._ga4_scope(),
            "summary": self._ga4_summary(),
            "previous_summary": self._ga4_previous_summary(),
            "trend": [
                {"report_date": "2026-03-22", "revenue": 420.0, "orders": 8, "items_purchased": 11, "items_added_to_cart": 17, "items_viewed": 210, "aov": 52.5},
                {"report_date": "2026-03-23", "revenue": 560.0, "orders": 10, "items_purchased": 13, "items_added_to_cart": 21, "items_viewed": 240, "aov": 56.0},
            ],
            "previous_trend": [
                {"report_date": "2026-02-22", "revenue": 390.0, "orders": 7, "items_purchased": 9, "items_added_to_cart": 15, "items_viewed": 205, "aov": 55.71},
                {"report_date": "2026-02-23", "revenue": 500.0, "orders": 9, "items_purchased": 12, "items_added_to_cart": 18, "items_viewed": 232, "aov": 55.56},
            ],
            "source_summary": [{"channel_group": "Google Ads", "sessionSourceMedium": "google / cpc", "revenue": 4200.0, "orders": 60, "items_purchased": 84, "items_added_to_cart": 120, "items_viewed": 1600, "aov": 70.0}],
            "campaign_summary": [{"channel_group": "Google Ads", "sessionCampaignName": "ROI - Performance Max", "revenue": 2600.0, "orders": 34, "items_purchased": 49, "items_added_to_cart": 72, "items_viewed": 920, "aov": 76.47}],
            "top_products": [{"item_name": "Lube", "item_brand": "Sexwell", "item_category": "Lubricants & Intimate Care", "revenue": 780.0, "orders": 16, "items_purchased": 24, "aov": 48.75}],
            "channel_monthly": [{"report_month": "2026-03-01", "channel_group": "Google Ads", "revenue": 4200.0, "revenue_share": 0.336, "orders": 60, "order_share": 0.333}],
            "insights": [{"title": "Revenue trend", "detail": "Revenue is up."}],
            "source_note": "GA4 overview note",
        }

    def get_ga4_impact_data(self, **_: object) -> dict[str, object]:
        row = {"revenue": 900.0, "orders": 12, "items_purchased": 16, "items_added_to_cart": 25, "items_viewed": 180, "aov": 75.0}
        return {
            "scope": self._ga4_scope(),
            "summary": self._ga4_summary(),
            "previous_summary": self._ga4_previous_summary(),
            "source_item_impact": [{"source_medium": "google / cpc", "item_name": "Lube", **row}],
            "source_category_impact": [{"source_medium": "google / cpc", "item_category": "Lubricants & Intimate Care", **row}],
            "source_brand_impact": [{"source_medium": "google / cpc", "item_brand": "Sexwell", **row}],
            "campaign_item_impact": [{"campaign_name": "ROI - Performance Max", "item_name": "Lube", **row}],
            "campaign_category_impact": [{"campaign_name": "ROI - Performance Max", "item_category": "Lubricants & Intimate Care", **row}],
            "campaign_brand_impact": [{"campaign_name": "ROI - Performance Max", "item_brand": "Sexwell", **row}],
            "source_note": "GA4 impact note",
        }

    def get_ga4_funnel_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._ga4_scope(),
            "summary": self._ga4_summary(),
            "previous_summary": self._ga4_previous_summary(),
            "channel_funnel": [{"channel_group": "Google Ads", "revenue": 4200.0, "orders": 60, "items_viewed": 1600, "items_added_to_cart": 120, "items_purchased": 84, "view_to_atc_rate": 0.075, "view_to_order_rate": 0.0375, "atc_to_order_rate": 0.5}],
            "source_funnel": [{"channel_group": "Google Ads", "sessionSourceMedium": "google / cpc", "revenue": 4200.0, "orders": 60, "items_viewed": 1600, "items_added_to_cart": 120, "items_purchased": 84, "view_to_atc_rate": 0.075, "view_to_order_rate": 0.0375, "atc_to_order_rate": 0.5}],
            "funnel_note": "GA4 funnel note",
        }

    def get_ga4_timing_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._ga4_scope(),
            "summary": self._ga4_summary(),
            "previous_summary": self._ga4_previous_summary(),
            "hourly_summary": [{"report_hour": 22, "revenue": 620.0, "orders": 10, "items_added_to_cart": 18, "items_purchased": 14, "items_viewed": 220, "aov": 62.0}],
            "day_window_summary": [{"period_group": "Day 07-23h", "revenue": 11800.0, "orders": 170, "items_added_to_cart": 360, "items_purchased": 232, "items_viewed": 5000, "aov": 69.41}],
            "revenue_matrix": [{"report_date": "2026-03-23", "day_label": "2026-03-23 Mon", "h00": 0.0, "h22": 620.0}],
            "orders_matrix": [{"report_date": "2026-03-23", "day_label": "2026-03-23 Mon", "h00": 0, "h22": 10}],
            "timing_highlights": [{"title": "Best revenue hour", "detail": "22:00 leads."}],
            "timing_note": "GA4 timing note",
        }

    def get_creative_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "ad_winners": [{"campaign_name": "Brand", "ad_group_name": "Brand Core", "ad_label": "Promo RSA", "current_cost_eur": 120.0, "previous_cost_eur": 80.0, "current_conversions": 7.0, "previous_conversions": 4.0, "current_conversion_value_eur": 540.0, "previous_conversion_value_eur": 260.0, "current_roas": 4.5, "previous_roas": 3.25, "value_delta_eur": 280.0, "roas_delta": 1.25}],
            "ad_losers": [{"campaign_name": "Generic", "ad_group_name": "Generic Core", "ad_label": "Old RSA", "current_cost_eur": 90.0, "previous_cost_eur": 75.0, "current_conversions": 1.0, "previous_conversions": 3.0, "current_conversion_value_eur": 60.0, "previous_conversion_value_eur": 180.0, "current_roas": 0.67, "previous_roas": 2.4, "value_delta_eur": -120.0, "roas_delta": -1.73}],
        }

    def get_alerts_data(self, **_: object) -> dict[str, object]:
        return {
            "scope": self._scope(),
            "summary": self._summary(),
            "previous_summary": self._previous_summary(),
            "alerts": [{"report_date": "2026-03-22", "severity": "medium", "alert_type": "keyword_issue", "alert_message": "Check budget"}],
            "budget_flags": [{"campaign_name": "Brand", "budget_exhausted_flag": False, "report_date": "2026-03-22", "last_active_hour": 22, "total_cost_eur": 140.0}],
        }

    def get_report_data(self, report_name: str, **_: object) -> dict[str, object]:
        if report_name == "overview":
            return self.get_overview_data()
        if report_name == "ga4-overview":
            return self.get_ga4_overview_data()
        if report_name == "ga4-impact":
            return self.get_ga4_impact_data()
        if report_name == "ga4-funnel":
            return self.get_ga4_funnel_data()
        if report_name == "ga4-timing":
            return self.get_ga4_timing_data()
        if report_name == "keywords":
            return self.get_keywords_data()
        if report_name == "timing":
            return self.get_timing_data()
        if report_name == "alerts":
            return self.get_alerts_data()
        if report_name == "efficiency":
            return self.get_efficiency_data()
        if report_name == "coverage":
            return self.get_coverage_data()
        if report_name == "auction":
            return self.get_auction_data()
        if report_name == "creative":
            return self.get_creative_data()
        raise ValueError("Unknown report")

    def get_dashboard_data(self, **_: object) -> dict[str, object]:
        return self.get_overview_data()


client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_reporting_service] = lambda: FakeReportingService()


def teardown_function() -> None:
    app.dependency_overrides.clear()
    client.cookies.clear()


def _auth_test_settings() -> ReportingAppSettings:
    return ReportingAppSettings(
        oauth_client_id="test-client-id",
        oauth_client_secret="test-client-secret",
        oauth_redirect_uri="http://testserver/auth/callback",
        session_secret_key="test-session-secret",
    )


def test_index_renders_hub_shell() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Google Ads Signal Board" in response.text
    assert "Reporting Workspace" in response.text
    assert "/static/branding/idconsult-logo-horizontal.png" in response.text
    assert "Reporting freshness" in response.text
    assert "Date preset" in response.text
    assert "Last 7 days" in response.text
    assert "Last 14 days" in response.text
    assert "Last 30 days" in response.text
    assert "Current month" in response.text
    assert "Past month" in response.text
    assert "Year-to-date" in response.text
    assert 'placeholder="YYYY-MM-DD"' in response.text
    assert "Detailed reports" in response.text
    assert "Time grain" in response.text
    assert "Top primary" in response.text
    assert "Top compare" in response.text
    assert "Bottom secondary" in response.text
    assert "Bottom compare" in response.text
    assert ">ROAS<" in response.text


def test_overview_page_renders_campaign_regex_filter() -> None:
    response = client.get("/reports/overview")
    assert response.status_code == 200
    assert "Spend and conversion rhythm" in response.text
    assert "All top campaigns" in response.text
    assert "Top compare" in response.text
    assert "Bottom secondary" in response.text
    assert 'id="overview-trend-grain"' in response.text
    assert ">ROAS<" in response.text
    assert "Auction insights snapshot" in response.text


def test_timing_page_renders_added_sections() -> None:
    response = client.get("/reports/timing")
    assert response.status_code == 200
    assert "Timing Analysis" in response.text
    assert "Weekend versus weekday" in response.text
    assert "Conversion rate" in response.text
    assert "Potential budget exhaustion days" in response.text
    assert "All campaigns" in response.text
    assert "All ad groups" in response.text


def test_keywords_page_renders_advanced_filters() -> None:
    response = client.get("/reports/keywords")
    assert response.status_code == 200
    assert "Regex search keywords" in response.text
    assert "Google Ads Quality Score" in response.text
    assert "Keyword-related alerts" in response.text
    assert "Higher than or equal" in response.text


def test_new_report_pages_render() -> None:
    response = client.get("/reports/ga4-overview")
    assert response.status_code == 200
    assert "GA4 Overview" in response.text
    assert "Revenue impact by source" in response.text
    assert "Top items by revenue" in response.text
    assert 'id="ga4-top-products-brand-filter-toggle"' in response.text
    assert 'id="ga4-top-products-category-filter-toggle"' in response.text
    assert "Monthly channel share" in response.text

    response = client.get("/reports/ga4-impact")
    assert response.status_code == 200
    assert "Product impact by source" in response.text
    assert "Category impact by source" in response.text
    assert "Brand impact by source" in response.text

    response = client.get("/reports/ga4-funnel")
    assert response.status_code == 200
    assert "Funnel by channel" in response.text

    response = client.get("/reports/ga4-timing")
    assert response.status_code == 200
    assert "Revenue by date and hour" in response.text

    response = client.get("/reports/efficiency")
    assert response.status_code == 200
    assert "Zero-conversion campaigns" in response.text

    response = client.get("/reports/coverage")
    assert response.status_code == 200
    assert "Converting terms not yet covered" in response.text

    response = client.get("/reports/auction")
    assert response.status_code == 200
    assert "Monthly auction insights" in response.text
    assert "Daily auction insights" in response.text
    assert "Weekly auction insights" in response.text
    assert 'id="auction-monthly-account-filter-toggle"' in response.text
    assert 'id="auction-monthly-metric-select"' in response.text
    assert 'id="auction-daily-account-filter-toggle"' in response.text

    response = client.get("/reports/creative")
    assert response.status_code == 200
    assert "Winning ads" in response.text


def test_filter_options_endpoint_works() -> None:
    response = client.get("/api/options")
    assert response.status_code == 200
    payload = response.json()
    assert payload["defaults"]["account_id"] == "1200697994"


def test_freshness_endpoint_works() -> None:
    response = client.get("/api/freshness", params={"client_id": "sexwell", "account_id": "1200697994"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["freshness_status"] == "stale"
    assert payload["last_data_date"] == "2026-03-22"


def test_auth_login_sets_state_cookie() -> None:
    app.dependency_overrides[get_settings] = _auth_test_settings

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    state_cookie = response.cookies.get("oauth_state")
    assert state_cookie
    redirect_state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert redirect_state == state_cookie


def test_auth_callback_rejects_state_mismatch() -> None:
    app.dependency_overrides[get_settings] = _auth_test_settings
    client.cookies.set("oauth_state", "expected-state")

    response = client.get("/auth/callback?code=test-code&state=wrong-state", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/auth/login"


def test_auth_callback_sets_session_on_matching_state(monkeypatch) -> None:
    app.dependency_overrides[get_settings] = _auth_test_settings
    client.cookies.set("oauth_state", "expected-state")

    monkeypatch.setattr(
        main_module,
        "exchange_code_for_id_token",
        lambda code, settings: {"email": "viewer@example.com"},
    )
    monkeypatch.setattr(
        main_module,
        "lookup_user_grants",
        lambda email, settings: UserSession(
            email=email,
            role="viewer",
            allowed_clients=["sexwell"],
            allowed_accounts={"sexwell": ["__all__"]},
        ),
    )

    response = client.get("/auth/callback?code=test-code&state=expected-state", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert response.cookies.get("session")


def test_auth_login_marks_state_cookie_secure_for_forwarded_https() -> None:
    app.dependency_overrides[get_settings] = _auth_test_settings

    response = client.get("/auth/login", headers={"x-forwarded-proto": "https"}, follow_redirects=False)

    assert response.status_code == 307
    assert "Secure" in response.headers["set-cookie"]


def test_auth_callback_marks_session_cookie_secure_for_forwarded_https(monkeypatch) -> None:
    app.dependency_overrides[get_settings] = _auth_test_settings
    client.cookies.set("oauth_state", "expected-state")

    monkeypatch.setattr(
        main_module,
        "exchange_code_for_id_token",
        lambda code, settings: {"email": "viewer@example.com"},
    )
    monkeypatch.setattr(
        main_module,
        "lookup_user_grants",
        lambda email, settings: UserSession(
            email=email,
            role="viewer",
            allowed_clients=["sexwell"],
            allowed_accounts={"sexwell": ["__all__"]},
        ),
    )

    response = client.get(
        "/auth/callback?code=test-code&state=expected-state",
        headers={"x-forwarded-proto": "https"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "session=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]


def test_dashboard_endpoint_accepts_campaign_regex() -> None:
    response = client.get(
        "/api/dashboard",
        params={
            "client_id": "sexwell",
            "account_id": "1200697994",
            "date_from": "2026-02-22",
            "date_to": "2026-03-22",
            "campaign_regex": "brand",
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
    assert payload["previous_trend"][0]["cost_eur"] == 85.0


def test_timing_endpoint_works() -> None:
    response = client.get("/api/reports/timing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hour_of_day"][0]["report_hour"] == 22
    assert payload["weekpart_comparison"][0]["period_group"] == "Weekday"
    assert payload["budget_flags_definition"] == "This is only a pacing heuristic."


def test_new_report_endpoints_work() -> None:
    response = client.get("/api/reports/ga4-overview")
    assert response.status_code == 200
    assert response.json()["source_summary"][0]["sessionSourceMedium"] == "google / cpc"

    response = client.get("/api/reports/ga4-impact")
    assert response.status_code == 200
    assert response.json()["campaign_item_impact"][0]["item_name"] == "Lube"

    response = client.get("/api/reports/ga4-funnel")
    assert response.status_code == 200
    assert response.json()["channel_funnel"][0]["channel_group"] == "Google Ads"

    response = client.get("/api/reports/ga4-timing")
    assert response.status_code == 200
    assert response.json()["hourly_summary"][0]["report_hour"] == 22

    response = client.get("/api/reports/efficiency")
    assert response.status_code == 200
    assert response.json()["campaign_winners"][0]["campaign_name"] == "Brand"

    response = client.get("/api/reports/coverage")
    assert response.status_code == 200
    assert response.json()["coverage_opportunities"][0]["search_term"] == "sexwell promo"

    response = client.get("/api/reports/auction")
    assert response.status_code == 200
    assert response.json()["auction_weekly"][0]["display_url_domain"] == "competitor.bg"

    response = client.get("/api/reports/creative")
    assert response.status_code == 200
    assert response.json()["ad_winners"][0]["ad_label"] == "Promo RSA"


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
