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
fx_daily as (
    select * from {{ ref('stg_account_fx_rates_daily') }}
),
rolled as (
    select
        transfer_source,
        account_id,
        campaign_id,
        ad_group_id,
        keyword_id,
        search_term,
        case
            when count(distinct search_term_status) = 1 then min(search_term_status)
            else 'MULTIPLE'
        end as search_term_status,
        case
            when count(distinct search_term_match_type) = 1 then min(search_term_match_type)
            else 'MULTIPLE'
        end as search_term_match_type,
        report_date,
        sum(cost_original) as cost_original,
        sum(clicks) as clicks,
        sum(impressions) as impressions,
        sum(conversions) as conversions,
        sum(conversion_value_original) as conversion_value_original
    from search_terms
    group by 1, 2, 3, 4, 5, 6, 9
),
base as (
    select
        a.client_id,
        r.account_id,
        a.account_name,
        a.currency,
        r.campaign_id,
        c.campaign_name,
        r.ad_group_id,
        g.ad_group_name,
        r.keyword_id,
        r.search_term,
        r.search_term_status,
        r.search_term_match_type,
        r.report_date,
        r.cost_original,
        safe_multiply(r.cost_original, fxd.eur_exchange_rate) as cost_eur,
        r.clicks,
        r.impressions,
        r.conversions,
        r.conversion_value_original,
        safe_multiply(r.conversion_value_original, fxd.eur_exchange_rate) as conversion_value_eur,
        safe_divide(r.clicks, r.impressions) as ctr,
        safe_divide(r.cost_original, r.clicks) as cpc_original,
        safe_divide(safe_multiply(r.cost_original, fxd.eur_exchange_rate), r.clicks) as cpc_eur,
        safe_divide(r.cost_original, r.conversions) as cpa_original,
        safe_divide(safe_multiply(r.cost_original, fxd.eur_exchange_rate), r.conversions) as cpa_eur,
        safe_divide(r.conversion_value_original, r.cost_original) as roas
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
    left join fx_daily fxd
        on r.account_id = fxd.account_id
       and r.report_date = fxd.report_date
)

select
    client_id,
    account_id,
    account_name,
    currency,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    keyword_id,
    search_term,
    search_term_status,
    search_term_match_type,
    report_date,
    cost_original,
    cost_eur,
    clicks,
    impressions,
    conversions,
    conversion_value_original,
    conversion_value_eur,
    ctr,
    cpc_original,
    cpc_eur,
    cpa_original,
    cpa_eur,
    roas
from base
