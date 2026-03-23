select
    client_id,
    account_id,
    report_date,
    report_hour,
    count(*) as row_count
from {{ ref('mart_ads_hourly_performance_daily') }}
group by 1, 2, 3, 4
having count(*) > 1
