/*
  The freshness verdict every mart in this build was built with, one row per active
  account. `mart_data_freshness` (a view) reads it to work out the current lag at
  query time. It lives in the mart dataset so readers of the marts can query that
  view without access to the staging dataset.
*/

select
    client_id,
    account_id,
    account_name,
    last_raw_date,
    lag_days,
    freshness_status,
    report_date,
    evaluated_at,
    freshness_source
from {{ ref('stg_account_freshness') }}
