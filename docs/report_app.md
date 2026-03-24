# Report App

## Scope

The application layer is a thin FastAPI service over the verified BigQuery marts.

It intentionally does not recreate reporting logic in Python. BigQuery remains the source of truth for:

- KPI computation
- period aggregation
- keyword audit classification
- alert generation
- timing analysis rollups

The app is responsible for:

- report routing
- client, account, and date filters
- short-lived response caching
- interactive rendering
- client-side sorting
- client-side text search
- visual layout

## Implemented Views

- `Hub`
  Management-level conclusions, status blocks, recent trend, top alerts, and drilldown links.
- `High-Level Overview`
  KPI row, executive status blocks, trend curve, campaign explorer, and auction snapshot.
- `Keyword and Query Audit`
  Keyword issues, search terms, keyword-specific alerts, regex filtering, and numeric search-term filters.
- `Timing Analysis`
  Hour-of-day, day-of-week, daypart summary, ad-group timing profile, budget pacing, and switchable timing metrics.
- `Action Queue`
  Consolidated alerts and budget flags.

## Excel Alignment

The current app structure intentionally pulls from the original workbook patterns:

- `Обозр_акаунт`
  Recast as the management hub plus the high-level overview page.
- `Резюме_Одит`
  Partly represented by the management conclusions and trend framing.
- `Ключови_Думи` and `Keyword_Одит`
  Recast as the keyword and query audit page.
- `Бюджет_Лимит`, `Резюме_часови_анализ`, and `Профил_по_групи`
  Recast as the timing page.

Items still deferred from the workbook are the blended GA4 and ecommerce sheets.

## Usability Refinements

The current app layer also includes:

- filtered summary rows above all table bodies
- regex search on the keyword-audit table
- search-term threshold filters for conversions, spend, and ROAS
- keyword-page alerts narrowed to `keyword_issue` items
- timing-chart metric switches for conversion value, spend, ROAS, and conversions
- explicit explanation text for budget-exhaustion flags

## API Surface

- `GET /`
  HTML hub shell
- `GET /reports/{report_name}`
  HTML report shell for `overview`, `keywords`, `timing`, or `alerts`
- `GET /healthz`
  lightweight app health check
- `GET /api/options`
  active accounts and global date bounds
- `GET /api/hub`
  bundled management-hub payload for the selected scope
- `GET /api/reports/{report_name}`
  report-specific payload for the selected scope
- `GET /api/dashboard`
  compatibility alias that returns the overview payload

## Query Sources

- `mart_ads_overview_daily`
- `mart_ads_campaign_daily`
- `mart_ads_hourly_performance_daily`
- `mart_ads_keyword_audit_detail`
- `mart_ads_search_terms`
- `mart_ads_budget_exhaustion`
- `mart_ads_adgroup_daypart`
- `mart_ads_alerts`
- `mart_ads_auction_insights_monthly`

## Performance

The app now uses an in-process TTL cache for:

- filter options
- scope-level BigQuery query results shared across hub and detail pages

Relevant environment knobs:

- `REPORTING_OPTIONS_CACHE_TTL_SECONDS`
  default `3600`
- `REPORTING_QUERY_CACHE_TTL_SECONDS`
  default `900`
- `REPORTING_QUERY_CACHE_MAX_ENTRIES`
  default `256`

This keeps the first request BigQuery-backed, while repeated loads and drilldowns within the same filter scope stay fast.

## Local Run

```bash
source .venv/bin/activate
./scripts/run_reporting_app.sh
```

Open `http://127.0.0.1:8000`.

## Next Additions

- ad-level explorer
- date-by-hour heatmap
- weekday and hour benchmarks versus the previous window
- CSV export endpoints
- Cloud Run service packaging for the app layer
