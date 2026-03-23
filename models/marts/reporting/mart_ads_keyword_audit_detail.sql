with perf as (
    select * from {{ ref('stg_keyword_performance_daily') }}
),
keywords as (
    select * from {{ ref('stg_keyword_dimension_latest') }}
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
thresholds as (
    select
        max(case when threshold_key = 'min_keyword_spend_eur' then threshold_value end) as min_keyword_spend_eur,
        max(case when threshold_key = 'min_keyword_clicks' then threshold_value end) as min_keyword_clicks,
        max(case when threshold_key = 'low_quality_score' then threshold_value end) as low_quality_score
    from {{ ref('cfg_thresholds') }}
    where client_id = 'default'
),
rolled as (
    select
        p.transfer_source,
        p.account_id,
        p.campaign_id,
        p.ad_group_id,
        p.keyword_id,
        sum(p.cost_eur) as cost_eur,
        sum(p.clicks) as clicks,
        sum(p.impressions) as impressions,
        sum(p.conversions) as conversions,
        sum(p.conversion_value) as conversion_value
    from perf p
    group by 1, 2, 3, 4, 5
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
    k.keyword_text,
    k.match_type,
    k.keyword_status,
    k.quality_score,
    k.first_page_cpc_eur,
    k.top_of_page_cpc_eur,
    r.cost_eur,
    r.clicks,
    r.impressions,
    r.conversions,
    r.conversion_value,
    safe_divide(r.cost_eur, r.conversions) as cpa,
    case
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 and coalesce(k.quality_score, 10) < t.low_quality_score then 'low_qs'
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 and r.clicks >= t.min_keyword_clicks then 'intent_or_offer'
        when r.cost_eur >= t.min_keyword_spend_eur and r.conversions = 0 then 'low_volume'
        when r.conversions > 0 and coalesce(k.quality_score, 10) < t.low_quality_score then 'scale_but_fix_qs'
        else 'ok'
    end as audit_reason
from rolled r
left join keywords k
    on r.transfer_source = k.transfer_source
   and r.account_id = k.account_id
   and r.campaign_id = k.campaign_id
   and r.ad_group_id = k.ad_group_id
   and r.keyword_id = k.keyword_id
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
cross join thresholds t
