-- Every mart left joins this model on (account_id, report_date). A duplicate pair
-- would fan out ten marts at once, so guard the grain explicitly -- especially now
-- that the model unions an ECB-resolved set with a seed-resolved fallback set.
select
    account_id,
    report_date,
    count(*) as row_count
from {{ ref('stg_account_fx_rates_daily') }}
group by 1, 2
having count(*) > 1
