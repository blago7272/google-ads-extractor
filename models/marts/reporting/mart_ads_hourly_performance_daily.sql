with hourly as (
    select * from {{ ref('stg_campaign_stats_hourly') }}
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
rolled as (
    select
        a.client_id,
        h.account_id,
        a.account_name,
        a.timezone,
        a.currency,
        h.report_date,
        case
            when extract(dayofweek from h.report_date) = 1 then 7
            else extract(dayofweek from h.report_date) - 1
        end as weekday_number,
        format_date('%A', h.report_date) as weekday_name,
        h.report_hour,
        sum(h.cost_original) as cost_original,
        sum(safe_multiply(h.cost_original, fxd.eur_exchange_rate)) as cost_eur,
        sum(h.clicks) as clicks,
        sum(h.impressions) as impressions,
        sum(h.conversions) as conversions,
        sum(h.conversion_value_original) as conversion_value_original,
        sum(safe_multiply(h.conversion_value_original, fxd.eur_exchange_rate)) as conversion_value_eur
    from hourly h
    join accounts a
        on h.account_id = cast(a.account_id as string)
       and a.is_active = true
    join healthy_accounts ha
        on h.account_id = ha.account_id
    left join fx_daily fxd
        on h.account_id = fxd.account_id
       and h.report_date = fxd.report_date
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
)

select
    client_id,
    account_id,
    account_name,
    timezone,
    currency,
    report_date,
    weekday_number,
    weekday_name,
    report_hour,
    cost_original,
    cost_eur,
    clicks,
    impressions,
    conversions,
    conversion_value_original,
    conversion_value_eur,
    safe_divide(clicks, impressions) as ctr,
    safe_divide(cost_original, clicks) as cpc_original,
    safe_divide(cost_eur, clicks) as cpc_eur,
    safe_divide(cost_original, conversions) as cpa_original,
    safe_divide(cost_eur, conversions) as cpa_eur,
    safe_divide(conversion_value_eur, cost_eur) as roas
from rolled
