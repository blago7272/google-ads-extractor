with hourly as (
    select * from {{ ref('stg_ad_group_stats_hourly') }}
),
ad_groups as (
    select * from {{ ref('stg_ad_group_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
bucketed as (
    select
        transfer_source,
        account_id,
        campaign_id,
        ad_group_id,
        case
            when report_hour between 0 and 6 then 'night'
            else 'day'
        end as daypart,
        sum(cost_eur) as cost_eur,
        sum(clicks) as clicks,
        sum(impressions) as impressions,
        sum(conversions) as conversions,
        sum(conversion_value) as conversion_value
    from hourly
    group by 1, 2, 3, 4, 5
)

select
    a.client_id,
    b.account_id,
    a.account_name,
    b.campaign_id,
    b.ad_group_id,
    g.ad_group_name,
    b.daypart,
    b.cost_eur,
    b.clicks,
    b.impressions,
    b.conversions,
    b.conversion_value,
    safe_divide(b.cost_eur, b.conversions) as cpa,
    safe_divide(b.conversion_value, b.cost_eur) as roas
from bucketed b
left join ad_groups g
    on b.transfer_source = g.transfer_source
   and b.account_id = g.account_id
   and b.campaign_id = g.campaign_id
   and b.ad_group_id = g.ad_group_id
left join accounts a
    on b.account_id = cast(a.account_id as string)

