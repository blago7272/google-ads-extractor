{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        cast(campaign_id as string) as campaign_id,
        cast(ad_group_id as string) as ad_group_id,
        segments_date as report_date,
        cast(segments_hour as int64) as report_hour,
        sum(metrics_cost_micros) / 1000000.0 as cost_eur,
        sum(metrics_clicks) as clicks,
        sum(metrics_impressions) as impressions,
        sum(metrics_conversions) as conversions,
        sum(metrics_conversions_value) as conversion_value
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_HourlyAdGroupStats_*`
    group by 1, 2, 3, 4, 5, 6
)

select * from src

