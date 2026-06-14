{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}
{% set max_lag = env_var('RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS', '3') | int %}

with accounts as (
    select
        cast(account_id as string) as account_id,
        client_id,
        account_name
    from {{ ref('cfg_accounts') }}
    where is_active = true
),
raw_last_dates as (
    select
        cast(customer_id as string) as account_id,
        max(segments_date)          as last_raw_date
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_AccountStats_*`
    group by 1
),
classified as (
    select
        a.account_id,
        a.client_id,
        a.account_name,
        r.last_raw_date,
        date_diff(current_date('{{ var("report_timezone", "Europe/Sofia") }}'), r.last_raw_date, day) as days_lag,
        case
            when r.last_raw_date is null
                then 'stale'
            when date_diff(current_date('{{ var("report_timezone", "Europe/Sofia") }}'), r.last_raw_date, day) > {{ max_lag }}
                then 'stale'
            else 'healthy'
        end as freshness_status
    from accounts a
    left join raw_last_dates r using (account_id)
)

select
    account_id,
    client_id,
    account_name,
    last_raw_date,
    days_lag,
    freshness_status
from classified
