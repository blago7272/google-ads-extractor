with report_dates as (
    select account_id, report_date from {{ ref('stg_account_stats_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_campaign_stats_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_campaign_stats_hourly') }}
    union distinct
    select account_id, report_date from {{ ref('stg_ad_group_stats_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_ad_group_stats_hourly') }}
    union distinct
    select account_id, report_date from {{ ref('stg_budget_stats_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_keyword_performance_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_search_query_stats_daily') }}
    union distinct
    select account_id, report_date from {{ ref('stg_ad_stats_daily') }}
),
accounts as (
    select
        cast(account_id as string) as account_id,
        currency
    from {{ ref('cfg_accounts') }}
    where is_active = true
),
fx_rates as (
    select * from {{ ref('cfg_exchange_rates') }}
),
ranked as (
    select
        d.account_id,
        a.currency,
        d.report_date,
        fx.eur_exchange_rate,
        row_number() over (
            partition by d.account_id, d.report_date
            order by fx.valid_from desc
        ) as rn
    from report_dates d
    join accounts a
        on d.account_id = a.account_id
    left join fx_rates fx
        on a.currency = fx.currency
       and fx.valid_from <= d.report_date
)

select
    account_id,
    currency,
    report_date,
    eur_exchange_rate
from ranked
where rn = 1
