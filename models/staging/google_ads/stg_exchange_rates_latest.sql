with ranked as (
    select
        currency,
        eur_exchange_rate,
        row_number() over (
            partition by currency
            order by valid_from desc
        ) as rn
    from {{ ref('cfg_exchange_rates') }}
)

select
    currency,
    eur_exchange_rate
from ranked
where rn = 1
