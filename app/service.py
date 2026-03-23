from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from google.cloud import bigquery

from app.settings import ReportingAppSettings, get_settings


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_rows(rows: list[bigquery.table.Row]) -> list[dict[str, Any]]:
    return [{key: _serialize_value(value) for key, value in dict(row).items()} for row in rows]


def resolve_date_window(
    min_date: date,
    max_date: date,
    requested_from: date | None,
    requested_to: date | None,
    default_window_days: int,
) -> tuple[date, date]:
    if requested_to is None:
        requested_to = max_date

    if requested_from is None:
        requested_from = max(min_date, requested_to - timedelta(days=max(default_window_days - 1, 0)))

    if requested_from > requested_to:
        raise ValueError("date_from must be on or before date_to")

    if requested_to < min_date or requested_from > max_date:
        raise ValueError("requested range falls outside the available reporting window")

    return max(requested_from, min_date), min(requested_to, max_date)


@dataclass(frozen=True)
class ScopeFilters:
    client_id: str | None
    account_id: str | None
    date_from: date
    date_to: date

    @property
    def date_span_days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    @property
    def previous_date_from(self) -> date:
        return self.date_from - timedelta(days=self.date_span_days)

    @property
    def previous_date_to(self) -> date:
        return self.date_from - timedelta(days=1)


class BigQueryReportingService:
    def __init__(self, settings: ReportingAppSettings):
        self.settings = settings
        self.client = bigquery.Client(project=settings.project_id)

    def mart_table(self, table_name: str) -> str:
        return f"`{self.settings.project_id}.{self.settings.mart_dataset}.{table_name}`"

    def cfg_table(self, table_name: str) -> str:
        return f"`{self.settings.project_id}.{self.settings.cfg_dataset}.{table_name}`"

    def _run_query(
        self,
        sql: str,
        *,
        parameters: list[bigquery.ScalarQueryParameter] | None = None,
    ) -> list[dict[str, Any]]:
        job_config = bigquery.QueryJobConfig(query_parameters=parameters or [])
        rows = list(self.client.query(sql, job_config=job_config).result())
        return _serialize_rows(rows)

    def get_filter_options(self) -> dict[str, Any]:
        sql = f"""
with active_accounts as (
  select
    client_id,
    cast(account_id as string) as account_id,
    account_name,
    timezone,
    currency
  from {self.cfg_table('cfg_accounts')}
  where is_active = true
),
account_windows as (
  select
    account_id,
    min(report_date) as min_report_date,
    max(report_date) as max_report_date
  from {self.mart_table('mart_ads_overview_daily')}
  group by 1
)
select
  a.client_id,
  a.account_id,
  a.account_name,
  a.timezone,
  a.currency,
  w.min_report_date,
  w.max_report_date
from active_accounts a
left join account_windows w using (account_id)
order by a.client_id, a.account_name
"""
        accounts = self._run_query(sql)
        if not accounts:
            raise ValueError("No active accounts are configured for the reporting app")

        valid_accounts = [row for row in accounts if row["min_report_date"] and row["max_report_date"]]
        if not valid_accounts:
            raise ValueError("Configured accounts do not have reporting data in mart_ads_overview_daily")

        min_date = min(date.fromisoformat(row["min_report_date"]) for row in valid_accounts)
        max_date = max(date.fromisoformat(row["max_report_date"]) for row in valid_accounts)
        default_client_id = valid_accounts[0]["client_id"]
        default_account_id = valid_accounts[0]["account_id"]
        default_from, default_to = resolve_date_window(
            min_date=min_date,
            max_date=max_date,
            requested_from=None,
            requested_to=None,
            default_window_days=self.settings.default_window_days,
        )

        clients = []
        seen_clients: set[str] = set()
        for row in valid_accounts:
            if row["client_id"] in seen_clients:
                continue
            seen_clients.add(row["client_id"])
            clients.append({"client_id": row["client_id"]})

        return {
            "clients": clients,
            "accounts": valid_accounts,
            "date_bounds": {
                "min_report_date": min_date.isoformat(),
                "max_report_date": max_date.isoformat(),
            },
            "defaults": {
                "client_id": default_client_id,
                "account_id": default_account_id,
                "date_from": default_from.isoformat(),
                "date_to": default_to.isoformat(),
            },
        }

    def resolve_scope(
        self,
        *,
        client_id: str | None,
        account_id: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> ScopeFilters:
        options = self.get_filter_options()
        bounds = options["date_bounds"]
        resolved_from, resolved_to = resolve_date_window(
            min_date=date.fromisoformat(bounds["min_report_date"]),
            max_date=date.fromisoformat(bounds["max_report_date"]),
            requested_from=date_from,
            requested_to=date_to,
            default_window_days=self.settings.default_window_days,
        )
        return ScopeFilters(
            client_id=client_id or None,
            account_id=account_id or None,
            date_from=resolved_from,
            date_to=resolved_to,
        )

    def _scope_parameters(self, scope: ScopeFilters) -> list[bigquery.ScalarQueryParameter]:
        return [
            bigquery.ScalarQueryParameter("client_id", "STRING", scope.client_id),
            bigquery.ScalarQueryParameter("account_id", "STRING", scope.account_id),
            bigquery.ScalarQueryParameter("date_from", "DATE", scope.date_from),
            bigquery.ScalarQueryParameter("date_to", "DATE", scope.date_to),
        ]

    def _summary_query(self, scope: ScopeFilters, *, previous: bool = False) -> tuple[str, list[bigquery.ScalarQueryParameter]]:
        date_from = scope.previous_date_from if previous else scope.date_from
        date_to = scope.previous_date_to if previous else scope.date_to
        parameters = [
            bigquery.ScalarQueryParameter("client_id", "STRING", scope.client_id),
            bigquery.ScalarQueryParameter("account_id", "STRING", scope.account_id),
            bigquery.ScalarQueryParameter("date_from", "DATE", date_from),
            bigquery.ScalarQueryParameter("date_to", "DATE", date_to),
        ]
        sql = f"""
select
  min(report_date) as report_date_start,
  max(report_date) as report_date_end,
  count(distinct report_date) as active_days,
  count(distinct account_id) as account_count,
  any_value(currency) as currency,
  sum(cost_original) as cost_original,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_original) as conversion_value_original,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
  safe_divide(sum(cost_original), sum(clicks)) as cpc_original,
  safe_divide(sum(cost_eur), sum(clicks)) as cpc_eur,
  safe_divide(sum(cost_original), sum(conversions)) as cpa_original,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_overview_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
"""
        return sql, parameters

    def _trend_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  report_date,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_overview_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by report_date
order by report_date
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _campaigns_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  client_id,
  account_id,
  account_name,
  currency,
  campaign_id,
  campaign_name,
  any_value(campaign_status) as campaign_status,
  any_value(campaign_serving_status) as campaign_serving_status,
  any_value(campaign_channel_type) as campaign_channel_type,
  any_value(campaign_channel_sub_type) as campaign_channel_sub_type,
  any_value(bidding_strategy_type) as bidding_strategy_type,
  any_value(campaign_budget_original) as campaign_budget_original,
  any_value(campaign_budget_eur) as campaign_budget_eur,
  sum(cost_original) as cost_original,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_original) as conversion_value_original,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
  safe_divide(sum(cost_original), sum(clicks)) as cpc_original,
  safe_divide(sum(cost_eur), sum(clicks)) as cpc_eur,
  safe_divide(sum(cost_original), sum(conversions)) as cpa_original,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_campaign_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by client_id, account_id, account_name, currency, campaign_id, campaign_name
