-- stg_ad_dimension_latest is merged incrementally on this key. A NULL in any key
-- column makes the MERGE predicate fail to match, which silently accumulates
-- duplicate rows and fans out the ad performance mart. Guard the grain explicitly.
select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    ad_id,
    count(*) as row_count
from {{ ref('stg_ad_dimension_latest') }}
group by 1, 2, 3, 4, 5
having count(*) > 1
