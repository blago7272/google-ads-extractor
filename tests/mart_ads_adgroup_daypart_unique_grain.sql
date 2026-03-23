select
    client_id,
    account_id,
    campaign_id,
    ad_group_id,
    report_date,
    daypart,
    count(*) as row_count
from {{ ref('mart_ads_adgroup_daypart') }}
group by 1, 2, 3, 4, 5, 6
having count(*) > 1
