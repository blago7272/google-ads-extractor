with stats as (
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
healthy_accounts as (
    select account_id from {{ ref('stg_account_freshness') }} where freshness_status = 'healthy'
),
fx_daily as (
    select * from {{ ref('stg_account_fx_rates_daily') }}
),
base as (
    select
        a.client_id,
        s.account_id,
        a.account_name,
        a.currency,
        s.campaign_id,
        c.campaign_name,
        s.ad_group_id,
        g.ad_group_name,
        s.keyword_id,
        k.keyword_text,
        k.match_type,
        k.keyword_status,
        k.quality_score,
        s.report_date,
        s.cost_original,
        safe_multiply(s.cost_original, fxd.eur_exchange_rate) as cost_eur,
        s.clicks,
        s.impressions,
        s.conversions,
        s.conversion_value_original,
        safe_multiply(s.conversion_value_original, fxd.eur_exchange_rate) as conversion_value_eur,
        s.ctr,
        s.cpc_original,
        safe_multiply(s.cpc_original, fxd.eur_exchange_rate) as cpc_eur,
        s.cpa_original,
        safe_multiply(s.cpa_original, fxd.eur_exchange_rate) as cpa_eur,
        s.roas
    from stats s
    left join keywords k
        on s.transfer_source = k.transfer_source
       and s.account_id = k.account_id
       and s.campaign_id = k.campaign_id
       and s.ad_group_id = k.ad_group_id
       and s.keyword_id = k.keyword_id
    left join campaigns c
        on s.transfer_source = c.transfer_source
       and s.account_id = c.account_id
       and s.campaign_id = c.campaign_id
    left join ad_groups g
        on s.transfer_source = g.transfer_source
       and s.account_id = g.account_id
       and s.campaign_id = g.campaign_id
       and s.ad_group_id = g.ad_group_id
    join accounts a
        on s.account_id = cast(a.account_id as string)
       and a.is_active = true
    join healthy_accounts ha
        on s.account_id = ha.account_id
    left join fx_daily fxd
        on s.account_id = fxd.account_id
       and s.report_date = fxd.report_date
)

select
    client_id,
    account_id,
    account_name,
    currency,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    keyword_id,
    keyword_text,
    match_type,
    keyword_status,
    quality_score,
    report_date,
    cost_original,
    cost_eur,
    clicks,
    impressions,
    conversions,
    conversion_value_original,
    conversion_value_eur,
    ctr,
    cpc_original,
    cpc_eur,
    cpa_original,
    cpa_eur,
    roas
from base
