select
    client_id,
    account_id,
    campaign_id,
    ad_group_id,
    keyword_id,
    report_date,
    count(*) as row_count
from {{ ref('mart_ads_keyword_daily') }}
group by 1, 2, 3, 4, 5, 6
having count(*) > 1
