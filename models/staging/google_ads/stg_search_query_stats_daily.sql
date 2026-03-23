{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        cast(campaign_id as string) as campaign_id,
        cast(ad_group_id as string) as ad_group_id,
        cast(segments_keyword_ad_group_criterion as string) as keyword_id,
        search_term_view_search_term as search_term,
        search_term_view_status as search_term_status,
        segments_search_term_match_type as search_term_match_type,
        segments_date as report_date,
        sum(metrics_cost_micros) / 1000000.0 as cost_eur,
        sum(metrics_clicks) as clicks,
        sum(metrics_impressions) as impressions,
        sum(metrics_conversions) as conversions,
        sum(metrics_conversions_value) as conversion_value
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_SearchQueryStats_*`
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
)

select * from src

