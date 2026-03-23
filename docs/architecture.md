# Ads-Only Reporting Architecture

## Implementation Choice

Use one shared reporting model for all clients.

- keep `gads_raw` as the immutable source
- add config tables for per-client behavior
- normalize raw transfer tables into shared staging views
- build report marts from those views
- keep the UI thin and let BigQuery own the business logic

Do not duplicate the full reporting dataset per client unless you need hard isolation or a separate billing boundary.

## Dataset Layout

### `gads_raw`

Raw Google Ads transfer tables such as:

- `p_ads_AccountStats_*`
- `p_ads_CampaignStats_*`
- `p_ads_AdGroupStats_*`
- `p_ads_HourlyCampaignStats_*`
- `p_ads_HourlyAdGroupStats_*`
- `p_ads_KeywordStats_*`
- `p_ads_SearchQueryStats_*`
- `p_ads_Campaign_*`
- `p_ads_AdGroup_*`
- `p_ads_Keyword_*`

### `gads_reporting_cfg`

Configuration tables:

- `cfg_accounts`
- `cfg_account_groups`
- `cfg_thresholds`
- `cfg_segments`

### `gads_reporting_stg`

Standardized staging views:

- `stg_account_stats_daily`
- `stg_campaign_stats_daily`
- `stg_campaign_stats_hourly`
- `stg_ad_group_stats_daily`
- `stg_ad_group_stats_hourly`
- `stg_budget_stats_daily`
- `stg_campaign_dimension_latest`
- `stg_ad_group_dimension_latest`
- `stg_keyword_dimension_latest`
- `stg_keyword_performance_daily`
- `stg_search_query_stats_daily`

### `gads_reporting_mart`

Report-facing marts:

- `mart_ads_overview_daily`
- `mart_ads_overview_monthly`
- `mart_ads_campaign_daily`
- `mart_ads_keyword_audit_detail`
- `mart_ads_budget_exhaustion`
- `mart_ads_adgroup_daypart`
- `mart_ads_search_terms`
- `mart_ads_alerts`

### `gads_manual`

Optional manual uploads:

- `auction_insights_raw`

## Data Contracts

Every mart should include:

- `client_id`
- `account_id`
- `account_name`
- `report_date`

Dimension marts should include:

- `campaign_id`, `campaign_name`
- `ad_group_id`, `ad_group_name`
- `keyword_id`, `keyword_text`, `match_type`

## Rules

- raw tables are read-only
- config owns client-specific behavior
- staging owns source normalization
- marts own reporting logic
- app code only filters, renders, and exports

