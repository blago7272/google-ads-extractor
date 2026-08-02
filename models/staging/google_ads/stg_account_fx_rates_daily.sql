/*
  Daily account-level EUR exchange rates.

  Resolves exchange rates from two sources in priority order:
    1. ecb_exchange_rates_daily (BigQuery table, updated daily)
    2. cfg_exchange_rates (CSV seed, fallback for any currency not in the ECB table)

  For weekends / ECB holidays where no rate is published, the most recent
  prior business-day rate is carried forward.

  MATERIALIZED AS A TABLE, not a view. Ten marts join to this model for currency
  conversion, and as a view every one of them inlined the whole definition. That
  made this the single largest cost in the pipeline -- 237 GB of a 339 GB build
  (70%), for an output of ~1 MB. As a table each consumer does a trivial lookup.

  The (account_id, report_date) pairs come from a DENSE DATE SPINE rather than a
  `union distinct` across all nine fact staging views. The lookup only needs the
  pairs to exist; the spine is a strict superset, so over-covering costs a few
  thousand unused rows while the old union cost a full scan of every fact table.
  Under-covering would be the dangerous direction -- it would null out cost_eur --
  which is why the spine deliberately starts well before any real data and runs a
  day past today. `stg_account_fx_rates_daily_covers_reported_dates` guards it.
*/

{{ config(materialized='table') }}

{% set spine_start = var('fx_spine_start_date', '2019-01-01') %}
{% set report_tz = var('report_timezone', 'Europe/Sofia') %}
{% set carry_forward_days = var('fx_carry_forward_days', 30) | int %}

with accounts as (
    select
        cast(account_id as string) as account_id,
        currency
    from {{ ref('cfg_accounts') }}
    where is_active = true
),

-- Dense spine: every active account x every plausible report date.
account_dates as (
    select
        a.account_id,
        a.currency,
        report_date
    from accounts a
    cross join unnest(generate_date_array(
        date('{{ spine_start }}'),
        date_add(current_date('{{ report_tz }}'), interval 1 day)
    )) as report_date
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

-- Join report dates with ECB rates, carrying forward for weekends/holidays.
-- The carry-forward window must outlast a real ECB feed outage, not just a long
-- weekend: the feed went dark for 13 days over 2026-05-26..06-07, which the
-- original 7-day window could not bridge, leaving null cost_eur for every
-- USD/GBP/RON/MXN account across those dates (the seed only covers BGN/EUR).
-- Widening only adds more-distant candidates, and rn=1 still picks the nearest
-- prior rate, so no already-resolved rate can change -- it can only fill gaps.
ecb_joined as (
    select
        d.account_id,
        d.currency,
        d.report_date,
        e.eur_exchange_rate,
        row_number() over (
            partition by d.account_id, d.report_date
            order by e.report_date desc
        ) as rn
    from account_dates d
    left join ecb_rates e
        on d.currency = e.currency
       and e.report_date <= d.report_date
       and e.report_date >= date_sub(d.report_date, interval {{ carry_forward_days }} day)
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
        d.currency,
        d.report_date,
        s.eur_exchange_rate,
        row_number() over (
            partition by d.account_id, d.report_date
            order by s.valid_from desc
        ) as rn
    from account_dates d
    left join seed_rates s
        on d.currency = s.currency
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
