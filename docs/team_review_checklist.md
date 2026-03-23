# Team Review Checklist

Use this checklist during the contract review meeting and record a clear decision for each item.

Decision states:

- `Approve`
- `Reject`
- `Defer`
- `Needs follow-up`

## Phase 1 Scope

- [ ] Ads-only phase 1 scope is approved
  Decision:
  Notes:

- [ ] The minimum page set is approved
  Pages: Overview, Campaign Explorer, Keyword Audit, Search Terms, Budget Exhaustion, Ad Group Daypart, Alerts
  Decision:
  Notes:

## Data Model

- [ ] `client_id` must be treated as part of every mart grain
  Decision:
  Notes:

- [ ] Search terms should remain daily-grain for real date filtering
  Decision:
  Notes:

- [ ] Keyword reporting should be split into:
  Daily keyword fact mart
  Keyword audit rollup mart
  Decision:
  Notes:

- [ ] `cfg_segments` should be kept and wired into campaign reporting
  Decision:
  Notes:

## Currency

- [ ] Dual-currency reporting is required in phase 1
  Native account currency plus EUR reporting values
  Decision:
  Notes:

- [ ] Exchange-rate cadence is agreed
  Options: daily, monthly
  Decision:
  Notes:

- [ ] Default UI currency is agreed
  Options: native currency, EUR
  Decision:
  Notes:

## Alerts And Freshness

- [ ] Simple rule-based alerts are sufficient for phase 1
  Decision:
  Notes:

- [ ] Data freshness should be shown on every report page
  Decision:
  Notes:

- [ ] Freshness SLA is approved
  Proposed: T-1 normal latency, warn at 36h, error at 72h
  Decision:
  Notes:

## Access And Security

- [ ] Application-level `client_id` filtering is sufficient for the first release
  Decision:
  Notes:

- [ ] Row-level security is deferred unless direct BigQuery or Looker-style access is introduced
  Decision:
  Notes:

## Next Extensions

- [ ] Ad-level reporting should be the next ads-only extension after the first HTML pages
  Decision:
  Notes:

- [ ] RSA asset-level reporting is deferred from the first ad-level release
  Decision:
  Notes:

- [ ] Auction insights remains optional unless the team marks it as required
  Decision:
  Notes:

## Delivery And Governance

- [ ] Mart contracts should be enforced before the HTML layer is built
  Decision:
  Notes:

- [ ] Breaking schema changes should require a deprecation period
  Decision:
  Notes:

- [ ] The environment and dataset strategy needs a separate infrastructure review
  Decision:
  Notes:

## Owners

- Product owner:
- Technical owner:
- Data owner:
- Date reviewed:

