with perf as (
    select * from {{ ref('stg_keyword_performance_daily') }}
),
keywords as (
    select * from {{ ref('stg_keyword_dimension_latest') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
),
ad_groups as (
    select * from {{ ref('stg_ad_group_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
fx_daily as (
    select * from {{ ref('stg_account_fx_rates_daily') }}
),
fx_latest as (
    select * from {{ ref('stg_exchange_rates_latest') }}
),
thresholds as (
    select
        max(case when threshold_key = 'min_keyword_spend_eur' then threshold_value end) as min_keyword_spend_eur,
        max(case when threshold_key = 'min_keyword_clicks' then threshold_value end) as min_keyword_clicks,
        max(case when threshold_key = 'low_quality_score' then threshold_value end) as low_quality_score
    from {{ ref('cfg_thresholds') }}
    where client_id = 'default'
),
perf_enriched as (
    select
        p.transfer_source,
        a.client_id,
        p.account_id,
        a.account_name,
        a.currency,
        p.campaign_id,
        p.ad_group_id,
        p.keyword_id,
        p.report_date,
        p.cost_original,
        safe_multiply(p.cost_original, fxd.eur_exchange_rate) as cost_eur,
        p.clicks,
        p.impressions,
        p.conversions,
        p.conversion_value_original,
        safe_multiply(p.conversion_value_original, fxd.eur_exchange_rate) as conversion_value_eur
    from perf p
    join accounts a
        on p.account_id = cast(a.account_id as string)
       and a.is_active = true
    left join fx_daily fxd
        on p.account_id = fxd.account_id
       and p.report_date = fxd.report_date
),
rolled as (
    select
        transfer_source,
        client_id,
        account_id,
        account_name,
        currency,
        campaign_id,
        ad_group_id,
        keyword_id,
        min(report_date) as report_date_start,
        max(report_date) as report_date_end,
        sum(cost_original) as cost_original,
        sum(cost_eur) as cost_eur,
        sum(clicks) as clicks,
        sum(impressions) as impressions,
        sum(conversions) as conversions,
        sum(conversion_value_original) as conversion_value_original,
        sum(conversion_value_eur) as conversion_value_eur
    from perf_enriched
    group by 1, 2, 3, 4, 5, 6, 7, 8
)

select
    r.client_id,
    r.account_id,
    r.account_name,
    r.currency,
    r.campaign_id,
    c.campaign_name,
    r.ad_group_id,
    g.ad_group_name,
    r.keyword_id,
    r.report_date_start,
    r.report_date_end,
    k.keyword_text,
    k.match_type,
    k.keyword_status,
    k.quality_score,
    k.first_page_cpc_original,
    safe_multiply(k.first_page_cpc_original, fxl.eur_exchange_rate) as first_page_cpc_eur,
    k.top_of_page_cpc_original,
    safe_multiply(k.top_of_page_cpc_original, fxl.eur_exchange_rate) as top_of_page_cpc_eur,
    r.cost_original,
    r.cost_eur,
    r.clicks,
    r.impressions,
    r.conversions,
    r.conversion_value_original,
    r.conversion_value_eur,
    safe_divide(r.cost_original, r.conversions) as cpa_original,
    safe_divide(r.cost_eur, r.conversions) as cpa_eur,
    case
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 and coalesce(k.quality_score, 10) < t.low_quality_score then 'low_qs'
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 and r.clicks >= t.min_keyword_clicks then 'intent_or_offer'
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 then 'low_volume'
        when r.conversions > 0 and coalesce(k.quality_score, 10) < t.low_quality_score then 'scale_but_fix_qs'
        else 'ok'
    end as audit_reason
from rolled r
left join keywords k
    on r.transfer_source = k.transfer_source
   and r.account_id = k.account_id
   and r.campaign_id = k.campaign_id
   and r.ad_group_id = k.ad_group_id
   and r.keyword_id = k.keyword_id
left join campaigns c
    on r.transfer_source = c.transfer_source
   and r.account_id = c.account_id
   and r.campaign_id = c.campaign_id
left join ad_groups g
    on r.transfer_source = g.transfer_source
   and r.account_id = g.account_id
   and r.campaign_id = g.campaign_id
   and r.ad_group_id = g.ad_group_id
left join fx_latest fxl
    on r.currency = fxl.currency
cross join thresholds t
