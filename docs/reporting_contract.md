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
- currency handling now preserves original currency and adds EUR reporting values
- search terms now remain date-filterable at daily grain
- ad-level reporting now exists through `mart_ads_ad_performance_daily`
- mart schemas are now enforced through dbt contracts in `gads_reporting_mart`
- account-level feature flags exist in `cfg_accounts` for GA4 and auction insights visibility

Agreed direction, implementation pending:

- keyword reporting should separate daily fact storage from audit rollups
- data freshness should become a first-class metadata output
- application queries must always enforce `client_id` filtering

Still open, with recommended resolution:

- exchange-rate cadence and source
  Recommended resolution: use a monthly exchange-rate seed in phase 1, plus fixed mappings for pegged currencies where appropriate; move to a daily external feed before scaling volatile non-EUR accounts
- UI default currency
  Recommended resolution: use native currency by default on single-account views and EUR by default on cross-account or client-rollup views
- whether RSA asset-level reporting belongs in the first ad-level release
  Recommended resolution: defer RSA asset-level reporting from the first ad-level release
- whether row-level security is needed beyond the application layer
  Recommended resolution: defer until direct BigQuery or BI-tool access is introduced
- final environment and dataset naming strategy for dev, staging, and prod
  Recommended resolution: handle this in a separate infrastructure design and use explicit per-environment dataset names rather than hidden suffix concatenation

Current design documents:

- `docs/infrastructure_design.md`
- `docs/operations_design.md`

## Proposal Disposition

This section records the current Codex recommendation on the review proposals.

### 1. `client_id` On Every Mart Grain

Recommendation:

- accept

Comment:

- This should be treated as part of the formal mart grain and the required downstream filter key.

### 2. Date Ranges On Search Terms And Keyword Audit

Recommendation:

- accept with modification

Comment:

- `mart_ads_search_terms` should remain daily-grain.
- keyword reporting should split into a daily fact mart plus an audit rollup mart.

### 3. Currency Handling

Recommendation:

- accept

Comment:

- high priority
- staging should preserve original-currency semantics
- mart layer should expose both native-currency and EUR values

### 4. Data Freshness

Recommendation:

- accept

Comment:

- implement a freshness metadata mart
- do not rely only on standard dbt source freshness if wildcarded source shapes make that brittle

### 5. Client Data Access And Isolation

Recommendation:

- accept for phase 1 at the application layer

Comment:

- defer row-level security unless direct warehouse or BI access is introduced

### 6. Ad-Level Reporting

Recommendation:

- accept

Comment:

- add ad-level performance next
- defer RSA asset-level detail from the first release

### 7. `cfg_segments` Purpose And Status

Recommendation:

- accept and wire into campaign reporting

Comment:

- this is a useful agency-facing grouping mechanism and should not remain placeholder-only

### 8. Alert Thresholds Linkage

Recommendation:

- defer

Comment:

- the current simple rule-based alerting is sufficient for the first release

### 9. Change Management And Versioning

Recommendation:

- accept

Comment:

- move mart schemas toward enforced dbt contracts before the HTML layer depends on them

## Current Implementation Snapshot

Verified in this workspace on `2026-03-23`.

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `151/151` passed

Current pilot mart row counts:

- `mart_ads_overview_daily`: `201`
- `mart_ads_overview_monthly`: `7`
- `mart_ads_campaign_daily`: `1086`
- `mart_ads_keyword_audit_detail`: `149`
- `mart_ads_search_terms`: `86292`
- `mart_ads_budget_exhaustion`: `1086`
- `mart_ads_adgroup_daypart`: `72`
- `mart_ads_alerts`: `115`
- `mart_ads_ad_performance_daily`: `6574`

### 10. Infrastructure Decisions

Recommendation:

- accept directionally, with a separate technical design pass

Comment:

- scheduling, environments, partitioning, monitoring, and backfill strategy all make sense
- environment and dataset naming must be designed explicitly against the current schema-macro approach

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
- `cfg_exchange_rates`
- `cfg_segments`
- `cfg_app_users`

Purpose:

- define which accounts are managed
- define active accounts
- define whether optional report packs should be visible for each account
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
- `has_auction_insights`
- `has_ga4`
- `notes`

Feature-flag meanings:

- `has_ga4`
  whether the selected account participates in the standalone GA4 report pack
- `has_auction_insights`
  whether the selected account participates in the standalone auction insights report

Current active accounts:

- `1200697994`
- `Sexwell.bg (EUR)`
- `4848659150`
- `Matraci (EUR)`

## Currency Contract

Status:

- implemented for phase 1

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

Current config dependency:

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

- implemented for ad-level daily performance

Current backing mart:

- `mart_ads_ad_performance_daily`

Current supporting staging:

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

Note:

- multiple raw rows can still exist for the same daily search-term grain when Google Ads emits different `segments_search_term_match_type` values
- that variance is collapsed in `mart_ads_search_terms`

### `stg_account_fx_rates_daily`

Status:

- implemented

Grain:

- one row per `account_id`, `report_date`

### `stg_exchange_rates_latest`

Status:

- implemented

Grain:

- one row per `currency`

### `stg_ad_dimension_latest`

Status:

- implemented

Grain:

- latest ad state per `transfer_source`, `account_id`, `campaign_id`, `ad_group_id`, `ad_id`

### `stg_ad_stats_daily`

Status:

- implemented

Grain:

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

Rollup rule:

- `search_term_status` and `search_term_match_type` are collapsed to `MULTIPLE` when more than one raw value exists within the published daily mart grain

### `mart_ads_alerts`

Grain:

- one row per generated alert event, including `client_id`, `account_id`, and `report_date`

### `mart_ads_ad_performance_daily`

Status:

- implemented

Grain:

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

- implemented for current marts

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
- marts are protected by explicit dbt-enforced contracts
- the reporting app should depend only on contracted mart schemas

## Verification Status

Current verified build status:

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `151/151` passed

Verification reference:

- `docs/verification.md`
- `docs/team_review_checklist.md`

Contract note:

- the verified build now includes dual-currency marts, ad-level reporting, FX staging helpers, and enforced mart contracts
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
- Do we want `cfg_segments` wired into campaign reporting in the next implementation pass?
- Which additional client-specific exports must be modeled in staging next?
- Do we want auction insights as a required source or optional manual upload?
- Do we ratify the implemented dual-currency and ad-level contracts as the phase-1 baseline?

## Team Review Checklist

For a shorter meeting-oriented version of the open decisions, use:

- `docs/team_review_checklist.md`
