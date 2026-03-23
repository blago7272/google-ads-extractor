{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        cast(campaign_id as string) as campaign_id,
        cast(ad_group_id as string) as ad_group_id,
        cast(ad_group_criterion_criterion_id as string) as keyword_id,
        ad_group_criterion_keyword_text as keyword_text,
        ad_group_criterion_keyword_match_type as match_type,
        ad_group_criterion_negative as is_negative,
        ad_group_criterion_status as keyword_status,
        ad_group_criterion_quality_info_quality_score as quality_score,
        ad_group_criterion_quality_info_creative_quality_score as creative_quality_score,
        ad_group_criterion_quality_info_post_click_quality_score as post_click_quality_score,
        ad_group_criterion_quality_info_search_predicted_ctr as predicted_ctr_score,
        ad_group_criterion_position_estimates_first_page_cpc_micros / 1000000.0 as first_page_cpc_original,
        ad_group_criterion_position_estimates_top_of_page_cpc_micros / 1000000.0 as top_of_page_cpc_original,
        _PARTITIONTIME as loaded_at
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_Keyword_*`
),
ranked as (
    select
        *,
        row_number() over (
            partition by transfer_source, account_id, campaign_id, ad_group_id, keyword_id
            order by loaded_at desc
        ) as rn
    from src
)

select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    keyword_id,
    keyword_text,
    match_type,
    is_negative,
    keyword_status,
    quality_score,
    creative_quality_score,
    post_click_quality_score,
    predicted_ctr_score,
    first_page_cpc_original,
    top_of_page_cpc_original
from ranked
where rn = 1
