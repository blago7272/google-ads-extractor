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

    def _summary_query(self, scope: ScopeFilters, *, previous: bool = False) -> list[dict[str, Any]]:
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

    def _alerts_query(self, scope: ScopeFilters, *, limit: int = 250) -> list[dict[str, Any]]:
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
order by
  report_date desc,
  case severity when 'high' then 1 when 'medium' then 2 else 3 end,
  alert_type
limit {limit}
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _competition_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
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

    def _hour_of_day_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  report_hour,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(clicks), sum(impressions)) as ctr,
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

    def _weekday_profile_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
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

    def _daypart_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
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

    def _daypart_ad_groups_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
        sql = f"""
select
  ad_group_name,
  daypart,
  sum(cost_eur) as cost_eur,
  sum(clicks) as clicks,
  sum(impressions) as impressions,
  sum(conversions) as conversions,
  sum(conversion_value_eur) as conversion_value_eur,
  safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
  safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from {self.mart_table('mart_ads_adgroup_daypart')}
where report_date between @date_from and @date_to
  and (@client_id is null or client_id = @client_id)
  and (@account_id is null or account_id = @account_id)
group by ad_group_name, daypart
order by cost_eur desc, conversions desc
limit 250
"""
        return self._run_query(sql, parameters=self._scope_parameters(scope))

    def _budget_query(self, scope: ScopeFilters) -> list[dict[str, Any]]:
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
            "trend": trend[-14:],
            "top_alerts": alerts[:8],
        }

    def get_overview_data(
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
        competition = self._competition_query(scope)
        budget_rows = self._budget_query(scope)
        alerts = self._alerts_query(scope, limit=50)
        hour_of_day = self._hour_of_day_query(scope)
        return {
            "scope": self._scope_payload(scope),
            "summary": summary,
            "previous_summary": previous_summary,
            "trend": self._trend_query(scope),
            "campaigns": self._campaigns_query(scope),
            "competition": competition,
            "status_cards": self._build_status_cards(summary, previous_summary, competition, alerts, hour_of_day, budget_rows),
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
            "alerts": self._alerts_query(scope, limit=100),
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
            "daypart": self._daypart_query(scope),
            "daypart_ad_groups": self._daypart_ad_groups_query(scope),
            "budget_flags": budget_rows,
            "timing_highlights": self._build_timing_highlights(hour_of_day, weekday_profile, budget_rows),
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
    ) -> dict[str, Any]:
        if report_name == "overview":
            return self.get_overview_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "keywords":
            return self.get_keywords_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "timing":
            return self.get_timing_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
        if report_name == "alerts":
            return self.get_alerts_data(client_id=client_id, account_id=account_id, date_from=date_from, date_to=date_to)
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
