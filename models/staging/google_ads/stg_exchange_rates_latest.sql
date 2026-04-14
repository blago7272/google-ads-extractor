/*
  Latest exchange rate per currency.

  Uses the ECB daily rates table as the primary source, with the CSV seed
  as a fallback for any currencies not covered by the ECB data.
*/

with ecb_latest as (
    select
        currency,
        eur_exchange_rate,
        row_number() over (
            partition by currency
            order by report_date desc
        ) as rn
    from {{ source('reporting_cfg', 'ecb_exchange_rates_daily') }}
),
seed_latest as (
    select
        currency,
        eur_exchange_rate,
        row_number() over (
            partition by currency
            order by valid_from desc
        ) as rn
    from {{ ref('cfg_exchange_rates') }}
),
ecb_resolved as (
    select currency, eur_exchange_rate
    from ecb_latest
    where rn = 1
),
seed_resolved as (
    select currency, eur_exchange_rate
    from seed_latest
    where rn = 1
      and currency not in (select currency from ecb_resolved)
)

select currency, eur_exchange_rate from ecb_resolved
union all
select currency, eur_exchange_rate from seed_resolved
