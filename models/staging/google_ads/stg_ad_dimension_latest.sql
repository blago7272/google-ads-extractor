{#
    Latest ad dimension state per account and transfer source.

    The raw `p_ads_Ad_*` transfer tables are DAILY FULL SNAPSHOTS: every partition
    repeats every ad that existed on that day. Reading the whole wildcard on every run
    therefore rescans the entire snapshot history just to pick the newest row per ad —
    ~164 GB per execution, growing by one full snapshot every day.

    This model is an accumulating dimension instead: it merges only the most recent
    snapshot partitions onto the previously stored state. Ads that stop appearing in
    recent snapshots (paused/removed) keep their last-known attributes, so historical
    stats rows in the downstream marts stay enriched.

    A full refresh (`dbt run --full-refresh`) rebuilds from the complete history.
#}

{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['transfer_source', 'account_id', 'campaign_id', 'ad_group_id', 'ad_id'],
        cluster_by=['account_id', 'campaign_id'],
        on_schema_change='sync_all_columns',
    )
}}

{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}
{% set lookback_days = var('dimension_snapshot_lookback_days', 7) | int %}

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
    {% if is_incremental() %}
    -- Constant expression, so BigQuery prunes to the lookback partitions only.
    where _PARTITIONDATE >= date_sub(current_date(), interval {{ lookback_days }} day)
    {% endif %}
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
