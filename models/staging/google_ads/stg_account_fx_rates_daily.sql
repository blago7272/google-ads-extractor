/*
  Daily account-level EUR exchange rates.

  Resolves exchange rates from two sources in priority order:
    1. ecb_exchange_rates_daily (BigQuery table, updated daily)
    2. cfg_exchange_rates (CSV seed, fallback for any currency not in the ECB table)

  For weekends / ECB holidays where no rate is published, the most recent
  prior business-day rate is carried forward.
*/

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

-- Primary source: ECB daily rates table
ecb_rates as (
    select
        currency,
        report_date,
        eur_exchange_rate
    from {{ source('reporting_cfg', 'ecb_exchange_rates_daily') }}
),

-- Fallback source: CSV seed (for currencies not yet in the ECB table)
seed_rates as (
    select * from {{ ref('cfg_exchange_rates') }}
),

-- Join report dates with ECB rates, carrying forward for weekends/holidays
ecb_joined as (
    select
        d.account_id,
        a.currency,
        d.report_date,
        e.eur_exchange_rate,
        row_number() over (
            partition by d.account_id, d.report_date
            order by e.report_date desc
        ) as rn
    from report_dates d
    join accounts a
        on d.account_id = a.account_id
    left join ecb_rates e
        on a.currency = e.currency
       and e.report_date <= d.report_date
       and e.report_date >= date_sub(d.report_date, interval 7 day)
),
ecb_resolved as (
    select account_id, currency, report_date, eur_exchange_rate
    from ecb_joined
    where rn = 1
),

-- Fallback: use seed rates for anything ECB didn't cover
seed_joined as (
    select
        d.account_id,
        a.currency,
        d.report_date,
        s.eur_exchange_rate,
        row_number() over (
            partition by d.account_id, d.report_date
            order by s.valid_from desc
        ) as rn
    from report_dates d
    join accounts a
        on d.account_id = a.account_id
    left join seed_rates s
        on a.currency = s.currency
       and s.valid_from <= d.report_date
    where not exists (
        select 1 from ecb_resolved er
        where er.account_id = d.account_id
          and er.report_date = d.report_date
          and er.eur_exchange_rate is not null
    )
),
seed_resolved as (
    select account_id, currency, report_date, eur_exchange_rate
    from seed_joined
    where rn = 1
)

select account_id, currency, report_date, eur_exchange_rate
from ecb_resolved
where eur_exchange_rate is not null

union all

select account_id, currency, report_date, eur_exchange_rate
from seed_resolved
where eur_exchange_rate is not null
