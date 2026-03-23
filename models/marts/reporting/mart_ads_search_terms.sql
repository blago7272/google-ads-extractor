with search_terms as (
    select * from {{ ref('stg_search_query_stats_daily') }}
),
campaigns as (
    select * from {{ ref('stg_campaign_dimension_latest') }}
),
ad_groups as (
    select * from {{ ref('stg_ad_group_dimension_latest') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
),
rolled as (
    select
        transfer_source,
        account_id,
        campaign_id,
        ad_group_id,
        keyword_id,
        search_term,
        search_term_status,
        search_term_match_type,
        sum(cost_eur) as cost_eur,
        sum(clicks) as clicks,
        sum(impressions) as impressions,
        sum(conversions) as conversions,
        sum(conversion_value) as conversion_value
    from search_terms
    group by 1, 2, 3, 4, 5, 6, 7, 8
)

select
    a.client_id,
    r.account_id,
    a.account_name,
    r.campaign_id,
    c.campaign_name,
    r.ad_group_id,
    g.ad_group_name,
    r.keyword_id,
    r.search_term,
    r.search_term_status,
    r.search_term_match_type,
    r.cost_eur,
    r.clicks,
    r.impressions,
    r.conversions,
    r.conversion_value
from rolled r
left join campaigns c
    on r.transfer_source = c.transfer_source
   and r.account_id = c.account_id
   and r.campaign_id = c.campaign_id
left join ad_groups g
    on r.transfer_source = g.transfer_source
   and r.account_id = g.account_id
   and r.campaign_id = g.campaign_id
   and r.ad_group_id = g.ad_group_id
join accounts a
    on r.account_id = cast(a.account_id as string)
   and a.is_active = true
