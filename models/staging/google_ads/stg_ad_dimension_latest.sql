{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        cast(campaign_id as string) as campaign_id,
        cast(ad_group_id as string) as ad_group_id,
        cast(ad_group_ad_ad_id as string) as ad_id,
        ad_group_ad_ad_type as ad_type,
        ad_group_ad_status as ad_status,
        ad_group_ad_policy_summary_approval_status as approval_status,
        ad_group_ad_ad_strength as ad_strength,
        ad_group_ad_ad_name as ad_name,
        coalesce(
            nullif(ad_group_ad_ad_name, ''),
            nullif(ad_group_ad_ad_text_ad_headline, ''),
            nullif(ad_group_ad_ad_expanded_text_ad_headline_part1, ''),
            regexp_extract(ad_group_ad_ad_responsive_search_ad_headlines, r'"text":"([^"]+)"'),
            cast(ad_group_ad_ad_id as string)
        ) as ad_label,
        coalesce(
            nullif(ad_group_ad_ad_text_ad_headline, ''),
            nullif(ad_group_ad_ad_expanded_text_ad_headline_part1, ''),
            regexp_extract(ad_group_ad_ad_responsive_search_ad_headlines, r'"text":"([^"]+)"')
        ) as headline_primary,
        coalesce(
            nullif(ad_group_ad_ad_text_ad_description1, ''),
            nullif(ad_group_ad_ad_expanded_text_ad_description, ''),
            regexp_extract(ad_group_ad_ad_responsive_search_ad_descriptions, r'"text":"([^"]+)"')
        ) as description_primary,
        regexp_extract(ad_group_ad_ad_final_urls, r'^\["([^"]+)') as landing_page_url,
        ad_group_ad_ad_final_urls as final_urls,
        _PARTITIONTIME as loaded_at
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_Ad_*`
),
ranked as (
    select
        *,
        row_number() over (
            partition by transfer_source, account_id, campaign_id, ad_group_id, ad_id
            order by loaded_at desc
        ) as rn
    from src
)

select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    ad_id,
    ad_type,
    ad_status,
    approval_status,
    ad_strength,
    ad_name,
    ad_label,
    headline_primary,
    description_primary,
    landing_page_url,
    final_urls
from ranked
where rn = 1
