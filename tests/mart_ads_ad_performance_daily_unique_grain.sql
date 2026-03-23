select
    client_id,
    account_id,
    campaign_id,
    ad_group_id,
    ad_id,
    report_date,
    count(*) as row_count
from {{ ref('mart_ads_ad_performance_daily') }}
group by 1, 2, 3, 4, 5, 6
having count(*) > 1
