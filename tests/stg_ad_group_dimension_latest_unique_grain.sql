-- stg_ad_group_dimension_latest is merged incrementally on this key. A NULL in any key
-- column makes the MERGE predicate fail to match, which silently accumulates
-- duplicate rows and fans out every mart that joins ad group names. Guard the grain.
select
    transfer_source,
    account_id,
    campaign_id,
    ad_group_id,
    count(*) as row_count
from {{ ref('stg_ad_group_dimension_latest') }}
group by 1, 2, 3, 4
having count(*) > 1
