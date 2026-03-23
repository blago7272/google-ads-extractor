# Infrastructure Design

This document defines the recommended environment, dataset, deployment, and storage strategy for the BigQuery and dbt reporting stack.

## Goals

- keep production reporting stable and auditable
- allow safe staging and local development without polluting prod datasets
- keep dataset naming explicit
- avoid unnecessary GCP project sprawl in phase 1

## Recommended Environment Model

Use three logical environments:

- `dev`
- `stage`
- `prod`

Use one GCP project in phase 1 unless security or billing isolation requires more:

- project: `gads-export-all`

Rationale:

- the raw Google Ads export already lives there
- the current dbt profile already points there
- the team gets faster delivery by separating environments at the dataset layer first

## Dataset Naming Strategy

Keep environment names explicit in the dataset names.

Production datasets:

- `gads_reporting_cfg`
- `gads_reporting_stg`
- `gads_reporting_mart`

Stage datasets:

- `gads_reporting_cfg_stage`
- `gads_reporting_stg_stage`
- `gads_reporting_mart_stage`

Developer datasets:

- `gads_reporting_cfg_dev_<owner>`
- `gads_reporting_stg_dev_<owner>`
- `gads_reporting_mart_dev_<owner>`

Rules:

- do not rely on hidden or implicit schema suffixing
- dataset names must show the environment directly
- prod keeps the current unsuffixed names to avoid breaking existing references

## Raw Data Strategy

Raw source stays shared and read-only:

- dataset: `gads_raw`

Phase-1 rule:

- `dev`, `stage`, and `prod` all read the same raw source
- only reporting datasets vary by environment

Future option:

- if a non-prod import pipeline is introduced later, add `gads_raw_stage`
- do not block the reporting rollout on that change

## dbt Target Strategy

Use explicit dbt targets:

- `dev`
- `stage`
- `prod`

Recommended behavior:

- `dev` writes to personal `*_dev_<owner>` datasets
- `stage` writes to shared `*_stage` datasets
- `prod` writes to current production datasets

Implementation direction:

- keep model-level schemas explicit
- map target name to exact dataset names
- preserve the current guarantee that dbt never writes to an accidental default schema

## Deployment Pattern

Recommended runtime:

- containerized dbt job on `Cloud Run Jobs`

Recommended triggers:

- `Cloud Scheduler` for recurring runs
- manual trigger for hotfixes and backfills

Why this pattern:

- simpler than Composer for the current scope
- good enough for one dbt project and a few scheduled jobs
- easy to monitor with Cloud Logging and Cloud Monitoring

## Service Accounts

Recommended service accounts:

- `dbt-runner`
- `reporting-app`

`dbt-runner` permissions:

- read `gads_raw`
- read and write `gads_reporting_cfg*`
- read and write `gads_reporting_stg*`
- read and write `gads_reporting_mart*`
- create BigQuery jobs
- write logs and metrics

`reporting-app` permissions:

- read `gads_reporting_mart*`
- read `gads_reporting_cfg*` when needed for labels and account metadata
- no write access to reporting datasets
- no access to `gads_raw`

## Storage And Materialization Strategy

Current phase-1 approach:

- staging models remain views
- marts remain tables
- daily builds can still use full refresh while volume is manageable

Next scaling threshold:

- move the largest daily marts to incremental partitioned tables first

Priority candidates:

- `mart_ads_search_terms`
- `mart_ads_ad_performance_daily`
- `mart_ads_campaign_daily`
- `mart_ads_budget_exhaustion`

## Partitioning And Clustering

Recommended production table settings:

### Partition By Date

- `mart_ads_overview_daily` by `report_date`
- `mart_ads_campaign_daily` by `report_date`
- `mart_ads_budget_exhaustion` by `report_date`
- `mart_ads_search_terms` by `report_date`
- `mart_ads_ad_performance_daily` by `report_date`

### Partition By Month

- `mart_ads_overview_monthly` by `report_month`

### Not Partitioned In Phase 1

- `mart_ads_keyword_audit_detail`
- `mart_ads_adgroup_daypart`
- `mart_ads_alerts`
- `mart_ads_auction_insights_monthly`

### Recommended Clustering

- `mart_ads_overview_daily`: `client_id`, `account_id`
- `mart_ads_campaign_daily`: `client_id`, `account_id`, `campaign_id`
- `mart_ads_budget_exhaustion`: `client_id`, `account_id`, `campaign_id`
- `mart_ads_search_terms`: `client_id`, `account_id`, `campaign_id`, `ad_group_id`
- `mart_ads_ad_performance_daily`: `client_id`, `account_id`, `campaign_id`, `ad_group_id`

Rationale:

- partition pruning controls date-scan cost
- clustering keeps common app filters efficient

## Promotion Flow

Recommended release path:

1. local development in `*_dev_<owner>`
2. merge to `main`
3. deploy to `stage`
4. run stage build and tests
5. promote the same container/image revision to `prod`

Rules:

- prod deploys should only use code already validated in stage
- do not edit prod datasets manually
- schema changes must go through git and dbt

## Secrets And Config

Keep runtime config outside the repo:

- dbt profile credentials
- target selection
- scheduler parameters
- alert routing

Keep reporting config inside the repo or seeded BigQuery tables:

- account registry
- thresholds
- exchange-rate seed
- segmentation labels

## Phase-1 Non-Goals

- separate GCP projects per environment
- non-prod raw imports
- row-level security in BigQuery
- asset-level RSA storage model

## Decision Summary

- one GCP project for phase 1
- explicit per-environment datasets
- `Cloud Run Jobs` plus `Cloud Scheduler`
- staging as views, marts as tables
- partition and cluster only the higher-volume marts first
