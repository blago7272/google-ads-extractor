{#
  The account freshness rule's settings, shared with orchestration/raw_freshness.py:
  stale when (today in report_timezone - last raw date) > this threshold.
  Defined once, as the raw_freshness_max_allowed_lag_days var in dbt_project.yml;
  RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS overrides it, for the orchestrator too.
#}
{% macro freshness_max_allowed_lag_days() -%}
    {{ return(env_var('RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS', var('raw_freshness_max_allowed_lag_days') | string) | int) }}
{%- endmacro %}


{#
  Which ops_account_freshness run stg_account_freshness should read, as a timestamp
  string, or none to apply the rule in SQL instead.

  - Orchestrated release: ACCOUNT_FRESHNESS_RUN_TS names the run it just recorded.
    If those rows are missing (the write failed), apply the rule.
  - Manual dbt run: use the latest run only if it was evaluated for today's report
    date; older verdicts would be a day out of date, so apply the rule.
#}
{% macro account_freshness_run_to_read() -%}
    {%- if not execute -%}
        {{ return(none) }}
    {%- endif -%}

    {%- set table = source('reporting_cfg', 'ops_account_freshness') -%}
    {%- if adapter.get_relation(database=table.database, schema=table.schema, identifier=table.identifier) is none -%}
        {{ log("stg_account_freshness: " ~ table ~ " does not exist; applying the freshness rule in SQL", info=true) }}
        {{ return(none) }}
    {%- endif -%}

    {%- set requested = env_var('ACCOUNT_FRESHNESS_RUN_TS', '') | trim -%}
    {%- if requested -%}
        {%- if not modules.re.fullmatch('[0-9T:.+ Z-]+', requested) -%}
            {{ exceptions.raise_compiler_error("ACCOUNT_FRESHNESS_RUN_TS is not a timestamp: " ~ requested) }}
        {%- endif -%}
        {%- set found = run_query("select count(*) from " ~ table ~ " where run_timestamp = timestamp('" ~ requested ~ "')") -%}
        {%- if found.columns[0].values()[0] > 0 -%}
            {{ return(requested) }}
        {%- endif -%}
        {{ log("stg_account_freshness: no rows for run " ~ requested ~ "; applying the freshness rule in SQL", info=true) }}
        {{ return(none) }}
    {%- endif -%}

    {%- set latest = run_query(
        "select format_timestamp('%Y-%m-%dT%H:%M:%E6S+00:00', max(run_timestamp), 'UTC') from " ~ table
        ~ " where run_timestamp >= timestamp_sub(current_timestamp(), interval 2 day)"
        ~ " and report_date = current_date('" ~ var('report_timezone') ~ "')"
    ) -%}
    {%- set latest_ts = latest.columns[0].values()[0] -%}
    {%- if latest_ts -%}
        {{ log("stg_account_freshness: using today's recorded run " ~ latest_ts, info=true) }}
        {{ return(latest_ts) }}
    {%- endif -%}
    {{ log("stg_account_freshness: no run recorded for today; applying the freshness rule in SQL", info=true) }}
    {{ return(none) }}
{%- endmacro %}
