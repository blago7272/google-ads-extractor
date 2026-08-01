{#
    Latest ad group dimension state per account and transfer source.

    Same shape as stg_ad_dimension_latest: the raw `p_ads_AdGroup_*` transfer tables
    are DAILY FULL SNAPSHOTS (~211M rows / ~43 GB for a far smaller number of distinct
    ad groups), so reading the full wildcard on every run rescans all history just to
    pick the newest row per ad group.

    Accumulating dimension: merge only the recent snapshot partitions onto the stored
    state. Ad groups that stop appearing keep their last-known attributes, so historical
    stats rows in the downstream marts stay enriched.

    A full refresh (`dbt run --full-refresh`) rebuilds from the complete history.
#}

{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['transfer_source', 'account_id', 'campaign_id', 'ad_group_id'],
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
        ad_group_name,
        ad_group_status,
        ad_group_type,
        _PARTITIONTIME as loaded_at
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_AdGroup_*`
    {% if is_incremental() %}
    -- Constant expression, so BigQuery prunes to the lookback partitions only.
    where _PARTITIONDATE >= date_sub(current_date(), interval {{ lookback_days }} day)
    {% endif %}
),
ranked as (
    select
        *,
        row_number() over (
            partition by transfer_source, account_id, campaign_id, ad_group_id
            order by loaded_at desc
        ) as rn
    from src
)

select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    ad_group_name,
    ad_group_status,
    ad_group_type
from ranked
where rn = 1

