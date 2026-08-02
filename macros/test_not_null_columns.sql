{#
    Assert that several columns are all non-null, in a SINGLE query.

    dbt runs one query per test, so N per-column `not_null` tests on a view
    re-execute that view N times. On the fact staging views that was the second
    largest cost in the pipeline -- five `not_null` tests on
    stg_ad_group_stats_hourly scanned 4.44 GB each, 22.2 GB to check one table.

    Coverage is identical to the per-column tests: a row violating any column
    still fails the build. The failing rows carry a `null_columns` label naming
    which columns were null, so the per-column diagnostics are not lost.

    Usage:
        tests:
          - not_null_columns:
              arguments:
                columns: [account_id, campaign_id, report_date]
#}

{% test not_null_columns(model, columns) %}

select
    {%- for column_name in columns %}
    {{ column_name }},
    {%- endfor %}
    trim(concat(
        {%- for column_name in columns %}
        case when {{ column_name }} is null then '{{ column_name }} ' else '' end{{ ',' if not loop.last }}
        {%- endfor %}
    )) as null_columns
from {{ model }}
where
    {%- for column_name in columns %}
    {{ column_name }} is null{{ ' or' if not loop.last }}
    {%- endfor %}

{% endtest %}
