# Codebase Assessment

Date: 2026-04-13

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Data warehouse | Google BigQuery | — |
| Data modelling | dbt-bigquery | 1.11.1 |
| Application | FastAPI + Jinja2 | 0.118.0 |
| ASGI server | Uvicorn | 0.37.0 |
| Auth | Google OAuth 2.0 + itsdangerous sessions | — |
| Infra | Cloud Run Jobs + Cloud Scheduler | — |
| Container | Python 3.12-slim Docker image | — |
| Testing | pytest + dbt tests | — |

## Repository Structure

```
.
├── app/                    # FastAPI reporting application
│   ├── main.py             # Routes, middleware, auth endpoints
│   ├── service.py          # BigQueryReportingService (2984 lines)
│   ├── auth.py             # Google OAuth + session management
│   ├── cache.py            # TTL in-process cache
│   ├── settings.py         # Env-driven config dataclass
│   ├── templates/          # Jinja2 HTML templates (hub, report_page, denied, base)
│   └── static/             # CSS + JS (reporting.css, reporting.js ~4900 lines)
├── models/
│   ├── staging/
│   │   ├── google_ads/     # 15 staging models + schema YAML
│   │   └── manual/         # 1 auction insights stub
│   └── marts/reporting/    # 14 mart models + schema YAML
├── seeds/                  # 5 config CSVs (accounts, groups, thresholds, FX, segments)
├── macros/                 # generate_schema_name (dev/stage/prod routing)
├── orchestration/          # Release pipeline Python modules
│   ├── release_orchestrator.py
│   ├── raw_freshness.py
│   ├── dbt_cli.py
│   ├── schema_mapping.py
│   └── logging_utils.py
├── scripts/                # Shell entry points + SQL bootstrap
├── deploy/cloud_run/       # Cloud Run Job + Scheduler deploy scripts
├── profiles/               # dbt profiles (dev, stage, prod)
├── tests/unit/             # 5 Python test modules
├── tests/                  # 8 dbt SQL grain tests + 1 FX coverage test
└── docs/                   # Design contracts and specifications
```

## Architecture Pattern

The project follows a layered analytics architecture:

1. **Raw layer** (`gads_raw`): Immutable Google Ads Data Transfer tables (`p_ads_*`). 13 raw table families covering account, campaign, ad group, keyword, ad, budget, and search query stats plus dimensions.
2. **Config layer** (`gads_reporting_cfg`): dbt seeds for accounts, thresholds, FX rates, segments, account groups. Plus a manually-managed `cfg_app_users` table for auth.
3. **Staging layer** (`gads_reporting_stg`): 16 dbt views standardising raw tables — cost micros → currency, deduplication of dimension snapshots, safe metric calculations.
4. **Mart layer** (`gads_reporting_mart`): 14 dbt tables with enforced contracts — daily/monthly/hourly aggregations, keyword audit, budget exhaustion, alerts, data freshness.
5. **Application layer** (`app/`): Thin FastAPI service reading from marts. 10+ report pages, management hub, Google OAuth, TTL caching, client-side sort/search/filter.
6. **Orchestration layer** (`orchestration/`): 8-step release pipeline — freshness gate → seed bootstrap → stage build → stage test → prod build → prod test.
7. **Infrastructure layer** (`deploy/`): Cloud Run Job for the orchestrator, Cloud Scheduler for daily triggers.

## Reusable Patterns

- **safe_divide / safe_multiply**: All metric calculations guard against division by zero.
- **Dual-currency reporting**: Every monetary field exists in `_original` and `_eur` variants. Daily FX rates applied at staging; latest FX rate fallback at mart level.
- **Dimension deduplication**: `row_number() over (partition by ... order by _data_load_timestamp desc)` picks latest dimension snapshot.
- **Contract enforcement**: All mart models have `contract: enforced: true` in dbt_project.yml — column names, types, and not-null constraints are validated at build time.
- **Schema routing macro**: Single `generate_schema_name` macro routes models to correct datasets across dev/stage/prod without code changes.
- **Feature flags**: `has_auction_insights` and `has_ga4` on `cfg_accounts` control which report pages are visible per account.
- **Structured logging**: JSON-formatted stdout logs throughout orchestration for Cloud Run observability.

## Test Coverage

| Category | Count | Description |
|----------|-------|-------------|
| dbt schema tests | ~100+ | not_null, unique, relationships, accepted_values across all models |
| dbt grain tests | 8 | Uniqueness assertions on composite keys for critical marts |
| dbt data tests | 1 | Currency coverage (active accounts vs FX rates) |
| Python unit tests | 5 modules | Orchestration, schema mapping, app routes/API, caching, freshness |
| Validation scripts | 2 | `dbt_validate.sh` (full pipeline) and `runtime_validate.sh` (unit + CLI) |

Last verified: all 151 dbt tests passing.

## Code Quality Notes

- Well-separated concerns: SQL for business logic, Python for orchestration/serving, YAML for contracts.
- Consistent naming conventions: `stg_` prefix for staging, `mart_` prefix for marts, `cfg_` for config.
- Design contracts documented before implementation in `docs/`.
- No duplicated business logic between dbt and Python — the app layer is intentionally thin.
- GA4 reporting is siloed from Ads reporting (separate query logic in service.py, not in dbt marts).
