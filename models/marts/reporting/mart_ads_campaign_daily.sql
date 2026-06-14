with stats as (
    select * from {{ ref('stg_campaign_stats_daily') }}
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
fx_latest as (
    select * from {{ ref('stg_exchange_rates_latest') }}
),
base as (
    select
        a.client_id,
        s.account_id,
        a.account_name,
        a.currency,
        s.campaign_id,
        c.campaign_name,
        c.campaign_status,
        c.campaign_serving_status,
        c.campaign_channel_type,
        c.campaign_channel_sub_type,
        c.bidding_strategy_type,
        c.campaign_budget_original,
        safe_multiply(c.campaign_budget_original, fxl.eur_exchange_rate) as campaign_budget_eur,
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
    left join fx_latest fxl
        on a.currency = fxl.currency
)

select
    client_id,
    account_id,
    account_name,
    currency,
    campaign_id,
    campaign_name,
    campaign_status,
    campaign_serving_status,
    campaign_channel_type,
    campaign_channel_sub_type,
    bidding_strategy_type,
    campaign_budget_original,
    campaign_budget_eur,
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
