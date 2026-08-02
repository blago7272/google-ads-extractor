-- stg_account_fx_rates_daily builds its (account_id, report_date) pairs from a dense
-- date spine rather than from the fact tables. The spine is a strict superset by
-- design, but if `fx_spine_start_date` ever drifts later than real reported data --
-- or the ECB feed goes dark for longer than `fx_carry_forward_days` -- the FX left
-- joins in the marts would silently produce null cost_eur instead of failing.
--
-- stg_account_stats_daily is the cheapest fact view (~0.3 GB) and carries a row for
-- every account/date with any activity, so it is the natural canary for coverage.
--
-- Dates earlier than the first rate that exists for the account's currency are
-- excluded: nothing can convert a date that predates every rate source. ECB history
-- starts 2020-01-02, so e.g. a stray 2020-01-01 row on a USD account is out of scope
-- rather than a failure.
with active_accounts as (
    select cast(account_id as string) as account_id, currency
    from {{ ref('cfg_accounts') }}
    where is_active = true
),
rate_starts as (
    select currency, min(report_date) as first_rate_date
    from {{ source('reporting_cfg', 'ecb_exchange_rates_daily') }}
    group by currency
    union all
    select currency, min(valid_from) as first_rate_date
    from {{ ref('cfg_exchange_rates') }}
    group by currency
),
earliest_rate as (
    select currency, min(first_rate_date) as first_rate_date
    from rate_starts
    group by currency
)
select
    s.account_id,
    a.currency,
    s.report_date
from {{ ref('stg_account_stats_daily') }} s
join active_accounts a
    on s.account_id = a.account_id
left join earliest_rate e
    on a.currency = e.currency
left join {{ ref('stg_account_fx_rates_daily') }} fx
    on s.account_id = fx.account_id
   and s.report_date = fx.report_date
where fx.account_id is null
  and s.report_date >= coalesce(e.first_rate_date, date '1900-01-01')
