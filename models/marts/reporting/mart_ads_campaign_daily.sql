with stats as (
    select * from {{ ref('stg_campaign_stats_daily') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
)

select
    a.client_id,
    s.account_id,
    a.account_name,
    s.campaign_id,
    c.campaign_name,
    c.campaign_status,
    c.campaign_serving_status,
    c.campaign_channel_type,
    c.campaign_channel_sub_type,
    c.bidding_strategy_type,
    c.campaign_budget_eur,
    s.report_date,
    s.cost_eur,
    s.clicks,
    s.impressions,
    s.conversions,
    s.conversion_value,
    s.ctr,
    s.cpc,
    s.cpa,
    s.roas
from stats s
left join campaigns c
    on s.transfer_source = c.transfer_source
   and s.account_id = c.account_id
   and s.campaign_id = c.campaign_id
left join accounts a
    on s.account_id = cast(a.account_id as string)

