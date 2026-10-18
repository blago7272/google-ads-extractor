/*
  Per-account freshness verdict for this build: `healthy` accounts are built into
  every mart, `stale` ones are excluded (the marts join on freshness_status).

  The rule (one rule, see orchestration/raw_freshness.py):
      lag_days = today in report_timezone - last raw date
      stale    = lag_days > raw_freshness_max_allowed_lag_days, or no raw data

  The release orchestrator applies it before dbt runs and records the result in
  gads_reporting_cfg.ops_account_freshness; this model reads that run's rows, so
  the release log, the skipped-accounts alert and the marts share one verdict.
  When there is no usable recorded run (a manual dbt run on a day the release has
  not run, or a failed write) the same rule is applied here instead.

  A table, not a view: the verdict must not change while the marts build.
*/

{{ config(materialized='table') }}

{% set report_tz = var('report_timezone') %}
{% set max_lag = freshness_max_allowed_lag_days() %}
{% set recorded_run = account_freshness_run_to_read() %}

{% if recorded_run %}

select
    account_id,
    client_id,
    account_name,
    last_raw_date,
    lag_days,
    status                      as freshness_status,
    report_date,
    run_timestamp               as evaluated_at,
    'ops_account_freshness'     as freshness_source
from {{ source('reporting_cfg', 'ops_account_freshness') }}
where run_timestamp = timestamp('{{ recorded_run }}')

{% else %}

{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

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
        date_diff(current_date('{{ report_tz }}'), r.last_raw_date, day) as lag_days,
        current_date('{{ report_tz }}')                                  as report_date
    from accounts a
    left join raw_last_dates r using (account_id)
)

select
    account_id,
    client_id,
    account_name,
    last_raw_date,
    lag_days,
    case
        when lag_days is null or lag_days > {{ max_lag }} then 'stale'
        else 'healthy'
    end                         as freshness_status,
    report_date,
    current_timestamp()         as evaluated_at,
    'computed_in_dbt'           as freshness_source
from classified

{% endif %}
