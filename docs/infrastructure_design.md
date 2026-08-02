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
- keep the release entrypoint target-aware so the same container can execute `stage` and then `prod` without rebuilding an image

## Deployment Pattern

Recommended runtime:

- containerized dbt job on `Cloud Run Jobs`

Recommended triggers:

- `Cloud Scheduler` for the daily release window
- manual trigger for hotfixes and backfills

Why this pattern:

- simpler than Composer for the current scope
- good enough for one dbt project and a few scheduled jobs
- easy to monitor with Cloud Logging and Cloud Monitoring

Phase-1 release orchestration:

- `Cloud Scheduler` triggers one `reporting-release-orchestrator` `Cloud Run Job`
- the orchestrator runs the release phases sequentially in one invocation:
  1. raw freshness probe
  2. skipped-account alerting (diff vs previous run)
  3. ECB exchange rate refresh (fetches latest daily rates from ECB API)
  4. `dbt run` in `prod`
  5. `dbt test` in `prod`
- stage is no longer on the daily path. It is a validation gate for *code* changes,
  run with `--include-stage` (stage then prod) or `--skip-prod` (stage only), and the
  daily refresh goes straight to prod with `dbt test` in prod as the gate.
  See `docs/pipeline_cost_optimizations.md`.
- the job exits on the first failing gate
- prod never starts from a separate fixed scheduler entry

Why a single orchestrator first:

- it guarantees prod cannot race ahead of stage
- it keeps phase-1 operations simpler than introducing `Cloud Workflows`
- it still allows manual reruns of individual steps when debugging

Future option:

- if step-level retries or parallel branches become necessary, move orchestration to `Cloud Workflows` without changing the release contract

## Container Image Versioning

Recommended image registry:

- `Artifact Registry`

Tagging rules:

- tag every deployable image with the git commit SHA
- never use `:latest` for scheduled stage or prod releases
- the same SHA-tagged image revision must run both the stage and prod phases inside a single orchestrated release

Rationale:

- it makes the stage-to-prod promotion auditable
- it keeps alert payloads and logs traceable back to a git revision

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
- execute the raw freshness probe query before `dbt`
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
3. build one SHA-tagged container image
4. schedule or manually trigger the `reporting-release-orchestrator`
5. run raw freshness gate
6. run stage build and tests
7. promote the same container or image revision to prod inside the same orchestrated release

Rules:

- prod deploys should only use code already validated in stage
- do not edit prod datasets manually
- schema changes must go through git and dbt
- raw freshness is a precondition for both stage and prod release execution

## Raw Freshness Infrastructure Contract

Phase-1 implementation:

- use a custom BigQuery probe against `gads_raw.p_ads_AccountStats_*`
- resolve active account scope from `gads_reporting_cfg.cfg_accounts`
- emit structured results to `Cloud Logging`

Why this is not `dbt source freshness` in phase 1:

- the raw tables are wildcarded by transfer suffix
- release gating depends on active-account coverage, not only on table timestamps
- the freshness decision must happen before `dbt run`

User-facing freshness surface:

- keep `mart_data_freshness` in the reporting mart layer for post-build visibility
- do not make the app depend directly on pre-build operational logs

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
- `Cloud Scheduler` triggers one orchestrated `Cloud Run Job` for the daily release
- raw freshness is a pre-`dbt` BigQuery gate, not a placeholder fixed-time job
- `Artifact Registry` plus SHA-tagged images define the promoted release revision
- staging as views, marts as tables
- partition and cluster only the higher-volume marts first
