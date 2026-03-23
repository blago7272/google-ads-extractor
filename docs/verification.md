# Verification

## Environment

- Python: `3.12`
- dbt-bigquery: `1.11.1`
- profile: `~/.dbt/profiles.yml`
- target project: `gads-export-all`
- location: `EU`

## Verified Commands

```bash
source .venv/bin/activate
dbt debug
dbt seed --full-refresh
dbt run --select path:models/staging/google_ads path:models/staging/manual
dbt run --full-refresh --select path:models/marts/reporting
dbt test
```

## Last Verified Result

Verified in this workspace on `2026-03-24`.

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `151/151` tests passed

## Runtime Verification

Verified operational scaffolding in this workspace on `2026-03-24`.

- `./scripts/runtime_validate.sh`: passed
- `python scripts/raw_freshness_check.py --execution-ts 2026-03-23T12:00:00Z --verbose`: passed for the active pilot account
- `python scripts/release_orchestrator.py --execution-ts 2026-03-23T12:00:00Z --stop-after-step raw_freshness_gate --skip-prod`: passed
- `DBT_PROFILES_DIR=profiles dbt debug --target stage`: passed
- `DBT_PROFILES_DIR=profiles dbt debug --target prod`: passed
- `DBT_PROFILES_DIR=profiles dbt run --target stage --full-refresh --select stg_auction_insights mart_ads_auction_insights_monthly`: passed and confirmed target-aware stage schemas
- `python scripts/release_orchestrator.py --execution-ts 2026-03-23T12:00:00Z --dbt-profiles-dir profiles --skip-prod`: passed with automatic stage seed bootstrap

Stage orchestrator run result:

- raw freshness gate: passed
- stage seed bootstrap: passed and created `gads_reporting_cfg_stage`
- stage build: passed
- stage test: `151/151` tests passed
- prod build: intentionally skipped

## GCP Deployment Verification

Verified deployment in project `gads-export-all` on `2026-03-24`.

- enabled APIs: `run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`, `cloudscheduler.googleapis.com`, `iam.googleapis.com`
- Artifact Registry repository: `europe-west1-docker.pkg.dev/gads-export-all/reporting`
- deployed image: `europe-west1-docker.pkg.dev/gads-export-all/reporting/release-orchestrator:b8c9592`
- Cloud Run Job: `reporting-release-orchestrator`
- region: `europe-west1`
- runtime service account: `dbt-runner@gads-export-all.iam.gserviceaccount.com`
- scheduler service account: `scheduler-invoker@gads-export-all.iam.gserviceaccount.com`
- Cloud Scheduler job: `reporting-release-orchestrator-daily`
- schedule: `30 6 * * *`
- time zone: `Europe/Sofia`

Verified Cloud Run execution:

- execution id: `reporting-release-orchestrator-q6b5z`
- args: `scripts/release_orchestrator.py --execution-ts=2026-03-23T12:00:00Z --skip-prod`
- start time: `2026-03-23T23:02:18.192438Z`
- completion time: `2026-03-23T23:04:56.720087Z`
- Cloud Run execution result: completed successfully in `2m38.52s`

Verified deployed runtime behavior:

- raw freshness gate: passed
- stage build: passed
- stage test: passed
- release completed: passed
- prod release: intentionally skipped for deployment verification

Operational note:

- A default run at verification time would have failed the raw freshness gate because the latest raw import was still `2026-03-22` while a real-time execution expected `2026-03-23`.
- `gcloud run jobs execute ... --args` on the installed SDK version emitted an invalid `priorityTier` override payload for this job type.
- Manual verification was executed successfully via the Cloud Run Jobs REST `:run` endpoint with container arg overrides instead.

## Report App Verification

Verified the first report application layer in this workspace on `2026-03-24`.

- `python -m compileall app`: passed
- `python -m pytest tests/unit/test_reporting_app.py tests/unit/test_raw_freshness.py tests/unit/test_schema_mapping.py tests/unit/test_release_orchestrator.py`: `14/14` passed
- direct `BigQueryReportingService.get_filter_options()`: passed
- direct `BigQueryReportingService.get_dashboard_data(...)`: passed
- local `uvicorn` app startup: passed on `http://127.0.0.1:8000`
- `GET /healthz`: passed
- `GET /api/options`: passed
- `GET /api/dashboard`: passed
- `GET /`: passed

Verified live preview payload against `gads-export-all`:

- default preview range: `2026-02-21` through `2026-03-22`
- trend points returned: `30`
- campaign rows returned: `10`
- keyword rows returned: `121`
- search term rows returned: `250`
- alert rows returned: `50`
- summary spend: `6952.132867999999 EUR`

## Current Mart Row Counts

- `mart_ads_overview_daily`: `201`
- `mart_ads_overview_monthly`: `7`
- `mart_ads_campaign_daily`: `1086`
- `mart_ads_keyword_audit_detail`: `149`
- `mart_ads_search_terms`: `86292`
- `mart_ads_budget_exhaustion`: `1086`
- `mart_ads_adgroup_daypart`: `72`
- `mart_ads_alerts`: `115`
- `mart_ads_ad_performance_daily`: `6574`

## Issues Found And Fixed During Verification

1. Seed CSVs had an extra trailing blank line, which caused BigQuery seed loads to fail. Fixed by normalizing the files to a single trailing newline.
2. Generic dbt tests used deprecated top-level arguments. Fixed by moving arguments under the `arguments` key.
3. The mart layer initially included every raw account. Fixed by filtering marts to configured active accounts only.
4. `stg_search_query_stats_daily` contained at least one null `search_term`. Fixed by filtering null search terms in staging to preserve the contract.
5. The placeholder auction insights model used a `WHERE` clause without a `FROM`. Fixed with a compile-safe empty-select stub.
6. Correlated FX lookup subqueries were rejected by BigQuery in mart builds. Fixed by introducing `stg_account_fx_rates_daily` and `stg_exchange_rates_latest` and joining them explicitly.
7. `mart_ads_adgroup_daypart` initially grouped on a derived daypart without grouping the underlying expression correctly. Fixed by grouping on the `daypart` output.
8. `mart_ads_search_terms` initially duplicated daily rows because Google Ads emitted multiple `search_term_match_type` values within the same search-term grain. Fixed by collapsing those rows and emitting `MULTIPLE` when the mart grain contains mixed status or match-type values.
9. The original schema macro still routed `stage` targets into prod datasets. Fixed by making schema generation target-aware for `dev`, `stage`, and `prod`.
10. A fresh `stage` environment initially failed because target-specific config seeds were missing. Fixed by adding automatic seed bootstrap in the release orchestrator when `cfg_*` tables are absent in the target dataset.
