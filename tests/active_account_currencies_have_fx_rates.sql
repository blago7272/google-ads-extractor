with active_currencies as (
    select distinct currency
    from {{ ref('cfg_accounts') }}
    where is_active
),
fx_currencies as (
    select distinct currency
    from {{ ref('cfg_exchange_rates') }}
)

select a.currency
from active_currencies a
left join fx_currencies f
    on a.currency = f.currency
where f.currency is null
