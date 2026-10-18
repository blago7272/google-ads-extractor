select
    client_id,
    account_id,
    account_name,
    last_raw_date,
    lag_days                  as days_lag,
    freshness_status,
    'lag_exceeds_threshold'   as exclusion_reason,
    evaluated_at
from {{ ref('stg_account_freshness') }}
where freshness_status = 'stale'
