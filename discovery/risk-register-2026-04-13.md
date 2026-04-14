# Risk Register

Date: 2026-04-13

## Identified Risks & Blockers

### R1 — Incomplete Exchange Rates (HIGH)
**Description:** Only EUR (base) and BGN (fixed peg) have exchange rates configured. The account registry includes accounts in USD, GBP, RON, and MXN, but these currencies have no FX rates in `cfg_exchange_rates`.
**Impact:** All EUR-converted fields (cost_eur, cpc_eur, cpa_eur, conversion_value_eur) will be NULL for non-EUR/non-BGN accounts. Multi-account rollups mixing currencies will produce incomplete totals.
**Mitigation:** Add exchange rates for USD, GBP, RON, and MXN to `cfg_exchange_rates` seed. Consider whether rates should be periodically updated or remain fixed snapshots.

### R2 — GA4 and Auction Insights Outside dbt (MEDIUM)
**Description:** GA4 ecommerce data and auction insights are queried directly from external BigQuery tables by the app's service layer, bypassing the dbt pipeline entirely. These live in `experimental-clients.sexwell_analyses.*`.
**Impact:** No dbt contract enforcement, no automated testing, no freshness monitoring for these data sources. Schema changes in external tables will break the app silently. Cross-referencing with Ads data is ad-hoc.
**Mitigation:** Either bring these into the dbt pipeline as proper staging/mart models, or implement explicit schema validation and freshness checks in the app layer. The `stg_auction_insights` stub already exists but is unused.

### R3 — Single-Account Feature Coverage (MEDIUM)
**Description:** GA4 reports (`has_ga4`) and auction insights (`has_auction_insights`) are enabled for only one account (Sexwell). The GA4 queries hardcode a specific BigQuery table ID (`GA4-345365542--historical`).
**Impact:** These features cannot scale to additional accounts without code changes in `service.py`. The pattern of one hardcoded table per feature doesn't support multi-tenant reporting.
**Mitigation:** Define a configuration pattern (seed or config table) that maps account_id → external data source. Refactor `ga4_table()` and `auction_table()` to be account-aware.

### R4 — App Service Layer Complexity (MEDIUM)
**Description:** `service.py` is 2,984 lines with extensive inline SQL queries. Business logic that should arguably live in dbt (GA4 channel grouping, ERP enrichment, efficiency calculations) is embedded in Python.
**Impact:** Harder to test, maintain, and extend. New report pages require Python changes even when the underlying data is available in BigQuery.
**Mitigation:** Progressively migrate app-layer SQL into dbt mart models, especially for GA4 and efficiency/coverage reports. Keep the app layer as a thin query executor.

### R5 — No Production Hosting Yet (MEDIUM)
**Description:** The reporting app runs locally via `uvicorn --reload`. The `docs/report_hosting_contract.md` describes Cloud Run + IAP deployment but this has not been implemented.
**Impact:** No external user access, no HTTPS, no production monitoring or scaling.
**Mitigation:** Implement the Cloud Run Service deployment following the existing hosting contract. IAP for authentication, HTTPS load balancer, scale-to-zero.

### R6 — Segment Configuration Placeholder (LOW)
**Description:** `cfg_segments` has a single placeholder record with `entity_id=0`. No real campaign-to-segment mappings exist.
**Impact:** Segment-based reporting and filtering cannot work. The infrastructure is there but unused.
**Mitigation:** Populate with real campaign IDs once segmentation requirements are confirmed.

### R7 — Account Group Configuration Minimal (LOW)
**Description:** `cfg_account_groups` has one placeholder record. No real multi-account groups are defined.
**Impact:** Group-level rollup reporting is not possible until groups are properly configured.
**Mitigation:** Define real account groups based on business requirements (by region, brand, etc.).

### R8 — Manual User Management (LOW)
**Description:** `cfg_app_users` is managed via a bootstrap SQL script, not through dbt seeds or an admin UI. Adding or removing users requires running SQL directly against BigQuery.
**Impact:** Operational overhead for user management. Risk of inconsistency between environments.
**Mitigation:** Either move to dbt seeds (with appropriate access controls) or build a simple admin endpoint.

## Open Questions

1. **FX rate update cadence:** Should exchange rates be static snapshots or updated periodically? If periodic, what source and how often?
2. **GA4 integration path:** Should GA4 data be brought into dbt as proper models, or remain as app-layer queries? What about scaling to multiple GA4 properties?
3. **Auction insights source:** The dbt stub (`stg_auction_insights`) exists but the app reads from external tables directly. Should we consolidate?
4. **Report backlog priority:** The `docs/report_backlog_contract.md` lists pending items (daily keyword mart, help screen, Cloud Run deployment). What is the priority order?
5. **Per-client thresholds:** All thresholds are currently at "default" level. Do any clients need custom thresholds for alerts and audits?
6. **Data Transfer coverage:** Several Google Ads report types are not in the current transfer (audiences, geo, placements, shopping, conversion actions). Are any of these needed?
7. **Multi-replica caching:** The current in-process TTL cache doesn't share across instances. If the app scales beyond one replica, should we introduce Redis or similar?
