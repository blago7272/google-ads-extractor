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
- client, account, and date filters, including calendar presets
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
  Keyword issues, search terms, keyword-specific alerts, regex filtering, issue-type filtering, and numeric search-term filters.
- `Timing Analysis`
  Hour-of-day, day-of-week, date-by-hour timing matrix, daypart summary, ad-group timing profile, budget pacing, and switchable timing metrics.
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

Items still deferred are the blended Ads + GA4 sheets and any landing-page/session-based analysis.

A client may also have its own reporting app next to its Google Ads reporting here. Two deployment-level settings support that without client-specific code (see "Client Reporting Homes" below). The source-local GA4 and Auction Insights pages were removed in September 2026: they read one client's external dataset regardless of the selected client scope.

Persistent help-note content is documented in `docs/report_help_contract.md`.

Pending implementation work is tracked in `docs/report_backlog_contract.md`.

## Usability Refinements

The current app layer also includes:

- compact table mode by default across reports: first `10` rows visible, internal scroll for longer result sets, and `Expand all` only when needed
- filtered summary rows above all table bodies
- shared filter-shell date presets for `Last 7 days`, `Last 14 days`, `Last 30 days`, `Current month`, `Past month`, and `Year-to-date`, anchored to the latest available date in the current scope
- ISO date inputs and rendered date labels in `YYYY-MM-DD`
- ID Consult brand shell with the official logo, `Raleway` headings, `Roboto` body text, and the live-site purple palette, without changing report behavior
- regex search on the keyword-audit table
- issue-type dropdown filtering and footer row counts on the keyword-audit table
- search-term threshold filters for conversions, spend, and ROAS
- keyword-page alerts narrowed to `keyword_issue` items
- timing-chart metric switches for conversion value, spend, ROAS, and conversions
- timing date-by-hour matrix with a separate recent-window selector, defaulting to `7` days and extending with internal scroll
- explicit explanation text for budget-exhaustion flags
- shared reporting-freshness badge and warning banner for the selected account

## API Surface

- `GET /` and `GET /ads`
  HTML hub shell
- `GET /reports/{report_name}`
  HTML report shell for the Ads report pages
- `GET /healthz`
  lightweight app health check
- `GET /api/options`
  active accounts, global date bounds, and account-level feature flags
- `GET /api/hub`
  bundled management-hub payload for the selected scope
- `GET /api/freshness`
  lightweight freshness payload for the currently selected account
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
- `mart_data_freshness`
- `mart_ads_auction_insights_monthly`

## Feature Flags

Page visibility is controlled from `cfg_accounts`.

- `has_auction_insights`
  controls whether the auction insights page appears in the navigation for the selected scope

## Client Reporting Homes

Some clients have their own reporting app elsewhere. This app supports that with configuration only; no client names appear in the code.

- `cfg_accounts.client_home_url` (optional, http(s))
  When the selected client has one, the navigation shows a "Client home" link to it. Clients without one get no link. All of a client's accounts should carry the same URL; if they disagree, no link is shown. The app reads the column defensively, so a deployed `cfg_accounts` that predates it just means no links until the seed is applied.
- `MOVED_PATHS_JSON` (environment variable, optional)
  Pages that moved to another host. The value is a JSON object mapping a bare origin to the paths that moved there, and a trailing `*` marks a prefix: `{"https://reports.client.example": ["/clients/client-a", "/business-results", "/business-results/assets/*"]}`. A matching request is redirected (302) before sign-in, with its path and query string unchanged. `/auth/…`, `/static/…`, `/healthz` and `/_ah/health` are never redirected, even under a broad rule such as `/*`; a rule that overlaps them is logged as a warning. Unparseable JSON is logged and ignored as a whole. An origin with credentials, a query string, a fragment or a path, or with a malformed path list, is logged and skipped, and the other origins still apply. The live value is set on the Cloud Run services, not in this repository.

Feature-flag rules:

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
- `REPORTING_FRESHNESS_CACHE_TTL_SECONDS`
  default `300`
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
