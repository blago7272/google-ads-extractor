with daily as (
    select * from {{ ref('mart_ads_overview_daily') }}
)

select
    client_id,
    account_id,
    account_name,
    currency,
    date_trunc(report_date, month) as report_month,
    sum(cost_original) as cost_original,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    sum(conversion_value_original) as conversion_value_original,
    sum(conversion_value_eur) as conversion_value_eur,
    safe_divide(sum(clicks), sum(impressions)) as ctr,
    safe_divide(sum(cost_original), sum(clicks)) as cpc_original,
    safe_divide(sum(cost_eur), sum(clicks)) as cpc_eur,
    safe_divide(sum(cost_original), sum(conversions)) as cpa_original,
    safe_divide(sum(cost_eur), sum(conversions)) as cpa_eur,
    safe_divide(sum(conversion_value_eur), sum(cost_eur)) as roas
from daily
group by 1, 2, 3, 4, 5
