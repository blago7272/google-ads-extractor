{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        segments_date as report_date,
        sum(metrics_cost_micros) / 1000000.0 as cost_original,
        sum(metrics_clicks) as clicks,
        sum(metrics_impressions) as impressions,
        sum(metrics_conversions) as conversions,
        sum(metrics_conversions_value) as conversion_value_original
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_AccountStats_*`
    group by 1, 2, 3
)

select
    transfer_source,
    account_id,
    report_date,
    cost_original,
    clicks,
    impressions,
    conversions,
    conversion_value_original,
    safe_divide(clicks, impressions) as ctr,
    safe_divide(cost_original, clicks) as cpc_original,
    safe_divide(cost_original, conversions) as cpa_original,
    safe_divide(conversion_value_original, cost_original) as roas
from src
