# Contract Review Proposals

This document captures proposals, open questions, and decisions arising from the
initial contract review. Each section has a status and is meant for collaborative
discussion before changes are merged into the main contracts.

Status legend:

- `PROPOSAL` — needs team decision
- `AGREED` — direction accepted, implementation pending
- `DEFERRED` — parked for a later phase
- `DONE` — implemented and verified

---

## 1. client_id On Every Mart Grain

Status: `PROPOSAL`

### Context

`client_id` is the agency client — the business that hired the agency. One client
can have multiple Google Ads accounts. It is the multi-tenant isolation key.

Currently, the contract says every mart must carry `client_id`, and the SQL already
does (via the join to `cfg_accounts`). However, the grain definitions for several
marts omit it:

- `mart_ads_campaign_daily` — grain says `account_id, campaign_id, report_date`
- `mart_ads_budget_exhaustion` — grain says `account_id, campaign_id, report_date`
- `mart_ads_adgroup_daypart` — grain says `account_id, campaign_id, ad_group_id, daypart`
- `mart_ads_search_terms` — grain says `account_id, campaign_id, ad_group_id, keyword_id, search_term`

### Risk

Without `client_id` as a documented grain column, a downstream consumer might
filter only by `account_id`. If two clients ever share overlapping account ID
spaces (unlikely with Google Ads, but possible in a multi-source future), data
could leak. More practically, any client-facing API must be able to filter by
`client_id` alone without needing to resolve account memberships.

### Proposal

Add `client_id` to the grain definition of every mart. This does not change the
SQL (it is already selected). It changes the contract to match reality and ensures
downstream consumers treat it as a required filter.

---

## 2. Date Ranges On Search Terms And Keyword Audit

Status: `AGREED`

### Context

`mart_ads_search_terms` and `mart_ads_keyword_audit_detail` are currently all-time
rollups with no date dimension. For an agency reporting product, users need to
filter by date range — comparing this month vs last month, or reviewing the last
30 days of search term waste.

### Proposal

Option A — Add `report_date` to the grain of both marts, making them daily-grain
fact tables. This is the most flexible approach but increases table size.

Option B — Add `report_date_start` and `report_date_end` as metadata columns
indicating the date window covered by each rollup row. The rollup stays
aggregated, but consumers know what time range it represents.

### Recommendation

Option A for `mart_ads_search_terms` — search term analysis benefits from daily
granularity (e.g. "this search term wasted money only last week").

For `mart_ads_keyword_audit_detail`, consider keeping the rollup but adding a
configurable lookback window (e.g. last 90 days) and documenting the window in
the contract.

---

## 3. Currency Handling

Status: `AGREED`

### Context

Currently, staging models hardcode `cost_eur` as the column name. The value is
actually `metrics_cost_micros / 1000000.0` — which gives the cost in the
account's native currency, not necessarily EUR. There is no actual conversion
happening.

When the system manages accounts in multiple currencies (EUR, BGN, USD, GBP),
this becomes incorrect. The column is labeled EUR but contains, say, BGN values
for a BGN-denominated account.

### Requirements

- Every cost/value column must exist in the account's original currency.
- Every cost/value column must also exist in a universal reporting currency (EUR).
- The UI should allow switching between original and EUR views.
- Conversion rates must be auditable (not buried in SQL logic).

### Proposal

#### 3a. Config: Exchange Rate Seed

Add a new seed `cfg_exchange_rates`:

```
currency_from,currency_to,rate,effective_date,notes
BGN,EUR,0.5113,2026-01-01,Fixed rate (BGN is pegged to EUR)
USD,EUR,0.92,2026-03-01,Approximate — replace with daily feed later
EUR,EUR,1.0,2026-01-01,Identity
```

For phase 1, use a simple seed with approximate or fixed rates. Later, replace
with a daily exchange rate table from an external feed.

#### 3b. Staging: Rename And Preserve Original Currency

