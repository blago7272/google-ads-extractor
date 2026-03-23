with daily as (
    select * from {{ ref('mart_ads_overview_daily') }}
)

select
    client_id,
    account_id,
    account_name,
    date_trunc(report_date, month) as report_month,
    sum(cost_eur) as cost_eur,
    sum(clicks) as clicks,
    sum(impressions) as impressions,
    sum(conversions) as conversions,
    sum(conversion_value) as conversion_value,
    safe_divide(sum(clicks), sum(impressions)) as ctr,
    safe_divide(sum(cost_eur), sum(clicks)) as cpc,
    safe_divide(sum(cost_eur), sum(conversions)) as cpa,
    safe_divide(sum(conversion_value), sum(cost_eur)) as roas
from daily
group by 1, 2, 3, 4

