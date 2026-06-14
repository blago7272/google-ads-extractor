with account_stats as (
    select * from {{ ref('stg_account_stats_daily') }}
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
        a.timezone,
        a.currency,
        s.report_date,
        s.cost_original,
        safe_multiply(s.cost_original, fx.eur_exchange_rate) as cost_eur,
        s.clicks,
        s.impressions,
        s.conversions,
        s.conversion_value_original,
        safe_multiply(s.conversion_value_original, fx.eur_exchange_rate) as conversion_value_eur,
        s.ctr,
        s.cpc_original,
        safe_multiply(s.cpc_original, fx.eur_exchange_rate) as cpc_eur,
        s.cpa_original,
        safe_multiply(s.cpa_original, fx.eur_exchange_rate) as cpa_eur,
        s.roas
    from account_stats s
    join accounts a
        on s.account_id = cast(a.account_id as string)
       and a.is_active = true
    join healthy_accounts ha
        on s.account_id = ha.account_id
    left join fx_daily fx
        on s.account_id = fx.account_id
       and s.report_date = fx.report_date
)

select
    client_id,
    account_id,
    account_name,
    timezone,
    currency,
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
