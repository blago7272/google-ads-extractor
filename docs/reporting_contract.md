# Ads Reporting Contract

This document is the team-review version of the current ads-only reporting contract.

It combines:

- reporting scope
- page descriptions
- data contracts
- source dependencies
- explicit phase boundaries

## Purpose

Build a shared, multi-account Google Ads reporting layer on top of the existing BigQuery raw export.

The reporting layer must:

- support many Google Ads accounts with the same core logic
- keep client-specific behavior in config, not copied SQL
- expose stable marts for an HTML reporting application
- be testable and contract-driven before UI work continues

## Current Scope

This contract is for the ads-only phase.

Included now:

- account overview
- monthly audit summary
- daily ads trend
- campaign explorer
- keyword audit
- search terms explorer
- budget exhaustion
- ad group daypart profile
- alerts
- optional auction insights placeholder

Deferred to later blended Ads + GA4 phase:

- funnel anomalies
- landing pages
- channel mix
- product analysis
- order or revenue heatmaps
- blended anomaly pages that depend on site behavior or ecommerce events

## Dataset Contract

### Raw Source

Dataset:

- `gads_raw`

Rules:

- read-only
- no reporting logic in raw tables
- no client-specific rewrites inside the raw layer

### Reporting Config

Dataset:

- `gads_reporting_cfg`

Objects:

- `cfg_accounts`
- `cfg_account_groups`
- `cfg_thresholds`
- `cfg_segments`

Purpose:

- define which accounts are managed
- define active accounts
- define thresholds and labels used by the marts

### Reporting Staging

Dataset:

- `gads_reporting_stg`

Purpose:

- standardize Google Ads transfer tables into stable shapes
- preserve raw semantics
- filter only where the reporting contract explicitly requires it

### Reporting Marts

Dataset:

- `gads_reporting_mart`

Purpose:

- provide report-ready tables for the future HTML layer
- contain business logic, classifications, and rollups

## Global Rules

- All marts must be shared across clients and accounts.
- All report-facing marts must be filtered to configured active accounts.
- Every report-facing mart must carry `client_id` and `account_id`.
- Date-based marts must carry `report_date` or `report_month`.
- UI code must read marts, not raw transfer tables.
- Client-specific variations belong in config tables or staging adapters.

## Managed Account Contract

Seed:

- `cfg_accounts`

Grain:

- one row per managed Google Ads account

Required fields:

- `client_id`
- `account_id`
- `account_name`
- `timezone`
- `currency`
- `is_active`

Current pilot account:

- `1200697994`
- `Sexwell.bg (EUR)`

## Report Pages

### 1. Overview

Backing marts:

- `mart_ads_overview_daily`
- `mart_ads_overview_monthly`
- `mart_ads_alerts`

Purpose:

- give a fast account-level view of performance and current issues

Expected metrics:

- spend
- clicks
- impressions
- conversions
- conversion value
- CTR
- CPC
- CPA
- ROAS

Expected UI behavior:

- date filtering
- period comparison
- KPI cards
- trend chart
- recent alerts list

### 2. Campaign Explorer

Backing mart:

- `mart_ads_campaign_daily`

Purpose:

- inspect campaign performance over time and sort or filter by key metrics

Expected dimensions:

- campaign
- channel type
- channel subtype
- bidding strategy
- status

Expected metrics:

- spend
- clicks
- impressions
- conversions
- conversion value
- CTR
- CPC
- CPA
- ROAS

### 3. Keyword Audit

Backing mart:

- `mart_ads_keyword_audit_detail`

Purpose:

- classify keywords into operational buckets for action

Current classification contract:

- `low_qs`
- `intent_or_offer`
- `low_volume`
- `scale_but_fix_qs`
- `ok`

Expected dimensions:

- campaign
- ad group
- keyword text
- match type
- keyword status
- quality score

Expected metrics:

- spend
- clicks
- impressions
- conversions
- conversion value
- CPA

### 4. Search Terms Explorer

Backing mart:

- `mart_ads_search_terms`

Purpose:

- identify waste and opportunity in actual search terms

Expected dimensions:

- campaign
- ad group
- keyword id
- search term
- search term status
- search term match type

Expected metrics:

- spend
- clicks
- impressions
- conversions
- conversion value

Contract note:

- null search terms are excluded in staging

### 5. Budget Exhaustion

Backing mart:

- `mart_ads_budget_exhaustion`

Purpose:

- flag campaigns that likely stopped spending too early in the day

Expected dimensions:

- campaign
- report date

Expected outputs:

- total daily spend
- first active hour
- last active hour
- `budget_exhausted_flag`

### 6. Ad Group Daypart Profile

Backing mart:

- `mart_ads_adgroup_daypart`

Purpose:

- compare day vs night performance by ad group

Daypart contract:

- `day`
- `night`

Expected metrics:

- spend
- clicks
- impressions
- conversions
- conversion value
- CPA
- ROAS

### 7. Alerts

Backing mart:

- `mart_ads_alerts`

Purpose:

- give a consolidated feed of actionable issues

Current alert type contract:

- `conversion_drop`
- `budget_exhausted`
- `keyword_issue`

Current severity contract:

- `high`
- `medium`

## Staging Model Contracts

### `stg_account_stats_daily`

Grain:

- one row per `transfer_source`, `account_id`, `report_date`

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

- latest campaign state per `transfer_source`, `account_id`, `campaign_id`

### `stg_ad_group_dimension_latest`

Grain:

- latest ad group state per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`

### `stg_keyword_dimension_latest`

Grain:

- latest keyword state per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

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

### `mart_ads_overview_monthly`

Grain:

- one row per `account_id`, `report_month`

### `mart_ads_campaign_daily`

Grain:

- one row per `account_id`, `campaign_id`, `report_date`

### `mart_ads_keyword_audit_detail`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

### `mart_ads_budget_exhaustion`

Grain:

- one row per `account_id`, `campaign_id`, `report_date`

### `mart_ads_adgroup_daypart`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `daypart`

### `mart_ads_search_terms`

Grain:

- one row per `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`

### `mart_ads_alerts`

Grain:

- one row per generated alert event

## Verification Status

Current verified build status:

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `87/87` passed

Verification reference:

- `docs/verification.md`

## Review Questions For The Team

- Is the ads-only scope correct for phase 1?
- Are the report pages above the right minimum set?
- Are the current keyword audit classifications sufficient?
- Should alerts remain simple rule-based logic in V1?
- Which additional client-specific exports must be modeled in staging next?
- Do we want auction insights as a required source or optional manual upload?

