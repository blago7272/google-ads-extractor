from __future__ import annotations

from datetime import date

from google.api_core.exceptions import NotFound

from app.cache import TtlCache
from app.service import BigQueryReportingService, ScopeFilters
from app.settings import ReportingAppSettings


class FakeBigQueryClient:
    def __init__(self, *_: object, **__: object) -> None:
        pass


def test_ttl_cache_get_or_set_reuses_cached_value() -> None:
    cache = TtlCache(ttl_seconds=60, max_entries=2)
    calls = 0

    def loader() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": 1}

    first = cache.get_or_set("alpha", loader)
    second = cache.get_or_set("alpha", loader)

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls == 1


def test_reporting_service_caches_filter_options(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(ReportingAppSettings())
    calls = 0

    def fake_run_query(*_: object, **__: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return [
            {
                "client_id": "sexwell",
                "account_id": "1200697994",
                "account_name": "Sexwell.bg (EUR)",
                "timezone": "Europe/Sofia",
                "currency": "EUR",
                "min_report_date": "2025-09-02",
                "max_report_date": "2026-03-22",
            }
        ]

    monkeypatch.setattr(service, "_run_query", fake_run_query)

    first = service.get_filter_options()
    second = service.get_filter_options()

    assert first["defaults"]["account_id"] == "1200697994"
    assert second["defaults"]["account_id"] == "1200697994"
    assert calls == 1


def test_sexwell_business_source_status_uses_freshness_mart_and_cache(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(ReportingAppSettings())
    calls = 0

    def fake_run_query(sql: str, **__: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        assert "sexwell_reporting_mart.mart_data_freshness" in sql
        return [
            {
                "freshness_status": "error",
                "report_generation_allowed": True,
                "failure_note": "Reports use the last successful data.",
            }
        ]

    monkeypatch.setattr(service, "_run_query", fake_run_query)

    first = service.get_sexwell_business_source_status()
    second = service.get_sexwell_business_source_status()

    assert first["report_generation_allowed"] is True
    assert second["freshness_status"] == "error"
    assert calls == 1


def test_sexwell_business_source_status_handles_unprovisioned_mart(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(ReportingAppSettings())

    def missing_mart(*_: object, **__: object) -> list[dict[str, object]]:
        raise NotFound("mart_data_freshness is not provisioned")

    monkeypatch.setattr(service, "_run_query", missing_mart)

    status = service.get_sexwell_business_source_status()

    assert status["freshness_status"] == "backfilling"
    assert status["report_generation_allowed"] is False
    assert "first approved load" in status["failure_note"]


def test_sexwell_business_results_reads_validated_marts_and_caches(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(ReportingAppSettings())
    calls = 0

    def fake_run_query(sql: str, **__: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        if "group by report_month" in sql:
            return [{"report_month": "2026-09-01", "completed_orders": 493}]
        if "mart_order_lines_daily" in sql:
            if "group by category_path" in sql:
                return [{"category_path": "Example category", "product_sales_eur": 25200.0}]
            return [{"product_name": "Example product", "product_sales_eur": 2520.0}]
        if "group by status, status_name" in sql:
            return [{"status": "C", "status_name": "Завършена", "orders": 4913}]
        assert "mart_orders_daily" in sql
        return [{"coverage_start": "2026-04-01", "coverage_end": "2026-09-20"}]

    monkeypatch.setattr(service, "_run_query", fake_run_query)

    first = service.get_sexwell_business_results()
    second = service.get_sexwell_business_results()

    assert first["available"] is True
    assert first["monthly"][0]["completed_orders"] == 493
    assert first["top_products"][0]["product_name"] == "Example product"
    assert first["statuses"][0]["status"] == "C"
    assert first["top_categories"][0]["category_path"] == "Example category"
    assert second == first
    assert calls == 5


def test_sexwell_business_results_handles_missing_marts(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(ReportingAppSettings())

    def missing_mart(*_: object, **__: object) -> list[dict[str, object]]:
        raise NotFound("SexWell business mart is not provisioned")

    monkeypatch.setattr(service, "_run_query", missing_mart)

    result = service.get_sexwell_business_results()

    assert result["available"] is False
    assert result["monthly"] == []
    assert result["statuses"] == []


def test_reporting_service_caches_scope_queries(monkeypatch) -> None:
    monkeypatch.setattr("app.service.bigquery.Client", FakeBigQueryClient)
    service = BigQueryReportingService(
        ReportingAppSettings(
            query_cache_ttl_seconds=900,
            query_cache_max_entries=16,
        )
    )
    calls = 0

    def fake_run_query(*_: object, **__: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return [
            {
                "report_date_start": "2026-02-21",
                "report_date_end": "2026-03-22",
                "active_days": 30,
                "account_count": 1,
                "currency": "EUR",
                "cost_original": 100.0,
                "cost_eur": 100.0,
                "clicks": 200,
                "impressions": 1000,
                "conversions": 10.0,
                "conversion_value_original": 300.0,
                "conversion_value_eur": 300.0,
                "ctr": 0.2,
                "cpc_original": 0.5,
                "cpc_eur": 0.5,
                "cpa_original": 10.0,
                "cpa_eur": 10.0,
                "roas": 3.0,
            }
        ]

    monkeypatch.setattr(service, "_run_query", fake_run_query)

    scope = ScopeFilters(
        client_id="sexwell",
        account_id="1200697994",
        date_from=date(2026, 2, 21),
        date_to=date(2026, 3, 22),
    )

    first = service._summary_query(scope)
    second = service._summary_query(scope)

    assert first[0]["roas"] == 3.0
    assert second[0]["roas"] == 3.0
    assert calls == 1