order by cost_eur desc, conversions desc
limit 250
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _keywords_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  client_id,
  account_id,
  account_name,
  currency,
  campaign_name,
  ad_group_name,
  keyword_text,
  match_type,
  keyword_status,
  quality_score,
  report_date_start,
  report_date_end,
  cost_eur,
  clicks,
  impressions,
  conversions,
  conversion_value_eur,
  cpa_eur,
  audit_reason
from {self.mart_table('mart_ads_keyword_audit_detail')}
where report_date_end >= @date_from
  and report_date_start <= @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
order by
  case audit_reason
    when 'low_qs' then 1
    when 'intent_or_offer' then 2
    when 'scale_but_fix_qs' then 3
    when 'low_volume' then 4
    else 5
  end,
  cost_eur desc
limit 250
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _search_terms_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  client_id,
  account_id,
  account_name,
  currency,
  campaign_name,
  ad_group_name,
  search_term,
  search_term_status,
  search_term_match_type,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_search_terms')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by client_id, account_id, account_name, currency, campaign_name, ad_group_name, search_term, search_term_status, search_term_match_type
order by cost_eur desc, conversions asc
limit 250
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _alerts_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  client_id,
  account_id,
  account_name,
  report_date,
  alert_type,
  severity,
  alert_message
from {self.mart_table('mart_ads_alerts')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
order by report_date desc, severity
limit 250
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def get_dashboard_data(
        self,
        *,
        client_id: str | None,
        account_id: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        scope = self.resolve_scope(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )

        current_summary_query, current_summary_params = self._summary_query(scope, previous=False)
        previous_summary_query, previous_summary_params = self._summary_query(scope, previous=True)
        current_summary = self._run_query(current_summary_query, parameters=current_summary_params)[0]
        previous_summary = self._run_query(previous_summary_query, parameters=previous_summary_params)[0]

        return {
            "scope": {
                "client_id": scope.client_id,
                "account_id": scope.account_id,
                "date_from": scope.date_from.isoformat(),
                "date_to": scope.date_to.isoformat(),
                "previous_date_from": scope.previous_date_from.isoformat(),
                "previous_date_to": scope.previous_date_to.isoformat(),
            },
            "summary": current_summary,
            "previous_summary": previous_summary,
            "trend": self._trend_query(scope),
            "campaigns": self._campaigns_query(scope),
            "keywords": self._keywords_query(scope),
            "search_terms": self._search_terms_query(scope),
            "alerts": self._alerts_query(scope),
        }


@lru_cache(maxsize=1)
def get_reporting_service() -> BigQueryReportingService:
    return BigQueryReportingService(get_settings())
