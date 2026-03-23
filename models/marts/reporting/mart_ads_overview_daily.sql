with account_stats as (
    select * from {{ ref('stg_account_stats_daily') }}
),
accounts as (
    select * from {{ ref('cfg_accounts') }}
)

select
    a.client_id,
    s.account_id,
    a.account_name,
    a.timezone,
    a.currency,
    s.report_date,
    s.cost_eur,
    s.clicks,
    s.impressions,
    s.conversions,
    s.conversion_value,
    s.ctr,
    s.cpc,
    s.cpa,
    s.roas
from account_stats s
left join accounts a
    on s.account_id = cast(a.account_id as string)

