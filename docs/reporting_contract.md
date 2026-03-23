# Ads Reporting Contract

This document is the team-review version of the current ads-only reporting contract.

It combines:

- reporting scope
- page descriptions
- data contracts
- source dependencies
- explicit phase boundaries

## Pass 2 Review Status

This document now reflects a second contract pass after review.

Already reflected in the contract:

- `client_id` is treated as part of every mart grain
- null search terms remain excluded in staging
- `cfg_segments` is documented as a real segmentation mechanism, not placeholder-only metadata

Agreed direction, implementation pending:

- currency handling must preserve original currency and add EUR reporting values
- search terms must remain date-filterable at daily grain
- keyword reporting should separate daily fact storage from audit rollups
- data freshness should become a first-class metadata output
- application queries must always enforce `client_id` filtering
- ad-level reporting should be added as the next ads-only extension
- mart schemas should move toward enforced dbt contracts

Still open:

- exchange-rate cadence and source
- UI default currency
- whether RSA asset-level reporting belongs in the first ad-level release
- whether row-level security is needed beyond the application layer
- final environment and dataset naming strategy for dev, staging, and prod

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
- define manual business segmentation such as `Brand`, `Generic`, `Competitor`, or `Retargeting`

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
- `client_id` is part of the documented mart grain, not just a selected column.
- Date-based marts must carry `report_date` or `report_month`.
- UI code must read marts, not raw transfer tables.
- Client-specific variations belong in config tables or staging adapters.
- Application queries must always filter by `client_id`.
- Cost and value metrics must preserve original account currency semantics before any reporting-currency conversion.

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

## Currency Contract

Status:

- agreed, implementation pending

Rules:

- staging models must preserve raw account-currency values
- staging cost and value fields should be named as original-currency values, not as EUR unless a real conversion has happened
- mart models should expose both original-currency values and EUR-converted values for money metrics
- exchange-rate logic must be explicit and auditable

Required direction:

- `cost_original` plus the account currency code
- `conversion_value_original` plus the account currency code
- `cost_eur`
- `conversion_value_eur`
- derived cost-per metrics should have both original-currency and EUR variants where relevant

Planned config dependency:

- `cfg_exchange_rates`

Open questions:

- whether exchange rates should be daily or monthly in phase 1
- whether the UI should default to native currency or EUR

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
- optional `segment_label` from `cfg_segments`
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

Supporting direction:

- add a separate daily fact mart for keyword-level time-series analysis

Purpose:

- classify keywords into operational buckets for action
- support date-windowed audit logic without losing daily performance traceability

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

Contract direction:

- the audit mart may remain a rollup mart for a configured lookback window
- daily keyword analysis should not depend on the audit mart alone

### 4. Search Terms Explorer

Backing mart:

- `mart_ads_search_terms`

Purpose:

- identify waste and opportunity in actual search terms
- support real date-range filtering in the UI

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
- search term reporting is expected to remain daily-grain so filters like "last 7 days" or "this month" are trustworthy

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

### 8. Ad Copy Performance

Status:

- agreed, implementation pending

Planned backing mart:

- `mart_ads_ad_performance_daily`

Planned supporting staging:

- `stg_ad_dimension_latest`
- `stg_ad_stats_daily`

Purpose:

- review ad-level performance and identify underperforming or scalable ads

Expected dimensions:

- campaign
- ad group
- ad id
- ad type
- ad status
- final URL
- text-copy fields where available

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

Open question:

- whether RSA asset-level detail is part of the first ad-level release or deferred

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

### `stg_ad_dimension_latest`

Status:

- planned, implementation pending

Planned grain:

- latest ad state per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`

### `stg_ad_stats_daily`

Status:

- planned, implementation pending

Planned grain:

- one row per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`, `report_date`

## Mart Contracts

### `mart_ads_overview_daily`

Grain:

- one row per `client_id`, `account_id`, `report_date`

### `mart_ads_overview_monthly`

Grain:

- one row per `client_id`, `account_id`, `report_month`

### `mart_ads_campaign_daily`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `report_date`

### `mart_ads_keyword_audit_detail`

Status:

- current mart exists
- supporting daily keyword mart is planned

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`

Window rule:

- this mart is a rollup for a defined reporting window or lookback, not a substitute for daily keyword facts

### `mart_ads_keyword_performance_daily`

Status:

- planned, implementation pending

Planned grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `report_date`

### `mart_ads_budget_exhaustion`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `report_date`

### `mart_ads_adgroup_daypart`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `daypart`

### `mart_ads_search_terms`

Grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `keyword_id`, `search_term`, `report_date`

### `mart_ads_alerts`

Grain:

- one row per generated alert event, including `client_id`, `account_id`, and `report_date`

### `mart_ads_ad_performance_daily`

Status:

- planned, implementation pending

Planned grain:

- one row per `client_id`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`, `report_date`

## Data Freshness And SLA

Status:

- agreed, implementation pending

Operational expectation:

- standard reporting latency is T-1
- new-account backfills may take 2-3 days

Planned metadata mart:

- `mart_data_freshness`

Planned outputs:

- `client_id`
- `account_id`
- `last_data_date`
- `freshness_status`
- `checked_at`

Planned SLA thresholds:

- warn after 36 hours
- error after 72 hours

Implementation note:

- freshness may be implemented through staging-based metadata or `INFORMATION_SCHEMA` logic rather than only through standard dbt source freshness

## Access Isolation

Status:

- agreed for phase 1

Phase 1 rule:

- report access is application-mediated
- clients do not receive direct BigQuery credentials
- every report query must include `WHERE client_id = @client_id`

Future option:

- if direct BigQuery or Looker-style access is introduced, revisit row-level security

## Change Management

Status:

- agreed in direction, implementation pending

Non-breaking changes:

- adding a column
- adding a mart
- adding rows

Breaking changes:

- removing a column
- renaming a column
- changing a column type
- changing grain

Policy direction:

- breaking changes require a deprecation period
- marts should move toward explicit dbt-enforced contracts
- the reporting app should depend only on contracted mart schemas

## Verification Status

Current verified build status:

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `87/87` passed

Verification reference:

- `docs/verification.md`

Contract note:

- the verified build still reflects the first executable pass
- some pass-2 contract additions above are agreed but not yet implemented in SQL

## Review Questions For The Team

- Is the ads-only scope correct for phase 1?
- Are the report pages above the right minimum set?
- Are the current keyword audit classifications sufficient?
- Should we approve the split between daily keyword facts and keyword audit rollups?
- Do we approve dual-currency reporting as a phase-1 requirement?
- Should alerts remain simple rule-based logic in V1?
- Do we want data freshness shown on every report page?
- Is application-level isolation sufficient for the first release?
- Should ad-level reporting be added immediately after the overview, campaign, and keyword pages?
- Do we want `cfg_segments` wired into campaign reporting in the next implementation pass?
- Which additional client-specific exports must be modeled in staging next?
- Do we want auction insights as a required source or optional manual upload?
- Should mart contracts be enforced before the HTML layer is built?
