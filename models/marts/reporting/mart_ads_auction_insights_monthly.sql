select
    client_id,
    account_id,
    report_month,
    competitor_domain,
    impression_share,
    overlap_rate,
    position_above_rate,
    outranking_share
from {{ ref('stg_auction_insights') }}

