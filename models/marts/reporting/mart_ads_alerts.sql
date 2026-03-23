with overview_daily as (
    select * from {{ ref('mart_ads_overview_daily') }}
),
keyword_audit as (
    select * from {{ ref('mart_ads_keyword_audit_detail') }}
),
budget_flags as (
    select * from {{ ref('mart_ads_budget_exhaustion') }}
),
thresholds as (
    select
        max(case when threshold_key = 'anomaly_drop_pct' then threshold_value end) as anomaly_drop_pct
    from {{ ref('cfg_thresholds') }}
    where client_id = 'default'
),
daily_with_prev as (
    select
        *,
        lag(conversions) over (partition by account_id order by report_date) as prev_day_conversions
    from overview_daily
),
conversion_drop_alerts as (
    select
        client_id,
        account_id,
        account_name,
        report_date,
        'conversion_drop' as alert_type,
        'high' as severity,
        concat(
            'Conversions dropped from ',
            cast(prev_day_conversions as string),
            ' to ',
            cast(conversions as string)
        ) as alert_message
    from daily_with_prev
    cross join thresholds
    where prev_day_conversions is not null
      and prev_day_conversions > 0
      and conversions <= prev_day_conversions * (1 - anomaly_drop_pct)
),
budget_alerts as (
    select
        client_id,
        account_id,
        account_name,
        report_date,
        'budget_exhausted' as alert_type,
        'medium' as severity,
        concat('Campaign ', campaign_name, ' likely exhausted budget early') as alert_message
    from budget_flags
    where budget_exhausted_flag
),
keyword_alerts as (
    select
        client_id,
        account_id,
        account_name,
        current_date() as report_date,
        'keyword_issue' as alert_type,
        'medium' as severity,
        concat('Keyword "', keyword_text, '" flagged as ', audit_reason) as alert_message
    from keyword_audit
    where audit_reason != 'ok'
)

select * from conversion_drop_alerts
union all
select * from budget_alerts
union all
select * from keyword_alerts