In staging models, rename `cost_eur` to `cost_original` (the raw value in the
account's native currency). Do not convert at the staging layer — staging
preserves raw semantics.

#### 3c. Marts: Dual Currency Columns

In mart models, join to `cfg_accounts` for the account's currency and to
`cfg_exchange_rates` for the conversion rate. Produce both:

- `cost_original` + `currency` — native account currency value and code
- `cost_eur` — converted to EUR using the exchange rate

Apply the same pattern to `conversion_value`, `campaign_budget`, `cpc`, `cpa`.

#### 3d. Derived Metrics

Computed ratios (`ctr`, `roas`) are currency-agnostic and do not need dual
columns. `cpc` and `cpa` do, since they divide cost by a count.

### Open Questions

- Should exchange rates be daily or monthly? Monthly is simpler; daily is more
  accurate for volatile currencies.
- Should the UI default to EUR or to the account's native currency?

---

## 4. Data Freshness

Status: `AGREED`

### Context

Data arrives with a one-day delay (T-1). A separate loading tool manages the
BigQuery transfer. New profiles take a couple of days to backfill.

### Proposal

#### 4a. Source Freshness In dbt

Add a `sources.yml` declaring the raw tables as dbt sources with freshness checks:

```yaml
sources:
  - name: gads_raw
    freshness:
      warn_after: {count: 36, period: hour}
      error_after: {count: 72, period: hour}
    loaded_at_field: _PARTITIONTIME
    tables:
      - name: p_ads_AccountStats
      - name: p_ads_CampaignStats
      # ...
```

Run `dbt source freshness` on a schedule to detect stale data.

#### 4b. Metadata Mart For The UI

Create a small metadata mart `mart_data_freshness` that exposes:

- `account_id`
- `last_data_date` — `max(report_date)` from `stg_account_stats_daily`
- `freshness_status` — `ok` / `stale` / `backfilling`
- `checked_at` — timestamp of the dbt run

The UI renders "Data as of {last_data_date}" on every page.

#### 4c. Contract Addition

Document the freshness SLA in the contract:

- Normal latency: T-1 (data for yesterday available by early morning)
- New account backfill: 2-3 days
- Staleness threshold: warn at 36h, error at 72h

---

## 5. Client Data Access And Isolation

Status: `PROPOSAL`

### Context

Clients will access prepared reports only — not raw BigQuery data. Each client
must see only data from their own `client_id`.

### Delivery Options

Reports can be delivered via:

1. **HTML reporting app** — the primary channel. The app authenticates users,
   resolves their `client_id`, and passes it as a query parameter to BigQuery.
2. **Scheduled PDF/email exports** — generated from the same mart data.
3. **Looker Studio / embedded dashboards** — if a client needs self-service.
4. **BigQuery direct access** (future) — only if a client needs raw access.

### Proposal: Application-Level Isolation (Phase 1)

For phase 1, isolation is enforced at the application layer:

- The HTML app authenticates users and maps them to a `client_id`.
- Every BigQuery query includes `WHERE client_id = @client_id`.
- The BigQuery service account used by the app has read access to `gads_reporting_mart`.
- Clients never get direct BigQuery credentials.

This is the simplest approach and sufficient when the only access path is the app.

### Proposal: BigQuery Row-Level Security (Phase 2, If Needed)

If clients ever get direct BigQuery access or Looker Studio connections:

- Use BigQuery row-level access policies on mart tables.
- Create a `client_access` table mapping user emails to `client_id`.
- Apply `CREATE ROW ACCESS POLICY` on each mart filtering by
  `SESSION_USER()` mapped to `client_id`.

This is only needed if access paths beyond the app are opened.

### Recommendation

Start with application-level isolation. Document the rule that every mart query
from the app must include `client_id` filtering. Revisit row-level security only
when direct BigQuery access becomes a requirement.

---

## 6. Ad-Level Reporting

Status: `AGREED`

### Context

The current contract covers account, campaign, ad group, keyword, and search term
levels — but no ad-level reporting. Ad copy performance (headlines, descriptions,
responsive search ad asset performance) is a standard agency deliverable.

### Proposal

#### 6a. Raw Source

The Google Ads BigQuery transfer includes ad-level tables:

- `p_ads_Ad_*` — ad dimension (type, status, URLs)
- `p_ads_AdStats_*` — ad performance metrics

Note: Responsive Search Ad (RSA) asset-level reporting (which headline/description
combination performed best) is available via `p_ads_AssetGroupAssetCombinationStats_*`
for Performance Max, or `p_ads_AdGroupAdAssetView_*` for standard RSAs. Check
which tables are present in `gads_raw`.

#### 6b. Staging Models

Add:

- `stg_ad_dimension_latest` — latest ad state per `transfer_source, account_id,
  campaign_id, ad_group_id, ad_id`
- `stg_ad_stats_daily` — daily ad performance per `transfer_source, account_id,
  campaign_id, ad_group_id, ad_id, report_date`

#### 6c. Mart Model

Add:

- `mart_ads_ad_performance_daily` — daily ad performance joined with ad
  dimensions, campaign and ad group names

Grain: `account_id, campaign_id, ad_group_id, ad_id, report_date`

Key dimensions: ad type, ad status, final URL, headlines, descriptions

Key metrics: cost, clicks, impressions, conversions, conversion_value, ctr, cpc,
cpa, roas

#### 6d. Report Page

Add an "Ad Copy Performance" page to the report pages contract:

- Backed by `mart_ads_ad_performance_daily`
- Purpose: review ad copy effectiveness, identify underperforming ads, compare
  RSA variants
- Filters: campaign, ad group, date range, ad status

### Open Questions

- Should RSA asset-level breakdowns (individual headline/description performance)
  be in phase 1 or deferred?
- Are there specific ad types the team wants to exclude from the mart (e.g.
  display ads that don't have text copy)?

---

## 7. cfg_segments Purpose And Status

Status: `PROPOSAL`

### Context

`cfg_segments` is defined as a seed with columns `client_id, entity_level,
entity_id, segment_label, notes`. The sample data shows:

```
sexwell,campaign,0,Brand,Replace entity ids with real campaign ids once segmentation starts
```

This appears to be a mechanism for manually tagging campaigns (or other entities)
with business segments like "Brand" vs "Non-Brand", "Prospecting" vs
"Retargeting", etc.

### Options

**Option A — Keep and document.** This is a useful feature for agencies. Clients
often want to see performance grouped by business intent (Brand vs Generic vs
Competitor). The seed lets the agency tag campaigns without modifying the Google
Ads account. Add a staging model `stg_entity_segments` and join it in campaign-
level marts to expose `segment_label`.

**Option B — Remove for now.** If nobody is using it and the design is unclear,
remove it to reduce confusion and re-introduce it when there is a clear use case.

### Recommendation

Option A — keep it. Brand vs non-brand segmentation is almost always needed for
agency reporting. Document its purpose in the contract and wire it into
`mart_ads_campaign_daily` as an optional join.

---

## 8. Alert Thresholds Linkage

Status: `DEFERRED`

Defer alert threshold documentation until reports are live and the team has better
context on what alert types are needed. The current simple rule-based approach in
`mart_ads_alerts` is sufficient for phase 1.

When revisited, the alert contract should map each `threshold_key` in
`cfg_thresholds` to the alert type it drives.

---

## 9. Change Management And Versioning

Status: `PROPOSAL`

### Context

When a mart schema changes (column added, removed, renamed, type changed), the
HTML reporting app could break if it relies on specific column names.

### 9a. Non-Breaking Changes Policy

Define what is a non-breaking change:

- **Non-breaking:** adding a new column, adding a new mart, adding new rows
- **Breaking:** removing a column, renaming a column, changing a column type,
  changing the grain

Rule: Non-breaking changes can be deployed without notice. Breaking changes
require a deprecation period.

### 9b. Deprecation Protocol For Breaking Changes

When a breaking change is needed:

1. Add the new column/mart alongside the old one.
2. Mark the old column/mart as deprecated in the contract and in the dbt
   description (prefix with `[DEPRECATED]`).
3. Update the UI to use the new column/mart.
4. After one release cycle, remove the deprecated column/mart.

### 9c. dbt Model Contracts

Enable `contract: {enforced: true}` on all mart models. This makes dbt enforce
the column list and types at build time. If someone accidentally drops a column,
the build fails instead of silently breaking the UI.

Example in `_reporting__models.yml`:

```yaml
- name: mart_ads_overview_daily
  config:
    contract:
      enforced: true
  columns:
    - name: client_id
      data_type: string
    - name: account_id
      data_type: string
    # ...
```

### 9d. Schema Validation In CI

Add a CI step that compares the current mart schema against the contract. If a
column is missing or its type has changed, the CI pipeline fails. This can be
done with `dbt docs generate` + a schema diffing script, or with dbt model
contracts alone.

### Recommendation

Start with dbt model contracts (9c) — they provide schema enforcement with
minimal tooling. Add the deprecation protocol (9b) as a documented process.

---

## 10. Infrastructure Decisions

Status: `PROPOSAL`

### 10a. Scheduling (dbt Runs)

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| Cloud Scheduler + Cloud Run | Serverless, low cost, GCP-native | Manual setup, no built-in dbt UI |
| dbt Cloud | Built-in scheduling, UI, CI/CD | Additional SaaS cost |
| Cloud Composer (Airflow) | Powerful orchestration, handles complex DAGs | Heavy for a dbt-only workload |
| GitHub Actions on schedule | Simple, already using GitHub | Cold starts, limited run history |

**Recommendation:** Cloud Scheduler + Cloud Run for phase 1. It is serverless, cheap,
and keeps everything in GCP. The dbt run command is simple — no complex DAG
orchestration needed at this stage. Move to dbt Cloud or Composer only if
orchestration complexity grows (e.g., when GA4 and Shopify sources are added).

Proposed schedule:

- `dbt run` at 06:00 UTC daily (after the T-1 Google Ads data lands)
- `dbt test` immediately after
- `dbt source freshness` at 08:00 UTC as a separate check

### 10b. Environments

| Environment | GCP Project | Dataset Suffix | Purpose |
|-------------|-------------|----------------|---------|
| dev | `gads-export-all` | `_dev` | Individual developer work |
| staging | `gads-export-all` | `_staging` | CI validation, pre-prod |
| prod | `gads-export-all` | (none) | Live reporting data |

Use dbt targets to manage this:

```yaml
# profiles.yml
google_ads_extractor:
  target: dev
  outputs:
    dev:
      dataset: gads_reporting_mart_dev
    staging:
      dataset: gads_reporting_mart_staging
    prod:
      dataset: gads_reporting_mart
```

### 10c. Partitioning And Clustering

For cost control and query performance on BigQuery:

| Mart | Partition Column | Cluster Columns |
|------|-----------------|-----------------|
| `mart_ads_overview_daily` | `report_date` | `client_id, account_id` |
| `mart_ads_overview_monthly` | `report_month` | `client_id, account_id` |
| `mart_ads_campaign_daily` | `report_date` | `client_id, account_id` |
| `mart_ads_keyword_audit_detail` | — | `client_id, account_id` |
| `mart_ads_budget_exhaustion` | `report_date` | `client_id, account_id` |
| `mart_ads_adgroup_daypart` | — | `client_id, account_id` |
| `mart_ads_search_terms` | `report_date` (after adding it) | `client_id, account_id` |
| `mart_ads_alerts` | `report_date` | `client_id, account_id` |

Configure in dbt:

```yaml
models:
  google_ads_extractor:
    marts:
      +materialized: table
      +partition_by:
        field: report_date
        data_type: date
      +cluster_by: ['client_id', 'account_id']
```

Override per-model where the partition column differs or doesn't exist.

### 10d. Monitoring And Alerting

| Layer | Tool | What It Watches |
|-------|------|-----------------|
| Pipeline | Cloud Monitoring | Cloud Run job failures, timeouts |
| Data quality | dbt test | Grain violations, null checks, accepted values |
| Data freshness | dbt source freshness | Stale raw tables |
| Cost | BigQuery billing alerts | Unexpected query cost spikes |

For phase 1, set up email alerts on Cloud Run job failures and BigQuery
billing thresholds. More sophisticated monitoring (Slack alerts, PagerDuty)
can be added later.

### 10e. Backfill Strategy

When raw data is corrected retroactively:

- Staging views automatically reflect changes (they are views, not tables).
- Mart tables require a `dbt run --full-refresh` for the affected models.
- For targeted backfills, use `dbt run --select mart_ads_overview_daily`
  with `--full-refresh` on just the affected mart.

Document a runbook for common backfill scenarios:

1. **New account added:** `dbt seed --full-refresh` + `dbt run --full-refresh`
2. **Raw data corrected for specific dates:** `dbt run --full-refresh --select` affected marts
3. **Exchange rate updated:** `dbt seed --full-refresh` for `cfg_exchange_rates` + `dbt run --full-refresh` for all marts with currency columns

---

## Summary: Priority Ranking

| # | Proposal | Priority | Phase |
|---|----------|----------|-------|
| 3 | Currency handling | High | Phase 1 |
| 6 | Ad-level reporting | High | Phase 1 |
| 1 | client_id on all grains | High | Phase 1 |
| 2 | Date ranges on search/keyword | High | Phase 1 |
| 9c | dbt model contracts | High | Phase 1 |
| 4 | Data freshness | Medium | Phase 1 |
| 10c | Partitioning and clustering | Medium | Phase 1 |
| 10a | Scheduling | Medium | Phase 1 |
| 10b | Environments | Medium | Phase 1 |
| 7 | cfg_segments purpose | Medium | Phase 1 |
| 5 | Client data isolation | Medium | Phase 1 (app-level) |
| 9b | Deprecation protocol | Low | Phase 1 (document only) |
| 10d | Monitoring | Low | Phase 1 (basic) |
| 10e | Backfill runbook | Low | Phase 1 (document only) |
| 8 | Alert thresholds | Deferred | Phase 2 |
