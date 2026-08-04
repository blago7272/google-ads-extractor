# PMax Historical Backfill Contract

## Status

- status: `scheduler controls implemented locally; live provisioning awaits explicit approval`
- owner: `data-eng`
- runtime project: `gads-export-all`
- rolling transfer: `gads_pmax_creative_test` (read-only boundary reference)
- historical destination: `gads_pmax_creative_history` (not deployed)
- reporting consumer: none

## Purpose And Isolation

Backfill PMax creative metrics from `2025-01-01` through `2026-07-02`, newest
first, without disturbing the operating 30-day rolling transfer. The historical
work uses a separate BigQuery Data Transfer Service configuration and separate
dataset. It must never submit dates to the rolling configuration.

The scope is the same three connector-supported reports already accepted for
the rolling transfer: asset groups, asset-group assets, and top combinations.
`asset_group_asset.performance_label` remains excluded; it needs the separately
approved direct Google Ads API snapshot path.

## Contracted Boundaries

| Setting | Value |
| --- | --- |
| History start (inclusive) | `2025-01-01` |
| Rolling boundary (exclusive) | `2026-07-03` |
| Newest history date | `2026-07-02` |
| Order | newest first |
| Historical dataset | `gads-export-all.gads_pmax_creative_history` |
| Automatic scheduling | disabled |
| Per-submission / in-flight limit | exactly 1 date / 1 run |
| Retry policy | at most 3 attempts; wait at least 24 hours after a failure |

The one-run limit is intentional. The completed rolling seed showed connector
pacing at roughly 35-minute intervals between scheduled dates; no independent
concurrency capacity has been demonstrated for this second configuration yet.
A documented smoke test is required before changing that limit.

The dedicated off-peak execution design and rolling-state gate are contracted in
[`pmax_historical_scheduler_contract.md`](pmax_historical_scheduler_contract.md).

## Deployment And Execution Gates

1. Review the locally implemented controls and grant explicit approval to create
   the historical dataset and manual-only transfer.
2. An operator runs `scripts/deploy_pmax_historical_transfer.sh --apply` and
   completes any Google Ads consent flow. This is the only command that creates
   the second transfer.
3. Run `python3 scripts/manage_pmax_historical_backfill.py --dry-run` to show
   the first candidate without contacting GCP.
4. After a successful one-date smoke test has been reviewed, an operator may
   submit one date with `--apply --confirm-submit-one-date`. The command creates
   or updates the ledger and refuses to submit while any ledgered run is active
   or while the rolling transfer is active.

No automatic schedule, historical run, label snapshot, reporting mart, or
consumer is created by merging this contract.

## Ledger Rules

The ledger table is
`gads_pmax_creative_history.pmax_historical_backfill_ledger`. Its key is
`source_date` and it retains status, attempt count, transfer run name,
submission/completion times, error text, and update time.

- `SUCCEEDED`, `PENDING`, and `RUNNING` dates are skipped.
- `FAILED` and `CANCELLED` dates become eligible only after the 24-hour delay
  and while fewer than three attempts have been recorded.
- Unknown states are held for investigation rather than retried.
- The executor reconciles known active transfer runs into terminal ledger states
  before selecting the next date.

## Acceptance Criteria

- one smoke-test run produces all three expected physical report views in the
  historical dataset for its source date;
- ledger evidence shows no duplicate or overlapping submission;
- every accepted historical date remains outside the rolling window;
- asset metrics remain non-additive; and
- `blissful-land-485813-e2` remains free of reporting consumers.

## Non-Goals

- alter `gads_raw` or the established rolling transfer;
- enable or schedule historical work merely by merging code;
- extract `performance_label`; or
- create a reporting mart or consumer.
