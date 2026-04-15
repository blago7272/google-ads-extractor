with active_currencies as (
    select distinct currency
    from {{ ref('cfg_accounts') }}
    where is_active
),
-- Covered by the CSV seed fallback
seed_currencies as (
    select distinct currency
    from {{ ref('cfg_exchange_rates') }}
),
-- Covered by the ECB daily rates table (primary source)
ecb_currencies as (
    select distinct currency
    from {{ source('reporting_cfg', 'ecb_exchange_rates_daily') }}
),
covered_currencies as (
    select currency from seed_currencies
    union distinct
    select currency from ecb_currencies
)

select a.currency
from active_currencies a
left join covered_currencies c
    on a.currency = c.currency
where c.currency is null
