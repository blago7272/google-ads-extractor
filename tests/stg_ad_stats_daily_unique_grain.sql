select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    ad_id,
    report_date,
    count(*) as row_count
from {{ ref('stg_ad_stats_daily') }}
group by 1, 2, 3, 4, 5, 6
having count(*) > 1
