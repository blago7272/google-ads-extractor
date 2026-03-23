# Data Contracts

This file defines the implemented grain and minimum required fields for the current ads-only reporting build.

## Global Rules

- staging models preserve native account-currency values with `*_original` naming
- EUR conversions are resolved from `cfg_exchange_rates`
- report-facing marts carry both `client_id` and `account_id`
- report-facing marts read only configured active accounts

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

### `cfg_exchange_rates`

Grain:

- one row per `currency`, `valid_from`

Required fields:

- `currency`
- `valid_from`
- `eur_exchange_rate`

## Staging Contracts

### `stg_account_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `report_date`

Required fields:

- `transfer_source`
- `account_id`
- `report_date`
- `cost_original`
- `clicks`
- `impressions`
- `conversions`
- `conversion_value_original`

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

### `stg_budget_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `campaign_budget_id`, `report_date`

### `stg_campaign_dimension_latest`

Grain:

- one row per latest campaign state for `transfer_source`, `account_id`, `campaign_id`

Required money fields:

- `campaign_budget_original`

### `stg_ad_group_dimension_latest`

Grain:

- one row per latest ad group state for `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`

### `stg_keyword_dimension_latest`

Grain:

- one row per latest keyword state for `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

Required money fields:

- `first_page_cpc_original`
- `top_of_page_cpc_original`

### `stg_keyword_performance_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `report_date`

### `stg_search_query_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`, `search_term_status`, `search_term_match_type`, `report_date`

### `stg_ad_dimension_latest`

Grain:

- one row per latest ad state for `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`

Required fields:

- `ad_id`
- `ad_type`
- `ad_status`
- `approval_status`
- `ad_label`

### `stg_ad_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`, `report_date`

### `stg_account_fx_rates_daily`

Grain:

- one row per `account_id`, `report_date`

Required fields:

- `account_id`
- `currency`
- `report_date`
- `eur_exchange_rate`

### `stg_exchange_rates_latest`

Grain:

- one row per `currency`

Required fields:

- `currency`
- `eur_exchange_rate`

## Mart Contracts

### `mart_ads_overview_daily`

Grain:

- one row per `client_id`, `account_id`, `report_date`

Required fields:

- `client_id`
- `account_id`
- `account_name`
- `currency`
- `report_date`
- `cost_original`
- `cost_eur`
- `conversion_value_original`
- `conversion_value_eur`

### `mart_ads_overview_monthly`

Grain:

- one row per `client_id`, `account_id`, `report_month`

### `mart_ads_campaign_daily`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `report_date`

Required money fields:

- `campaign_budget_original`
- `campaign_budget_eur`
- `cost_original`
- `cost_eur`

### `mart_ads_keyword_audit_detail`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

Required window fields:

- `report_date_start`
- `report_date_end`

Contracted enumerations:

- `audit_reason` in `low_qs`, `intent_or_offer`, `low_volume`, `scale_but_fix_qs`, `ok`

### `mart_ads_budget_exhaustion`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `report_date`

Required fields:

- `total_cost_original`
- `total_cost_eur`
- `budget_exhausted_flag`

### `mart_ads_adgroup_daypart`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `daypart`

Contracted enumerations:

- `daypart` in `day`, `night`

### `mart_ads_search_terms`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`, `report_date`

Rollup rule:

- if a search term is split across multiple `search_term_status` or `search_term_match_type` values inside the same daily grain, the mart collapses them and emits `MULTIPLE`

### `mart_ads_alerts`

Grain:

- one row per generated alert event

Contracted enumerations:

- `alert_type` in `conversion_drop`, `budget_exhausted`, `keyword_issue`
- `severity` in `high`, `medium`

### `mart_ads_ad_performance_daily`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`, `report_date`

Required dimensions:

- `ad_id`
- `ad_type`
- `ad_status`
- `approval_status`
- `ad_label`

Required money fields:

- `cost_original`
- `cost_eur`
- `conversion_value_original`
- `conversion_value_eur`
