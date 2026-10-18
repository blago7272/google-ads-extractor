/*
  User-facing data freshness per active account (reporting app badge, Telegram
  /freshness and daily summary).

  A VIEW, so the lag is measured when it is read, in days, from the last raw date
  the current marts were built with. If a release fails, the lag keeps growing and
  the status degrades, instead of a stored "hours since" freezing at build time.

  Statuses, on the one freshness rule (lag = today in report_timezone - last raw date):
    ok           lag <= 1                 (data through yesterday)
    stale        1 < lag <= threshold     (behind, still in the marts)
    error        lag > threshold          (excluded from the marts)
    backfilling  no raw data at all
*/

{{ config(materialized='view') }}

{% set report_tz = var('report_timezone') %}
{% set max_lag = freshness_max_allowed_lag_days() %}

with snapshot as (
    select
        *,
        date_diff(current_date('{{ report_tz }}'), last_raw_date, day) as current_lag_days
    from {{ ref('mart_account_freshness_snapshot') }}
)

select
    client_id,
    account_id,
    account_name,
    last_raw_date,
    current_lag_days                       as lag_days,
    case
        when last_raw_date is null then 'backfilling'
        when current_lag_days <= 1 then 'ok'
        when current_lag_days <= {{ max_lag }} then 'stale'
        else 'error'
    end                                    as freshness_status,
    freshness_status = 'stale'             as excluded_from_marts,
    evaluated_at,
    current_timestamp()                    as checked_at
from snapshot
