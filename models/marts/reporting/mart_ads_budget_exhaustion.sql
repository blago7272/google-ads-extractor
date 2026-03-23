with hourly as (
    select * from {{ ref('stg_campaign_stats_hourly') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
thresholds as (
    select
        max(case when threshold_key = 'budget_exhausted_zero_spend_hours' then threshold_value end) as zero_spend_hours,
        max(case when threshold_key = 'budget_exhausted_min_cost_eur' then threshold_value end) as min_cost_eur
    from {{ ref('cfg_thresholds') }}
    where client_id = 'default'
),
hourly_rollup as (
    select
        transfer_source,
        account_id,
        campaign_id,
        report_date,
        report_hour,
        cost_eur,
        sum(cost_eur) over (
            partition by transfer_source, account_id, campaign_id, report_date
            order by report_hour
        ) as cumulative_cost_eur
    from hourly
),
daily_bounds as (
    select
        transfer_source,
        account_id,
        campaign_id,
        report_date,
        max(cumulative_cost_eur) as total_cost_eur,
        min(case when report_hour >= 7 and cost_eur > 0.01 then report_hour end) as first_active_hour,
        max(case when report_hour >= 7 and cost_eur > 0.01 then report_hour end) as last_active_hour
    from hourly_rollup
    group by 1, 2, 3, 4
)

select
    a.client_id,
    d.account_id,
    a.account_name,
    d.campaign_id,
    c.campaign_name,
    d.report_date,
    d.total_cost_eur,
    d.first_active_hour,
    d.last_active_hour,
    case
        when d.total_cost_eur >= t.min_cost_eur
         and d.last_active_hour is not null
         and d.last_active_hour <= 23 - cast(t.zero_spend_hours as int64)
            then true
        else false
    end as budget_exhausted_flag
from daily_bounds d
left join campaigns c
    on d.transfer_source = c.transfer_source
   and d.account_id = c.account_id
   and d.campaign_id = c.campaign_id
left join accounts a
    on d.account_id = cast(a.account_id as string)
cross join thresholds t

