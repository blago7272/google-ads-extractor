# Google Ads Extractor

Ads-only reporting scaffold on top of the existing BigQuery Google Ads raw export.

This repo is structured around a shared multi-account reporting model:

- raw source dataset stays immutable
- config and thresholds live in seeds
- staging models standardize transfer tables
- mart models drive the HTML reporting layer
- a small Python runtime orchestrates release gating and dbt promotion

## Proposed BigQuery Datasets

- `gads_raw`
  Existing Google Ads transfer tables. Do not modify.
- `gads_reporting_cfg`
  Seeded config tables such as accounts, thresholds, and account groups.
- `gads_reporting_stg`
  Standardized views over the raw transfer tables.
- `gads_reporting_mart`
  Precomputed reporting tables for the app.
- `gads_manual`
  Optional manual uploads such as auction insights if they are not present in the transfer.

## First Ads-Only Modules

- management hub
- overview
- daily trends
- campaign explorer
- keyword audit
- search terms
- budget exhaustion
- hourly performance
- weekday profile
- ad group daypart profile
- alerts
- first interactive report app

## Project Layout

```text
.
├── deploy
├── docs
├── macros
├── models
│   ├── marts
│   │   └── reporting
│   └── staging
│       ├── google_ads
│       └── manual
├── orchestration
├── profiles
├── scripts
└── seeds
```

## Notes

- The reporting model is shared across all clients. Every reporting table carries `client_id`, `account_id`, and `report_date`.
- Client-specific differences belong in config tables or staging adapters, not duplicated datasets and not frontend logic.
- The eventual HTML layer should read from `gads_reporting_mart`, not from raw transfer tables.

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp profiles.example.yml ~/.dbt/profiles.yml
dbt debug
```

## Validation

Run the repeatable validation flow with:

```bash
./scripts/dbt_validate.sh
```

Validate the operational runtime with:

```bash
./scripts/runtime_validate.sh
```

Validation details and the last verified results are tracked in `docs/verification.md`.

## First Report App

The first application layer lives in `app/` and reads directly from `gads_reporting_mart`.

It currently includes:

- shared client/account/date filters
- management hub with conclusions and drilldown links
- overview page with KPI summary, trend, campaigns, and competition
- keyword and query audit page
- timing page with time-of-day, day-of-week, ad-group daypart, and budget pacing
- action queue page

Run it locally with:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_reporting_app.sh
```

Then open `http://127.0.0.1:8000`.

## Operational Runtime

- `scripts/raw_freshness_check.py`
  Manual raw-import gate against active accounts in `cfg_accounts`.
- `scripts/release_orchestrator.py`
  Runs raw freshness, stage build, stage tests, prod build, and prod tests in order.
  It also bootstraps missing config seeds in the target environment on first run.
- `profiles/profiles.yml`
  dbt profile template for `dev`, `stage`, and `prod` targets.
- `deploy/cloud_run/deploy_release_orchestrator.sh`
  Deploys the orchestrator as a `Cloud Run Job`.
- `deploy/cloud_run/create_release_scheduler.sh`
  Creates the daily `Cloud Scheduler` trigger against the Cloud Run Jobs API.

## Design Docs

- `docs/reporting_contract.md`
- `docs/contracts.md`
- `docs/report_app.md`
- `docs/infrastructure_design.md`
- `docs/operations_design.md`
