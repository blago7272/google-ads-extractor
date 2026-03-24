from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from google.cloud import bigquery

from app.cache import TtlCache
from app.settings import ReportingAppSettings, get_settings


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_rows(rows: list[bigquery.table.Row]) -> list[dict[str, Any]]:
    return [{key: _serialize_value(value) for key, value in dict(row).items()} for row in rows]


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _delta_pct(current: Any, previous: Any) -> float | None:
    current_value = _as_float(current)
    previous_value = _as_float(previous)
    if previous_value == 0:
        return None
    return (current_value - previous_value) / previous_value


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "no baseline"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.0f}%"


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
        self.options_cache = TtlCache(
            ttl_seconds=settings.options_cache_ttl_seconds,
            max_entries=4,
        )
        self.query_cache = TtlCache(
            ttl_seconds=settings.query_cache_ttl_seconds,
            max_entries=settings.query_cache_max_entries,
        )

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

    def _scope_cache_key(self, scope: ScopeFilters) -> tuple[str | None, str | None, str, str]:
        return (
            scope.client_id,
            scope.account_id,
            scope.date_from.isoformat(),
            scope.date_to.isoformat(),
        )

    def _cached_query_result(
        self,
        cache_name: str,
        key_parts: tuple[Any, ...],
        loader: callable,
    ) -> list[dict[str, Any]]:
        return self.query_cache.get_or_set((cache_name, *key_parts), loader)

    def get_filter_options(self) -> dict[str, Any]:
        def load_options() -> dict[str, Any]:
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

            clients: list[dict[str, str]] = []
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

        return self.options_cache.get_or_set(("filter_options",), load_options)

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

    def _scope_parameters(
        self,
        scope: ScopeFilters,
        *,
        previous: bool = False,
    ) -> list[bigquery.ScalarQueryParameter]:
        date_from = scope.previous_date_from if previous else scope.date_from
        date_to = scope.previous_date_to if previous else scope.date_to
        return [
            bigquery.ScalarQueryParameter("client_id", "STRING", scope.client_id),
            bigquery.ScalarQueryParameter("account_id", "STRING", scope.account_id),
            bigquery.ScalarQueryParameter("date_from", "DATE", date_from),
            bigquery.ScalarQueryParameter("date_to", "DATE", date_to),
        ]

    def _scope_parameters_with_campaign_regex(
        self,
        scope: ScopeFilters,
        *,
        campaign_regex: str | None,
        previous: bool = False,
    ) -> list[bigquery.ScalarQueryParameter]:
        return [
            *self._scope_parameters(scope, previous=previous),
            bigquery.ScalarQueryParameter("campaign_regex", "STRING", campaign_regex),
        ]

    def _summary_query(self, scope: ScopeFilters, *, previous: bool = False) -> list[dict[str, Any]]:
        def load_summary() -> list[dict[str, Any]]:
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
            return self._run_query(sql, parameters=self._scope_parameters(scope, previous=previous))

        return self._cached_query_result("summary", (*self._scope_cache_key(scope), previous), load_summary)

    def _trend_query(
        self,
        scope: ScopeFilters,
        *,
        campaign_regex: str | None = None,
        previous: bool = False,
    ) -> list[dict[str, Any]]:
        def load_trend() -> list[dict[str, Any]]:
            sql = f"""
select
  report_date,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(cost_eur), sum(clicks)) as cpc_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate
from {self.mart_table('mart_ads_campaign_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
  and (@campaign_regex is null or regexp_contains(campaign_name, @campaign_regex))
group by report_date
order by report_date
"""
            return self._run_query(
                sql,
                parameters=self._scope_parameters_with_campaign_regex(scope, campaign_regex=campaign_regex, previous=previous),
            )

        return self._cached_query_result("trend", (*self._scope_cache_key(scope), campaign_regex, previous), load_trend)

    def _campaigns_query(self, scope: ScopeFilters, *, campaign_regex: str | None = None) -> list[dict[str, Any]]:
        def load_campaigns() -> list[dict[str, Any]]:
            sql = f"""
select
  client_id,
  account_id,
  account_name,
  currency,
  campaign_id,
  campaign_name,
  array_agg(ifnull(campaign_status, 'Unknown') order by report_date desc limit 1)[safe_offset(0)] as campaign_status,
  array_agg(ifnull(campaign_serving_status, 'Unknown') order by report_date desc limit 1)[safe_offset(0)] as campaign_serving_status,
  array_agg(ifnull(campaign_channel_type, 'Unknown') order by report_date desc limit 1)[safe_offset(0)] as campaign_channel_type,
  array_agg(ifnull(campaign_channel_sub_type, 'Unknown') order by report_date desc limit 1)[safe_offset(0)] as campaign_channel_sub_type,
  case
    when count(distinct ifnull(bidding_strategy_type, 'Unknown')) > 1
      then concat(
        'Mixed (latest: ',
        array_agg(ifnull(bidding_strategy_type, 'Unknown') order by report_date desc limit 1)[safe_offset(0)],
        ')'
      )
    else array_agg(ifnull(bidding_strategy_type, 'Unknown') order by report_date desc limit 1)[safe_offset(0)]
  end as bidding_strategy_type,
  array_agg(campaign_budget_original order by report_date desc limit 1)[safe_offset(0)] as campaign_budget_original,
  array_agg(campaign_budget_eur order by report_date desc limit 1)[safe_offset(0)] as campaign_budget_eur,
  sum(cost_original) as cost_original,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_original) as conversion_value_original,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(cost_original), sum(clicks)) as cpc_original,
  safe_divide(sum(cost_eur), sum(clicks)) as cpc_eur,
  safe_divide(sum(cost_original), sum(conversions)) as cpa_original,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_campaign_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
  and (@campaign_regex is null or regexp_contains(campaign_name, @campaign_regex))
group by client_id, account_id, account_name, currency, campaign_id, campaign_name
order by cost_eur desc, conversions desc
limit 250
"""
            return self._run_query(sql, parameters=self._scope_parameters_with_campaign_regex(scope, campaign_regex=campaign_regex))

        return self._cached_query_result("campaigns", (*self._scope_cache_key(scope), campaign_regex), load_campaigns)

    def _keywords_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_keywords() -> list[dict[str, Any]]:
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

        return self._cached_query_result("keywords", self._scope_cache_key(scope), load_keywords)

    def _search_terms_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_search_terms() -> list[dict[str, Any]]:
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

        return self._cached_query_result("search_terms", self._scope_cache_key(scope), load_search_terms)

    def _alerts_query(
        self,
        scope: ScopeFilters,
        *,
        limit: int = 250,
        alert_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        def load_alerts() -> list[dict[str, Any]]:
            alert_type_filter = ""
            parameters = self._scope_parameters(scope)
            if alert_types:
                alert_type_filter = "  and alert_type in unnest(@alert_types)\n"
                parameters = [
                    *parameters,
                    bigquery.ArrayQueryParameter("alert_types", "STRING", list(alert_types)),
                ]
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
{alert_type_filter}
order by
  report_date desc,
  case severity when 'high' then 1 when 'medium' then 2 else 3 end,
  alert_type
limit {limit}
"""
            return self._run_query(sql, parameters=parameters)

        return self._cached_query_result("alerts", (*self._scope_cache_key(scope), limit, *(alert_types or ())), load_alerts)

    def _competition_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_competition() -> list[dict[str, Any]]:
            sql = f"""
select
  report_month,
  competitor_domain,
  impression_share,
  overlap_rate,
  position_above_rate,
  outranking_share
from {self.mart_table('mart_ads_auction_insights_monthly')}
where report_month between date_trunc(@date_from, month) and date_trunc(@date_to, month)
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
order by report_month desc, impression_share desc
limit 60
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("competition", self._scope_cache_key(scope), load_competition)

    def _hour_of_day_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_hour_of_day() -> list[dict[str, Any]]:
            sql = f"""
select
  report_hour,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_hourly_performance_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by report_hour
order by report_hour
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("hour_of_day", self._scope_cache_key(scope), load_hour_of_day)

    def _weekday_profile_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_weekday_profile() -> list[dict[str, Any]]:
            sql = f"""
select
  weekday_number,
  weekday_name,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_hourly_performance_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by weekday_number, weekday_name
order by weekday_number
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("weekday_profile", self._scope_cache_key(scope), load_weekday_profile)

    def _daypart_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_daypart() -> list[dict[str, Any]]:
            sql = f"""
select
  daypart,
  sum(cost_eur) as cost_eur,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_adgroup_daypart')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by daypart
order by daypart
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("daypart", self._scope_cache_key(scope), load_daypart)

    def _daypart_ad_groups_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_daypart_ad_groups() -> list[dict[str, Any]]:
            sql = f"""
with latest_campaigns as (
  select
    client_id,
    account_id,
    campaign_id,
    array_agg(campaign_name order by report_date desc limit 1)[safe_offset(0)] as campaign_name
  from {self.mart_table('mart_ads_campaign_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by client_id, account_id, campaign_id
)
select
  c.campaign_name,
  ad_group_name,
  daypart,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_adgroup_daypart')} d
left join latest_campaigns c
  on d.client_id = c.client_id
 and d.account_id = c.account_id
 and d.campaign_id = c.campaign_id
where d.report_date between @date_from and @date_to
  and (@client_id is null or d.client_id = @client_id)
  and (@account_id is null or d.account_id = @account_id)
group by c.campaign_name, ad_group_name, daypart
order by cost_eur desc, conversions desc
limit 250
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("daypart_ad_groups", self._scope_cache_key(scope), load_daypart_ad_groups)

    def _budget_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_budget() -> list[dict[str, Any]]:
            sql = f"""
select
  client_id,
  account_id,
  account_name,
  campaign_id,
  campaign_name,
  report_date,
  total_cost_eur,
  first_active_hour,
  last_active_hour,
  budget_exhausted_flag
from {self.mart_table('mart_ads_budget_exhaustion')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
order by budget_exhausted_flag desc, report_date desc, total_cost_eur desc
limit 250
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("budget", self._scope_cache_key(scope), load_budget)

    def _zero_conv_campaigns_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_zero_conv_campaigns() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    cost_eur,
    clicks,
    impressions,
    conversions
  from {self.mart_table('mart_ads_campaign_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
  select
    campaign_name,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    safe_divide(sum(clicks), sum(impressions)) as ctr
  from scoped
  group by campaign_name
)
select *
from rolled
where cost_eur > 0 and conversions = 0
order by cost_eur desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("zero_conv_campaigns", self._scope_cache_key(scope), load_zero_conv_campaigns)

    def _zero_conv_ad_groups_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_zero_conv_ad_groups() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    ad_group_name,
    cost_eur,
    clicks,
    impressions,
    conversions
  from {self.mart_table('mart_ads_ad_group_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
  select
    campaign_name,
    ad_group_name,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    safe_divide(sum(clicks), sum(impressions)) as ctr
  from scoped
  group by campaign_name, ad_group_name
)
select *
from rolled
where cost_eur > 0 and conversions = 0
order by cost_eur desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("zero_conv_ad_groups", self._scope_cache_key(scope), load_zero_conv_ad_groups)

    def _zero_conv_keywords_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_zero_conv_keywords() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    ad_group_name,
    keyword_text,
    match_type,
    cost_eur,
    clicks,
    impressions,
    conversions
  from {self.mart_table('mart_ads_keyword_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
  select
    campaign_name,
    ad_group_name,
    keyword_text,
    match_type,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    safe_divide(sum(clicks), sum(impressions)) as ctr
  from scoped
  group by campaign_name, ad_group_name, keyword_text, match_type
)
select *
from rolled
where cost_eur > 0 and conversions = 0
order by cost_eur desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("zero_conv_keywords", self._scope_cache_key(scope), load_zero_conv_keywords)

    def _zero_conv_search_terms_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_zero_conv_search_terms() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    ad_group_name,
    search_term,
    search_term_status,
    cost_eur,
    clicks,
    impressions,
    conversions
  from {self.mart_table('mart_ads_search_terms')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
  select
    campaign_name,
    ad_group_name,
    search_term,
    search_term_status,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    safe_divide(sum(clicks), sum(impressions)) as ctr
  from scoped
  group by campaign_name, ad_group_name, search_term, search_term_status
)
select *
from rolled
where cost_eur > 0 and conversions = 0
order by cost_eur desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("zero_conv_search_terms", self._scope_cache_key(scope), load_zero_conv_search_terms)

    def _campaign_delta_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_campaign_delta() -> list[dict[str, Any]]:
            sql = f"""
with current_period as (
  select
    campaign_id,
    any_value(campaign_name) as campaign_name,
    sum(cost_eur) as current_cost_eur,
    sum(conversions) as current_conversions,
    sum(conversion_value_eur) as current_conversion_value_eur,
    safe_divide(sum(conversion_value_eur), sum(cost_eur)) as current_roas
  from {self.mart_table('mart_ads_campaign_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by campaign_id
),
previous_period as (
  select
    campaign_id,
    any_value(campaign_name) as campaign_name,
    sum(cost_eur) as previous_cost_eur,
    sum(conversions) as previous_conversions,
    sum(conversion_value_eur) as previous_conversion_value_eur,
    safe_divide(sum(conversion_value_eur), sum(cost_eur)) as previous_roas
  from {self.mart_table('mart_ads_campaign_daily')}
  where report_date between @date_from_previous and @date_to_previous
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by campaign_id
)
select
  coalesce(c.campaign_name, p.campaign_name) as campaign_name,
  ifnull(c.current_cost_eur, 0) as current_cost_eur,
  ifnull(p.previous_cost_eur, 0) as previous_cost_eur,
  ifnull(c.current_conversions, 0) as current_conversions,
  ifnull(p.previous_conversions, 0) as previous_conversions,
  ifnull(c.current_conversion_value_eur, 0) as current_conversion_value_eur,
  ifnull(p.previous_conversion_value_eur, 0) as previous_conversion_value_eur,
  ifnull(c.current_roas, 0) as current_roas,
  ifnull(p.previous_roas, 0) as previous_roas,
  ifnull(c.current_conversion_value_eur, 0) - ifnull(p.previous_conversion_value_eur, 0) as value_delta_eur,
  ifnull(c.current_cost_eur, 0) - ifnull(p.previous_cost_eur, 0) as spend_delta_eur,
  ifnull(c.current_roas, 0) - ifnull(p.previous_roas, 0) as roas_delta
from current_period c
full outer join previous_period p
  using (campaign_id)
where coalesce(c.current_cost_eur, 0) > 0 or coalesce(p.previous_cost_eur, 0) > 0
order by value_delta_eur desc, current_cost_eur desc
limit 120
"""
            parameters = [
                bigquery.ScalarQueryParameter("client_id", "STRING", scope.client_id),
                bigquery.ScalarQueryParameter("account_id", "STRING", scope.account_id),
                bigquery.ScalarQueryParameter("date_from", "DATE", scope.date_from),
                bigquery.ScalarQueryParameter("date_to", "DATE", scope.date_to),
                bigquery.ScalarQueryParameter("date_from_previous", "DATE", scope.previous_date_from),
                bigquery.ScalarQueryParameter("date_to_previous", "DATE", scope.previous_date_to),
            ]
            return self._run_query(sql, parameters=parameters)

        return self._cached_query_result("campaign_delta", self._scope_cache_key(scope), load_campaign_delta)

    def _campaign_concentration_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_campaign_concentration() -> list[dict[str, Any]]:
            sql = f"""
with rolled as (
  select
    campaign_name,
    sum(cost_eur) as cost_eur,
    sum(conversion_value_eur) as conversion_value_eur,
    sum(conversions) as conversions
  from {self.mart_table('mart_ads_campaign_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by campaign_name
),
totals as (
  select
    sum(cost_eur) as total_cost_eur,
    sum(conversion_value_eur) as total_conversion_value_eur
  from rolled
)
select
  r.campaign_name,
  r.cost_eur,
  r.conversion_value_eur,
  r.conversions,
  safe_divide(r.conversion_value_eur, r.cost_eur) as roas,
  safe_divide(r.cost_eur, t.total_cost_eur) as spend_share,
  safe_divide(r.conversion_value_eur, t.total_conversion_value_eur) as value_share
from rolled r
cross join totals t
order by r.cost_eur desc
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("campaign_concentration", self._scope_cache_key(scope), load_campaign_concentration)

    def _weekpart_comparison_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_weekpart_comparison() -> list[dict[str, Any]]:
            sql = f"""
select
  case when weekday_number in (6, 7) then 'Weekend' else 'Weekday' end as period_group,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_hourly_performance_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by period_group
order by period_group
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("weekpart_comparison", self._scope_cache_key(scope), load_weekpart_comparison)

    def _day_window_comparison_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_day_window_comparison() -> list[dict[str, Any]]:
            sql = f"""
select
  case when report_hour between 8 and 19 then 'Business hours' else 'Off hours' end as period_group,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_hourly_performance_daily')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by period_group
order by period_group
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("day_window_comparison", self._scope_cache_key(scope), load_day_window_comparison)

    def _coverage_opportunity_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_coverage_opportunities() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    ad_group_name,
    search_term,
    search_term_status,
    cost_eur,
    clicks,
    conversions,
    conversion_value_eur
  from {self.mart_table('mart_ads_search_terms')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
select
  campaign_name,
  ad_group_name,
  search_term,
  search_term_status,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(conversions), sum(clicks)) as conversion_rate,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from scoped
group by campaign_name, ad_group_name, search_term, search_term_status
)
select *
from rolled
where conversions > 0
  and search_term_status not in ('ADDED', 'ADDED_EXCLUDED')
order by conversion_value_eur desc, conversions desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("coverage_opportunities", self._scope_cache_key(scope), load_coverage_opportunities)

    def _negative_candidate_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_negative_candidates() -> list[dict[str, Any]]:
            sql = f"""
with scoped as (
  select
    campaign_name,
    ad_group_name,
    search_term,
    search_term_status,
    cost_eur,
    clicks,
    impressions,
    conversions
  from {self.mart_table('mart_ads_search_terms')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
),
rolled as (
select
  campaign_name,
  ad_group_name,
  search_term,
  search_term_status,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  safe_divide(sum(clicks), sum(impressions)) as ctr
from scoped
group by campaign_name, ad_group_name, search_term, search_term_status
)
select *
from rolled
where conversions = 0
  and cost_eur >= 15
  and clicks >= 10
  and search_term_status != 'ADDED_EXCLUDED'
order by cost_eur desc, clicks desc
limit 100
"""
            return self._run_query(sql, parameters=self._scope_parameters(scope))

        return self._cached_query_result("negative_candidates", self._scope_cache_key(scope), load_negative_candidates)

    def _ad_delta_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        def load_ad_delta() -> list[dict[str, Any]]:
            sql = f"""
with current_period as (
  select
    ad_id,
    any_value(campaign_name) as campaign_name,
    any_value(ad_group_name) as ad_group_name,
    any_value(ad_name) as ad_name,
    any_value(headline_primary) as headline_primary,
    sum(cost_eur) as current_cost_eur,
    sum(conversions) as current_conversions,
    sum(conversion_value_eur) as current_conversion_value_eur,
    safe_divide(sum(conversion_value_eur), sum(cost_eur)) as current_roas
  from {self.mart_table('mart_ads_ad_performance_daily')}
  where report_date between @date_from and @date_to
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by ad_id
),
previous_period as (
  select
    ad_id,
    sum(cost_eur) as previous_cost_eur,
    sum(conversions) as previous_conversions,
    sum(conversion_value_eur) as previous_conversion_value_eur,
    safe_divide(sum(conversion_value_eur), sum(cost_eur)) as previous_roas
  from {self.mart_table('mart_ads_ad_performance_daily')}
  where report_date between @date_from_previous and @date_to_previous
    and (@client_id is null or client_id = @client_id)
    and (@account_id is null or account_id = @account_id)
  group by ad_id
)
select
  c.campaign_name,
  c.ad_group_name,
  coalesce(c.ad_name, c.headline_primary, cast(c.ad_id as string)) as ad_label,
  ifnull(c.current_cost_eur, 0) as current_cost_eur,
  ifnull(p.previous_cost_eur, 0) as previous_cost_eur,
  ifnull(c.current_conversions, 0) as current_conversions,
  ifnull(p.previous_conversions, 0) as previous_conversions,
  ifnull(c.current_conversion_value_eur, 0) as current_conversion_value_eur,
  ifnull(p.previous_conversion_value_eur, 0) as previous_conversion_value_eur,
  ifnull(c.current_roas, 0) as current_roas,
  ifnull(p.previous_roas, 0) as previous_roas,
  ifnull(c.current_conversion_value_eur, 0) - ifnull(p.previous_conversion_value_eur, 0) as value_delta_eur,
  ifnull(c.current_roas, 0) - ifnull(p.previous_roas, 0) as roas_delta
from current_period c
left join previous_period p using (ad_id)
where ifnull(c.current_cost_eur, 0) > 0
order by value_delta_eur desc, current_cost_eur desc
limit 160
"""
            parameters = [
                bigquery.ScalarQueryParameter("client_id", "STRING", scope.client_id),
                bigquery.ScalarQueryParameter("account_id", "STRING", scope.account_id),
                bigquery.ScalarQueryParameter("date_from", "DATE", scope.date_from),
                bigquery.ScalarQueryParameter("date_to", "DATE", scope.date_to),
                bigquery.ScalarQueryParameter("date_from_previous", "DATE", scope.previous_date_from),
                bigquery.ScalarQueryParameter("date_to_previous", "DATE", scope.previous_date_to),
            ]
            return self._run_query(sql, parameters=parameters)

        return self._cached_query_result("ad_delta", self._scope_cache_key(scope), load_ad_delta)

    def _build_status_cards(
        self,
        summary: dict[str, Any],
        previous_summary: dict[str, Any],
        competition: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        hour_of_day: list[dict[str, Any]],
        budget_rows: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        roas_delta = _delta_pct(summary.get("roas"), previous_summary.get("roas"))
        exhausted_rows = [row for row in budget_rows if row.get("budget_exhausted_flag")]
        high_alerts = [row for row in alerts if row.get("severity") == "high"]

        competitor_card = {
            "title": "Competition",
            "tone": "neutral",
            "detail": "No auction insights loaded yet.",
        }
        if competition:
            top_competitor = next((row for row in competition if row.get("competitor_domain")), competition[0])
            competitor_card = {
                "title": "Competition",
                "tone": "warning" if _as_float(top_competitor.get("impression_share")) >= 0.2 else "neutral",
                "detail": f"{top_competitor['competitor_domain']} latest IS {top_competitor.get('impression_share', 0):.1%}",
            }

        timing_card = {
            "title": "Timing",
            "tone": "neutral",
            "detail": "No hourly signal available.",
        }
        if hour_of_day:
            best_hour = max(
                hour_of_day,
                key=lambda row: (_as_float(row.get("conversion_value_eur")), _as_float(row.get("roas"))),
            )
            timing_card = {
                "title": "Timing",
                "tone": "positive",
                "detail": f"Best hour {int(best_hour['report_hour']):02d}:00, ROAS {(_as_float(best_hour.get('roas'))):.2f}x",
            }

        return [
            {
                "title": "Efficiency",
                "tone": "negative" if roas_delta is not None and roas_delta < -0.1 else "positive",
                "detail": f"ROAS {_fmt_pct(roas_delta)} vs previous window",
            },
            {
                "title": "Budget",
                "tone": "warning" if exhausted_rows else "positive",
                "detail": (
                    f"{len(exhausted_rows)} exhausted campaign-day rows flagged"
                    if exhausted_rows
                    else "No budget exhaustion flagged in range"
                ),
            },
            competitor_card,
            {
                "title": "Alerts",
                "tone": "warning" if high_alerts else "neutral",
                "detail": (
                    f"{len(high_alerts)} high-severity alerts, {len(alerts)} total"
                    if alerts
                    else "No alerts in range"
                ),
            },
            timing_card,
        ]

    def _build_management_conclusions(
        self,
        summary: dict[str, Any],
        previous_summary: dict[str, Any],
        competition: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
        budget_rows: list[dict[str, Any]],
        hour_of_day: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        conclusions: list[dict[str, str]] = []

        conversions_delta = _delta_pct(summary.get("conversions"), previous_summary.get("conversions"))
        roas_delta = _delta_pct(summary.get("roas"), previous_summary.get("roas"))

        conclusions.append(
            {
                "title": "Volume trend",
                "detail": (
                    f"Conversions are {_fmt_pct(conversions_delta)} versus the prior window."
                    if conversions_delta is not None
                    else "No prior conversion baseline is available for this range."
                ),
            }
        )
        conclusions.append(
            {
                "title": "Efficiency trend",
                "detail": (
                    f"ROAS is {_fmt_pct(roas_delta)} versus the prior window."
                    if roas_delta is not None
                    else "ROAS has no previous-period baseline."
                ),
            }
        )

        exhausted_rows = [row for row in budget_rows if row.get("budget_exhausted_flag")]
        conclusions.append(
            {
                "title": "Budget risk",
                "detail": (
                    f"{len(exhausted_rows)} campaign-day rows show early budget exhaustion in the selected range."
                    if exhausted_rows
                    else "No early budget exhaustion was flagged in the selected range."
                ),
            }
        )

        flagged_keywords = [row for row in keywords if row.get("audit_reason") != "ok"]
        conclusions.append(
            {
                "title": "Keyword pressure",
                "detail": (
                    f"{len(flagged_keywords)} keyword rows are flagged for bid, quality, or intent issues."
                    if flagged_keywords
                    else "No flagged keyword issues are present in the selected range."
                ),
            }
        )

        if competition:
            top_competitor = next((row for row in competition if row.get("competitor_domain")), competition[0])
            conclusions.append(
                {
                    "title": "Competitive pressure",
                    "detail": f"Latest visible competitor signal: {top_competitor['competitor_domain']} at {top_competitor.get('impression_share', 0):.1%} impression share.",
                }
            )

        if hour_of_day:
            best_hour = max(
                hour_of_day,
                key=lambda row: (_as_float(row.get("conversion_value_eur")), _as_float(row.get("roas"))),
            )
            conclusions.append(
                {
                    "title": "Timing opportunity",
                    "detail": f"Best conversion-value hour in the selected range is {int(best_hour['report_hour']):02d}:00.",
                }
            )

        return conclusions[:5]

    def _build_report_cards(
        self,
        campaigns: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        budget_rows: list[dict[str, Any]],
        weekday_profile: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        flagged_keywords = [row for row in keywords if row.get("audit_reason") != "ok"]
        exhausted_rows = [row for row in budget_rows if row.get("budget_exhausted_flag")]
        best_weekday = max(
            weekday_profile,
            key=lambda row: (_as_float(row.get("conversion_value_eur")), _as_float(row.get("roas"))),
        ) if weekday_profile else None

        return [
            {
                "report_name": "overview",
                "title": "High-level overview",
                "description": "KPI trend, campaign mix, and competitive context.",
                "meta": f"{len(campaigns)} campaigns in scope",
            },
            {
                "report_name": "keywords",
                "title": "Keyword and query audit",
                "description": "Issue buckets, wasted spend, and search-term coverage.",
                "meta": f"{len(flagged_keywords)} flagged keyword rows",
            },
            {
                "report_name": "timing",
                "title": "Timing analysis",
                "description": "Hour-of-day, day-of-week, daypart, and budget pacing.",
                "meta": (
                    f"Best weekday: {best_weekday['weekday_name']}"
                    if best_weekday
                    else "Timing profile ready"
                ),
            },
            {
                "report_name": "alerts",
                "title": "Action queue",
                "description": "Consolidated issues and budget flags that need review.",
                "meta": f"{len(alerts)} alerts, {len(exhausted_rows)} budget flags",
            },
            {
                "report_name": "efficiency",
                "title": "Efficiency lab",
                "description": "Zero-conversion spend, winners and losers, and concentration risk.",
                "meta": "Loss and dependency review",
            },
            {
                "report_name": "coverage",
                "title": "Query coverage",
                "description": "Coverage opportunities and negative-keyword candidates.",
                "meta": "Search-term action list",
            },
            {
                "report_name": "creative",
                "title": "Creative performance",
                "description": "Ad winners and losers versus the prior period.",
                "meta": "Ad-level change review",
            },
        ]

    def get_hub_data(
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
        summary = self._summary_query(scope)[0]
        previous_summary = self._summary_query(scope, previous=True)[0]
        trend = self._trend_query(scope)
        previous_trend = self._trend_query(scope, previous=True)
        campaigns = self._campaigns_query(scope)
        keywords = self._keywords_query(scope)
        alerts = self._alerts_query(scope, limit=50)
        competition = self._competition_query(scope)
        hour_of_day = self._hour_of_day_query(scope)
        weekday_profile = self._weekday_profile_query(scope)
        budget_rows = self._budget_query(scope)

        return {
            "scope": self._scope_payload(scope),
            "summary": summary,
            "previous_summary": previous_summary,
            "status_cards": self._build_status_cards(summary, previous_summary, competition, alerts, hour_of_day, budget_rows),
            "management_conclusions": self._build_management_conclusions(summary, previous_summary, competition, keywords, budget_rows, hour_of_day),
            "report_cards": self._build_report_cards(campaigns, keywords, alerts, budget_rows, weekday_profile),
            "trend": trend,
            "previous_trend": previous_trend,
            "top_alerts": alerts,
        }

    def get_overview_data(
        self,
        *,
        client_id: str | None,
        account_id: str | None,
        date_from: date | None,
        date_to: date | None,
        campaign_regex: str | None = None,
    ) -> dict[str, Any]:
        scope = self.resolve_scope(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        summary = self._summary_query(scope)[0]
        previous_summary = self._summary_query(scope, previous=True)[0]
        competition = self._competition_query(scope)
        campaign_filter_options = [row["campaign_name"] for row in self._campaigns_query(scope)[:10]]
        budget_rows = self._budget_query(scope)
        alerts = self._alerts_query(scope, limit=50)
        hour_of_day = self._hour_of_day_query(scope)
        return {
            "scope": self._scope_payload(scope),
            "summary": summary,
            "previous_summary": previous_summary,
            "trend": self._trend_query(scope, campaign_regex=campaign_regex),
            "previous_trend": self._trend_query(scope, campaign_regex=campaign_regex, previous=True),
            "campaigns": self._campaigns_query(scope, campaign_regex=campaign_regex),
            "campaign_filter_options": campaign_filter_options,
            "competition": competition,
            "competition_note": (
                "No auction insights data is currently available in the reporting mart for this account and selected period."
                if not competition
                else "Monthly auction insights rows are shown only when competitor-domain data exists for the selected period."
            ),
            "status_cards": self._build_status_cards(summary, previous_summary, competition, alerts, hour_of_day, budget_rows),
            "campaign_regex": campaign_regex,
        }

    def get_keywords_data(
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
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "keywords": self._keywords_query(scope),
            "search_terms": self._search_terms_query(scope),
            "alerts": self._alerts_query(scope, limit=100, alert_types=("keyword_issue",)),
            "alerts_definition": "This table only includes keyword_issue alerts generated from the same filtered account and date range.",
        }

    def get_timing_data(
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
        hour_of_day = self._hour_of_day_query(scope)
        weekday_profile = self._weekday_profile_query(scope)
        budget_rows = self._budget_query(scope)
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "hour_of_day": hour_of_day,
            "weekday_profile": weekday_profile,
            "weekpart_comparison": self._weekpart_comparison_query(scope),
            "day_window_comparison": self._day_window_comparison_query(scope),
            "daypart": self._daypart_query(scope),
            "daypart_ad_groups": self._daypart_ad_groups_query(scope),
            "budget_flags": budget_rows,
            "budget_flags_definition": (
                "A flagged row means the campaign had meaningful spend, started serving after 07:00, "
                "and then stopped spending several hours before the day ended. It is a pacing heuristic, "
                "not proof of a hard campaign-budget cap."
            ),
            "timing_highlights": self._build_timing_highlights(hour_of_day, weekday_profile, budget_rows),
        }

    def get_efficiency_data(
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
        campaign_delta = self._campaign_delta_query(scope)
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "zero_conv_campaigns": self._zero_conv_campaigns_query(scope),
            "zero_conv_ad_groups": self._zero_conv_ad_groups_query(scope),
            "zero_conv_keywords": self._zero_conv_keywords_query(scope),
            "zero_conv_search_terms": self._zero_conv_search_terms_query(scope),
            "campaign_winners": [row for row in campaign_delta if _as_float(row.get("value_delta_eur")) > 0][:20],
            "campaign_losers": sorted(
                [row for row in campaign_delta if _as_float(row.get("value_delta_eur")) < 0],
                key=lambda row: _as_float(row.get("value_delta_eur")),
            )[:20],
            "campaign_concentration": self._campaign_concentration_query(scope),
        }

    def get_coverage_data(
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
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "coverage_opportunities": self._coverage_opportunity_query(scope),
            "negative_candidates": self._negative_candidate_query(scope),
        }

    def get_creative_data(
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
        ad_delta = self._ad_delta_query(scope)
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "ad_winners": [row for row in ad_delta if _as_float(row.get("value_delta_eur")) > 0][:20],
            "ad_losers": sorted(
                [row for row in ad_delta if _as_float(row.get("value_delta_eur")) < 0],
                key=lambda row: _as_float(row.get("value_delta_eur")),
            )[:20],
        }

    def get_alerts_data(
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
        return {
            "scope": self._scope_payload(scope),
            "summary": self._summary_query(scope)[0],
            "previous_summary": self._summary_query(scope, previous=True)[0],
            "alerts": self._alerts_query(scope),
            "budget_flags": self._budget_query(scope),
        }

    def get_report_data(
        self,
        report_name: str,
        *,
        client_id: str | None,
        account_id: str | None,
        date_from: date | None,
        date_to: date | None,
        campaign_regex: str | None = None,
    ) -> dict[str, Any]:
        if report_name == "overview":
            return self.get_overview_data(
                client_id=client_id,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                campaign_regex=campaign_regex,
            )
        if report_name == "keywords":
            return self.get_keywords_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "timing":
            return self.get_timing_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "alerts":
            return self.get_alerts_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "efficiency":
            return self.get_efficiency_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "coverage":
            return self.get_coverage_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "creative":
            return self.get_creative_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        raise ValueError(f"Unknown report: {report_name}")

    def _build_timing_highlights(
        self,
        hour_of_day: list[dict[str, Any]],
        weekday_profile: list[dict[str, Any]],
        budget_rows: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        highlights: list[dict[str, str]] = []
        if hour_of_day:
            best_hour = max(hour_of_day, key=lambda row: (_as_float(row.get("conversion_value_eur")), _as_float(row.get("roas"))))
            highlights.append(
                {
                    "title": "Best hour",
                    "detail": f"{int(best_hour['report_hour']):02d}:00 drives the strongest conversion value in the selected range.",
                }
            )
        if weekday_profile:
            best_weekday = max(weekday_profile, key=lambda row: (_as_float(row.get("conversion_value_eur")), _as_float(row.get("roas"))))
            highlights.append(
                {
                    "title": "Best weekday",
                    "detail": f"{best_weekday['weekday_name']} is the strongest day by conversion value.",
                }
            )
        exhausted_rows = [row for row in budget_rows if row.get("budget_exhausted_flag")]
        highlights.append(
            {
                "title": "Budget pacing",
                "detail": (
                    f"{len(exhausted_rows)} campaign-day rows show budget exhaustion before the end of the day."
                    if exhausted_rows
                    else "No budget exhaustion is flagged in the selected range."
                ),
            }
        )
        return highlights

    def _scope_payload(self, scope: ScopeFilters) -> dict[str, str | None]:
        return {
            "client_id": scope.client_id,
            "account_id": scope.account_id,
            "date_from": scope.date_from.isoformat(),
            "date_to": scope.date_to.isoformat(),
            "previous_date_from": scope.previous_date_from.isoformat(),
            "previous_date_to": scope.previous_date_to.isoformat(),
        }

    def get_dashboard_data(
        self,
        *,
        client_id: str | None,
        account_id: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        return self.get_overview_data(
            client_id=client_id,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )


@lru_cache(maxsize=1)
def get_reporting_service() -> BigQueryReportingService:
    return BigQueryReportingService(get_settings())
