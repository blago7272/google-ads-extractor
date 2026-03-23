# First Report App

## Scope

The first application layer is a thin FastAPI service over the verified BigQuery marts.

It intentionally does not recreate reporting logic in Python. BigQuery remains the source of truth for:

- KPI computation
- period aggregation
- keyword audit classification
- alert generation

The app is responsible for:

- client, account, and date filters
- interactive rendering
- client-side sorting
- client-side text search
- visual layout

## Implemented Views

Single dashboard page with:

- KPI card row with previous-period deltas
- daily trend chart
- campaign explorer table
- keyword audit table
- alerts table
- search terms table

## API Surface

- `GET /`
  HTML dashboard shell
- `GET /healthz`
  lightweight app health check
- `GET /api/options`
  active accounts and global date bounds
- `GET /api/dashboard`
  bundled dashboard payload for the selected scope

## Query Sources

- `mart_ads_overview_daily`
- `mart_ads_campaign_daily`
- `mart_ads_keyword_audit_detail`
- `mart_ads_search_terms`
- `mart_ads_alerts`

## Local Run

```bash
source .venv/bin/activate
./scripts/run_reporting_app.sh
```

Open `http://127.0.0.1:8000`.

## Next Additions

- budget exhaustion panel
- ad-level explorer
- CSV export endpoints
- report routing by page instead of one dashboard
- Cloud Run service packaging for the app layer
