{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

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

