{% set raw_project = var('raw_project_id', target.project) %}
{% set raw_dataset = var('raw_dataset', 'gads_raw') %}

with src as (
    select
        _TABLE_SUFFIX as transfer_source,
        cast(customer_id as string) as account_id,
        cast(campaign_id as string) as campaign_id,
        campaign_name,
        campaign_status,
        campaign_serving_status,
        campaign_advertising_channel_type as campaign_channel_type,
        campaign_advertising_channel_sub_type as campaign_channel_sub_type,
        campaign_bidding_strategy_type as bidding_strategy_type,
        campaign_budget_amount_micros / 1000000.0 as campaign_budget_original,
        _PARTITIONTIME as loaded_at
    from `{{ raw_project }}.{{ raw_dataset }}.p_ads_Campaign_*`
),
ranked as (
    select
        *,
        row_number() over (
            partition by transfer_source, account_id, campaign_id
            order by loaded_at desc
        ) as rn
    from src
)

select
    transfer_source,
    account_id,
    campaign_id,
    campaign_name,
    campaign_status,
    campaign_serving_status,
    campaign_channel_type,
    campaign_channel_sub_type,
    bidding_strategy_type,
    campaign_budget_original
from ranked
where rn = 1
