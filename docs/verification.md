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

Verified in this workspace on `2026-03-23`.

- `dbt debug`: passed
- `dbt seed --full-refresh`: passed
- staging build: passed
- mart build: passed
- `dbt test`: `87/87` tests passed

## Issues Found And Fixed During Verification

1. Seed CSVs had an extra trailing blank line, which caused BigQuery seed loads to fail. Fixed by normalizing the files to a single trailing newline.
2. Generic dbt tests used deprecated top-level arguments. Fixed by moving arguments under the `arguments` key.
3. The mart layer initially included every raw account. Fixed by filtering marts to configured active accounts only.
4. `stg_search_query_stats_daily` contained at least one null `search_term`. Fixed by filtering null search terms in staging to preserve the contract.
5. The placeholder auction insights model used a `WHERE` clause without a `FROM`. Fixed with a compile-safe empty-select stub.

