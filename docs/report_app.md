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
- page visibility based on account feature flags from `cfg_accounts`

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
- `GA4 Overview`
  Standalone commerce KPIs, source/campaign mix, product leaders, and monthly channel share from the GA4 historical export, with brand restored from GA4 view-side item rows and category restored from ERP item mapping.
- `GA4 Impact`
  Standalone source/campaign impact on products, categories, and brands.
- `GA4 Funnel`
  Standalone views, add-to-cart, and purchase progression by channel and source.
- `GA4 Timing`
  Standalone hourly performance and date-by-hour matrices from the GA4 historical export.

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

The GA4 scope is now documented separately in `docs/ga4_reporting_contract.md`. Items still deferred are the blended Ads + GA4 sheets and any landing-page/session-based analysis not present in the current GA4 source.

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
  HTML report shell for Ads, Auction, and GA4 report pages
- `GET /healthz`
  lightweight app health check
- `GET /api/options`
  active accounts, global date bounds, and account-level feature flags
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
- `experimental-clients.sexwell_analyses.gads--impression_share--daily`
- `experimental-clients.sexwell_analyses.gads--impression_share--weekly`
- `experimental-clients.sexwell_analyses.gads--impression_share--monthly`
- `experimental-clients.sexwell_analyses.GA4-345365542--historical`

## Feature Flags

Page visibility is controlled from `cfg_accounts`.

- `has_ga4`
  controls whether GA4 report pages appear in the navigation for the selected scope
- `has_auction_insights`
  controls whether the auction insights page appears in the navigation for the selected scope

Rules:

- if a specific account is selected, the app uses that account's flags
- if a client is selected with no specific account, the app enables a feature when any active account under that client has it
- if no client or account is selected, the app enables a feature when any active account in the current options payload has it

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

## Hosting Reference

Stable hosted deployment, access control, and subdomain setup are defined in:

- `docs/report_hosting_contract.md`
