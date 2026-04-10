with account_latest as (
    select
        account_id,
        max(report_date) as last_data_date
    from {{ ref('mart_ads_overview_daily') }}
    group by 1
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
freshness as (
    select
        a.client_id,
        cast(a.account_id as string) as account_id,
        a.account_name,
        l.last_data_date as last_data_date,
        case
            when l.last_data_date is null then null
            else timestamp_diff(current_timestamp(), timestamp(l.last_data_date), hour)
        end as hours_since_last_data,
        case
            when l.last_data_date is null then 'backfilling'
            when timestamp_diff(current_timestamp(), timestamp(l.last_data_date), hour) > 72 then 'error'
            when timestamp_diff(current_timestamp(), timestamp(l.last_data_date), hour) > 36 then 'stale'
            else 'ok'
        end as freshness_status,
        current_timestamp() as checked_at
    from accounts a
    left join account_latest l
        on cast(a.account_id as string) = l.account_id
    where a.is_active = true
)

select
    client_id,
    account_id,
    account_name,
    last_data_date,
    hours_since_last_data,
    freshness_status,
    checked_at
from freshness
