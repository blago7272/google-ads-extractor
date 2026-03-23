# Google Ads Extractor

Ads-only reporting scaffold on top of the existing BigQuery Google Ads raw export.

This repo is structured around a shared multi-account reporting model:

- raw source dataset stays immutable
- config and thresholds live in seeds
- staging models standardize transfer tables
- mart models drive the HTML reporting layer

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

- overview
- daily trends
- campaign explorer
- keyword audit
- search terms
- budget exhaustion
- ad group daypart profile
- alerts

## Project Layout

```text
.
├── docs
├── macros
├── models
│   ├── marts
│   │   └── reporting
│   └── staging
│       ├── google_ads
│       └── manual
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

Validation details and the last verified results are tracked in `docs/verification.md`.

## Design Docs

- `docs/reporting_contract.md`
- `docs/contracts.md`
- `docs/infrastructure_design.md`
- `docs/operations_design.md`
