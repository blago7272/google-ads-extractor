# Team Review Checklist

Use this checklist during the contract review meeting and record a clear decision for each item.

Decision states:

- `Approve`
- `Reject`
- `Defer`
- `Needs follow-up`

## Phase 1 Scope

- [ ] Ads-only phase 1 scope is approved
  Decision: Recommend Approve
  Notes: Keeps the first release bounded to Ads-native logic and avoids blocking delivery on GA4 blending.

- [ ] The minimum page set is approved
  Pages: Overview, Campaign Explorer, Keyword Audit, Search Terms, Budget Exhaustion, Ad Group Daypart, Alerts
  Decision: Recommend Approve
  Notes: This is a strong minimum set for agency reporting. Add ad-level reporting immediately after these pages, not before.

## Data Model

- [ ] `client_id` must be treated as part of every mart grain
  Decision: Recommend Approve
  Notes: This should be treated as a required filtering and API key, not just a selected column.

- [ ] Search terms should remain daily-grain for real date filtering
  Decision: Recommend Approve
  Notes: Required if the UI will support trustworthy filters such as last 7 days, last 30 days, or this month.

- [ ] Keyword reporting should be split into:
  Daily keyword fact mart
  Keyword audit rollup mart
  Decision: Recommend Approve
  Notes: Use the daily fact for time-series analysis and keep the audit mart for lookback-window classification.

- [ ] `cfg_segments` should be kept and wired into campaign reporting
  Decision: Recommend Approve
  Notes: Brand vs Generic vs Competitor segmentation is standard for agency reporting and should not require account-side changes.

## Currency

- [ ] Dual-currency reporting is required in phase 1
  Native account currency plus EUR reporting values
  Decision: Recommend Approve
  Notes: The current `cost_eur` naming is unsafe for non-EUR accounts. Original and EUR values should both exist in the mart layer.

- [ ] Exchange-rate cadence is agreed
  Options: daily, monthly
  Decision: Recommend Monthly For Phase 1
  Notes: Monthly rates are enough for the first pass. Use fixed mappings for pegged currencies where appropriate and move to a daily feed before scaling volatile non-EUR accounts.

- [ ] Default UI currency is agreed
  Options: native currency, EUR
  Decision: Recommend Native For Single-Account Views, EUR For Cross-Account Rollups
  Notes: This keeps account-level numbers familiar while preserving a common basis for multi-account summaries.

## Alerts And Freshness

- [ ] Simple rule-based alerts are sufficient for phase 1
  Decision: Recommend Approve
  Notes: Good enough for launch. More sophisticated threshold linkage can come after the first live reporting cycle.

- [ ] Data freshness should be shown on every report page
  Decision: Recommend Approve
  Notes: Every report page should show the effective data date so users do not mistake T-1 data for live data.

- [ ] Freshness SLA is approved
  Proposed: T-1 normal latency, warn at 36h, error at 72h
  Decision: Recommend Approve
  Notes: This is a sensible first SLA for Google Ads transfer-based reporting.

## Access And Security

- [ ] Application-level `client_id` filtering is sufficient for the first release
  Decision: Recommend Approve
  Notes: This is enough while the only access path is the app and clients do not receive direct BigQuery credentials.

- [ ] Row-level security is deferred unless direct BigQuery or Looker-style access is introduced
  Decision: Recommend Approve
  Notes: Revisit only if direct warehouse or BI-tool access becomes a real requirement.

## Next Extensions

- [ ] Ad-level reporting should be the next ads-only extension after the first HTML pages
  Decision: Recommend Approve
  Notes: Ad-level reporting adds clear agency value and is the logical next layer after overview, campaign, keyword, and search-term pages.

- [ ] RSA asset-level reporting is deferred from the first ad-level release
  Decision: Recommend Approve
  Notes: Start with ad-level performance first. Asset-level RSA analysis can follow once the base ad mart is proven useful.

- [ ] Auction insights remains optional unless the team marks it as required
  Decision: Recommend Approve
  Notes: Keep it optional unless monthly competitor reporting is a contractual deliverable for clients.

## Delivery And Governance

- [ ] Mart contracts should be enforced before the HTML layer is built
  Decision: Recommend Approve
  Notes: This reduces the risk of silent schema drift breaking the app.

- [ ] Breaking schema changes should require a deprecation period
  Decision: Recommend Approve
  Notes: New columns can be added freely, but removals, renames, type changes, and grain changes should not be deployed abruptly.

- [ ] The environment and dataset strategy needs a separate infrastructure review
  Decision: Recommend Approve
  Notes: The current schema-macro approach and any future dev/staging/prod dataset strategy need to be designed together, not patched ad hoc.

## Owners

- Product owner: TBD by team
- Technical owner: TBD by team
- Data owner: TBD by team
- Date reviewed: TBD by team
