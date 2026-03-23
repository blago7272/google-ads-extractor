select
    client_id,
    account_id,
    campaign_id,
    ad_group_id,
    keyword_id,
    search_term,
    report_date,
    count(*) as row_count
from {{ ref('mart_ads_search_terms') }}
group by 1, 2, 3, 4, 5, 6, 7
having count(*) > 1
