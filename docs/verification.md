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
