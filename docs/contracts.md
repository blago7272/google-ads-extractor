# Data Contracts

This file defines the intended grain and minimum required fields for the first ads-only implementation.

## Seed Contracts

### `cfg_accounts`

Grain:

- one row per managed Google Ads account

Required fields:

- `client_id`
- `account_id`
- `account_name`
- `timezone`
- `currency`
- `is_active`

### `cfg_account_groups`

Grain:

- one row per account-group membership

Required fields:

- `group_id`
- `account_id`

### `cfg_thresholds`

Grain:

- one row per threshold key and scope

Required fields:

- `client_id`
- `threshold_key`
- `threshold_value`

## Staging Contracts

### `stg_account_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `report_date`

Required fields:

- `transfer_source`
- `account_id`
- `report_date`
- `cost_eur`
- `clicks`
- `impressions`
- `conversions`
- `conversion_value`

### `stg_campaign_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `report_date`

### `stg_campaign_stats_hourly`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `report_date`, `report_hour`

### `stg_ad_group_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `report_date`

### `stg_ad_group_stats_hourly`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `report_date`, `report_hour`

### `stg_keyword_dimension_latest`

Grain:

- one row per latest keyword state for `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

### `stg_keyword_performance_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `report_date`

### `stg_search_query_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`, `report_date`

## Mart Contracts

### `mart_ads_overview_daily`

Grain:

- one row per `account_id`, `report_date`

Required fields:

- `client_id`
- `account_id`
- `account_name`
- `report_date`
- `cost_eur`
- `clicks`
- `impressions`
- `conversions`
- `conversion_value`

### `mart_ads_overview_monthly`

Grain:

- one row per `account_id`, `report_month`

### `mart_ads_campaign_daily`

Grain:

- one row per `account_id`, `campaign_id`, `report_date`

### `mart_ads_keyword_audit_detail`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

Contracted enumerations:

- `audit_reason` in `low_qs`, `intent_or_offer`, `low_volume`, `scale_but_fix_qs`, `ok`

### `mart_ads_budget_exhaustion`

Grain:

- one row per `account_id`, `campaign_id`, `report_date`

### `mart_ads_adgroup_daypart`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `daypart`

Contracted enumerations:

- `daypart` in `day`, `night`

### `mart_ads_search_terms`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`

### `mart_ads_alerts`

Grain:

- one row per generated alert event

Contracted enumerations:

- `alert_type` in `conversion_drop`, `budget_exhausted`, `keyword_issue`
- `severity` in `high`, `medium`

