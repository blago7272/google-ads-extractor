with stats as (
    select * from {{ ref('stg_ad_group_stats_daily') }}
),
ad_groups as (
    select * from {{ ref('stg_ad_group_dimension_latest') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
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
        s.report_date,
        s.cost_original,
        safe_multiply(s.cost_original, fxd.eur_exchange_rate) as cost_eur,
        s.clicks,
        s.impressions,
        s.conversions,
        s.conversion_value_original,
        safe_multiply(s.conversion_value_original, fxd.eur_exchange_rate) as conversion_value_eur,
        safe_divide(s.clicks, s.impressions) as ctr,
        safe_divide(s.cost_original, s.clicks) as cpc_original,
        safe_multiply(safe_divide(s.cost_original, s.clicks), fxd.eur_exchange_rate) as cpc_eur,
        safe_divide(s.cost_original, s.conversions) as cpa_original,
        safe_multiply(safe_divide(s.cost_original, s.conversions), fxd.eur_exchange_rate) as cpa_eur,
        safe_divide(s.conversion_value_original, s.cost_original) as roas
    from stats s
    left join ad_groups g
        on s.transfer_source = g.transfer_source
       and s.account_id = g.account_id
       and s.campaign_id = g.campaign_id
       and s.ad_group_id = g.ad_group_id
    left join campaigns c
        on s.transfer_source = c.transfer_source
       and s.account_id = c.account_id
       and s.campaign_id = c.campaign_id
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
