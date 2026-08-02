# Data Field Inventory

Date: 2026-04-13

## Raw Source Tables (BigQuery Data Transfer)

All tables live in `gads-export-all.gads_raw` and use wildcard suffixes (`_*`) for multi-account transfers.

| Raw Table Pattern | Category | Key Fields |
|-------------------|----------|------------|
| `p_ads_AccountStats_*` | Daily metrics | account_id, segments_date, metrics_cost_micros, metrics_clicks, metrics_impressions, metrics_conversions, metrics_conversions_value |
| `p_ads_CampaignStats_*` | Daily metrics | + campaign_id |
| `p_ads_HourlyCampaignStats_*` | Hourly metrics | + campaign_id, segments_hour |
| `p_ads_AdGroupStats_*` | Daily metrics | + campaign_id, ad_group_id |
| `p_ads_HourlyAdGroupStats_*` | Hourly metrics | + campaign_id, ad_group_id, segments_hour |
| `p_ads_BudgetStats_*` | Daily metrics | + campaign_id, campaign_budget_id, campaign_name, campaign_status |
| `p_ads_AdStats_*` | Daily metrics | + campaign_id, ad_group_id, ad_id |
| `p_ads_KeywordStats_*` | Daily metrics | + campaign_id, ad_group_id, keyword_id |
| `p_ads_SearchQueryStats_*` | Daily metrics | + campaign_id, ad_group_id, keyword_id, search_term, search_term_status, match_type |
| `p_ads_Campaign_*` | Dimensions | campaign_id, campaign_name, campaign_status, serving_status, channel_type, channel_sub_type, bidding_strategy_type, budget |
| `p_ads_AdGroup_*` | Dimensions | ad_group_id, campaign_id, ad_group_name, ad_group_status, ad_group_type |
| `p_ads_Keyword_*` | Dimensions | keyword_id, keyword_text, match_type, is_negative, status, quality_score, creative_quality, post_click_quality, predicted_ctr, first_page_cpc, top_of_page_cpc |
| `p_ads_Ad_*` | Dimensions | ad_id, ad_type, ad_status, approval_status, ad_strength, headline, description, final_urls, responsive_search_ad fields |

## Configuration Seeds

| Seed | Records | Key Fields | Status |
|------|---------|------------|--------|
| `cfg_accounts` | 96 | client_id, account_id, account_name, timezone, currency, is_active, has_auction_insights, has_ga4 | Populated — 6 clients, mix of active/inactive |
| `cfg_account_groups` | 1 | group_id, account_id | Minimal — single placeholder group |
| `cfg_thresholds` | 6 | client_id (default), threshold_key, threshold_value | Populated — all default-level thresholds |
| `cfg_exchange_rates` | 2 | currency, valid_from, eur_exchange_rate | Partial — EUR + BGN only. Missing: USD, GBP, RON, MXN |
| `cfg_segments` | 1 | client_id, entity_level, entity_id, segment_label | Placeholder — needs real campaign IDs |

## Staging Models (16 total)

### Metric Models (9)
| Model | Grain | Monetary Fields | Derived Metrics |
|-------|-------|-----------------|-----------------|
| stg_account_stats_daily | account × date | cost_original | ctr, cpc_original, cpa_original, roas |
| stg_campaign_stats_daily | campaign × date | cost_original | ctr, cpc_original, cpa_original, roas |
| stg_campaign_stats_hourly | campaign × date × hour | cost_original | — |
| stg_ad_group_stats_daily | ad_group × date | cost_original | — |
| stg_ad_group_stats_hourly | ad_group × date × hour | cost_original | — |
| stg_budget_stats_daily | budget × campaign × date | cost_original | — |
| stg_ad_stats_daily | ad × date | cost_original | ctr, cpc_original, cpa_original, roas |
| stg_keyword_performance_daily | keyword × date | cost_original | ctr, cpc_original, cpa_original, roas |
| stg_search_query_stats_daily | search_term × keyword × date | cost_original | — |

### Dimension Models (4)
| Model | Grain | Notable Fields |
|-------|-------|----------------|
| stg_campaign_dimension_latest | campaign (latest snapshot) | campaign_name, status, channel_type, bidding_strategy, budget |
| stg_ad_group_dimension_latest | ad_group (latest snapshot) | ad_group_name, status, type |
| stg_keyword_dimension_latest | keyword (latest snapshot) | keyword_text, match_type, quality_score (3 sub-scores), first_page_cpc, top_of_page_cpc |
| stg_ad_dimension_latest | ad (latest snapshot) | ad_type, status, strength, headline_primary, description_primary, landing_page_url, ad_label |

### FX & Manual (3)
| Model | Purpose |
|-------|---------|
| stg_account_fx_rates_daily | Daily FX rate per account (joined from cfg_exchange_rates) |
| stg_exchange_rates_latest | Latest FX rate per currency (for budget conversions) |
| stg_auction_insights | Manual upload stub (all nulls currently) |

## Mart Models (14 total)

| Model | Grain | EUR Fields | Special Logic |
|-------|-------|------------|---------------|
| mart_ads_overview_daily | account × date | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | — |
| mart_ads_overview_monthly | account × month | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | Monthly rollup |
| mart_ads_campaign_daily | campaign × date | cost_eur, cpc_eur, cpa_eur, campaign_budget_eur, conversion_value_eur | Dual FX (daily + latest for budget) |
| mart_ads_ad_group_daily | ad_group × date | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | — |
| mart_ads_hourly_performance_daily | account × date × hour | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | weekday_number, weekday_name |
| mart_ads_keyword_daily | keyword × date | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | quality_score from dimension |
| mart_ads_keyword_audit_detail | keyword (all-time rollup) | cost_eur, cpa_eur, first_page_cpc_eur, top_of_page_cpc_eur, conversion_value_eur | audit_reason classification |
| mart_ads_budget_exhaustion | campaign × date | total_cost_eur | budget_exhausted_flag |
| mart_ads_adgroup_daypart | ad_group × date × daypart | cost_eur, cpa_eur, conversion_value_eur | daypart = day/night split |
| mart_ads_ad_performance_daily | ad × date | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | ad creative fields |
| mart_ads_search_terms | search_term × date | cost_eur, cpc_eur, cpa_eur, conversion_value_eur | MULTIPLE status handling |
| mart_ads_auction_insights_monthly | account × month × competitor | — | Manual upload backed |
| mart_ads_alerts | account × date × alert | — | Union of 3 alert types |
| mart_data_freshness | account (singleton) | — | freshness_status: ok/stale/error/backfilling |

## Fields That Are Populated vs Missing

### Populated
- All metric fields (cost, clicks, impressions, conversions, conversion_value) across all grains
- All dimension fields (names, statuses, types) for campaigns, ad groups, keywords, ads
- Quality score decomposition (creative, post-click, predicted CTR)
- EUR conversions for BGN accounts
- 96 account configurations across 6 clients

### Missing or Incomplete
- **Exchange rates**: Only EUR and BGN configured. USD, GBP, RON, MXN accounts exist but have no FX rates — EUR conversions will be NULL for these.
- **Segments**: Placeholder only. No real campaign-to-segment mappings exist yet.
- **Account groups**: Single placeholder group. No real multi-account rollup groups defined.
- **Auction insights**: Stub model with all NULLs. Real data lives in external tables (`experimental-clients.sexwell_analyses.gads--impression_share--*`), accessed directly by the app layer, not through dbt.
- **Client-specific thresholds**: All thresholds are default-level. No per-client overrides exist.
- **GA4 data**: Not in dbt. Queried directly from `experimental-clients.sexwell_analyses.GA4-*` by the app.
