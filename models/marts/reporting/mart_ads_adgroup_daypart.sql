with hourly as (
    select * from {{ ref('stg_ad_group_stats_hourly') }}
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
hourly_enriched as (
    select
        h.transfer_source,
        a.client_id,
        h.account_id,
        a.account_name,
        a.currency,
        h.campaign_id,
        h.ad_group_id,
        h.report_date,
        h.report_hour,
        h.cost_original,
        safe_multiply(h.cost_original, fxd.eur_exchange_rate) as cost_eur,
        h.clicks,
        h.impressions,
        h.conversions,
        h.conversion_value_original,
        safe_multiply(h.conversion_value_original, fxd.eur_exchange_rate) as conversion_value_eur
    from hourly h
    join accounts a
        on h.account_id = cast(a.account_id as string)
       and a.is_active = true
    left join fx_daily fxd
        on h.account_id = fxd.account_id
       and h.report_date = fxd.report_date
),
bucketed as (
    select
        transfer_source,
        client_id,
        account_id,
        account_name,
        currency,
        campaign_id,
        ad_group_id,
        case
            when report_hour between 0 and 6 then 'night'
            else 'day'
        end as daypart,
        sum(cost_original) as cost_original,
        sum(cost_eur) as cost_eur,
        sum(clicks) as clicks,
        sum(impressions) as impressions,
        sum(conversions) as conversions,
        sum(conversion_value_original) as conversion_value_original,
        sum(conversion_value_eur) as conversion_value_eur
    from hourly_enriched
    group by 1, 2, 3, 4, 5, 6, 7, 8
)

select
    b.client_id,
    b.account_id,
    b.account_name,
    b.currency,
    b.campaign_id,
    b.ad_group_id,
    g.ad_group_name,
    b.daypart,
    b.cost_original,
    b.cost_eur,
    b.clicks,
    b.impressions,
    b.conversions,
    b.conversion_value_original,
    b.conversion_value_eur,
    safe_divide(b.cost_original, b.conversions) as cpa_original,
    safe_divide(b.cost_eur, b.conversions) as cpa_eur,
    safe_divide(b.conversion_value_eur, b.cost_eur) as roas
from bucketed b
left join ad_groups g
    on b.transfer_source = g.transfer_source
   and b.account_id = g.account_id
   and b.campaign_id = g.campaign_id
   and b.ad_group_id = g.ad_group_id
