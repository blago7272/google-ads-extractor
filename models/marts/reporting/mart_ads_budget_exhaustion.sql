with hourly as (
    select * from {{ ref('stg_campaign_stats_hourly') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
fx_daily as (
    select * from {{ ref('stg_account_fx_rates_daily') }}
),
thresholds as (
    select
        max(case when threshold_key = 'budget_exhausted_zero_spend_hours' then threshold_value end) as zero_spend_hours,
        max(case when threshold_key = 'budget_exhausted_min_cost_eur' then threshold_value end) as min_cost_eur
    from {{ ref('cfg_thresholds') }}
    where client_id = 'default'
),
hourly_enriched as (
    select
        h.transfer_source,
        a.client_id,
        h.account_id,
        a.account_name,
        a.currency,
        h.campaign_id,
        h.report_date,
        h.report_hour,
        h.cost_original,
        safe_multiply(h.cost_original, fxd.eur_exchange_rate) as cost_eur
    from hourly h
    join accounts a
        on h.account_id = cast(a.account_id as string)
       and a.is_active = true
    left join fx_daily fxd
        on h.account_id = fxd.account_id
       and h.report_date = fxd.report_date
),
hourly_rollup as (
    select
        transfer_source,
        client_id,
        account_id,
        account_name,
        currency,
        campaign_id,
        report_date,
        report_hour,
        cost_original,
        cost_eur,
        sum(cost_eur) over (
            partition by transfer_source, account_id, campaign_id, report_date
            order by report_hour
        ) as cumulative_cost_eur
    from hourly_enriched
),
daily_bounds as (
    select
        transfer_source,
        client_id,
        account_id,
        account_name,
        currency,
        campaign_id,
        report_date,
        sum(cost_original) as total_cost_original,
        max(cumulative_cost_eur) as total_cost_eur,
        min(case when report_hour >= 7 and cost_eur > 0.01 then report_hour end) as first_active_hour,
        max(case when report_hour >= 7 and cost_eur > 0.01 then report_hour end) as last_active_hour
    from hourly_rollup
    group by 1, 2, 3, 4, 5, 6, 7
)

select
    d.client_id,
    d.account_id,
    d.account_name,
    d.currency,
    d.campaign_id,
    c.campaign_name,
    d.report_date,
    d.total_cost_original,
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
cross join thresholds t
