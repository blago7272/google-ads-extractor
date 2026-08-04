# PMax Rolling Refresh Contract

## Status

- status: `operating; initial rolling window accepted`
- owner: `data-eng`
- runtime project: `gads-export-all`
- BigQuery location: `EU`
- transfer: `Google Ads MCC 8179020903 PMax Creative Test`
- destination dataset: `gads_pmax_creative_test`
- reporting consumer: none

## Purpose

Run the already validated, isolated PMax creative transfer every day and refresh
the last 30 source days. This reprocesses recent creative metrics for late
conversions and source corrections without touching the production `gads_raw`
Google Ads transfer.

## Configuration

| Setting | Contracted value |
| --- | --- |
| Transfer resource | `projects/638625952730/locations/europe/transferConfigs/6a96a83d-0000-22b6-beb9-14223bb50dc6` |
| Schedule | `every day 08:00` UTC |
| Refresh window | 30 days |
| Native mechanism | BigQuery Data Transfer Service `dataRefreshWindowDays` |
| Destination | `gads-export-all.gads_pmax_creative_test` |

BigQuery Data Transfer Service refreshes `[today-30, today-1]` on each scheduled
run. It overwrites only the refreshed date partitions, so repeated runs do not
duplicate PMax creative rows.

The schedule and refresh window are configured only by
[`../scripts/deploy_pmax_rolling_refresh.sh`](../scripts/deploy_pmax_rolling_refresh.sh).
The script validates the immutable transfer resource, Google Ads source,
destination dataset, and display name before it can make a change.

## Operating Rules

- First run: submit one range run for the exact active `[today-30, today-1]`
  window with `scripts/deploy_pmax_rolling_refresh.sh --seed-current-window`.
  This makes the initial window observable immediately rather than waiting for
  the next daily schedule. It is not historical backfill.
- Daily run: preserve the native 30-day window; do not supplement it with
  client-side manual runs.
- Failure: inspect transfer runs, correct the connector failure, and let the
  next scheduled run retry the window. Use a manual run only for a documented
  one-off recovery.
- The running transfer remains the only data writer. No object in
  `blissful-land-485813-e2` consumes this dataset.
- Asset metrics continue to be non-additive and must not be summed into campaign
  metrics.

## Activation Evidence

- enabled at: 2026-08-02 23:42 UTC
- configuration check: daily `08:00` UTC schedule and 30-day refresh window
  accepted by BigQuery Data Transfer Service
- initial seed: `[2026-07-03T00:00:00Z, 2026-08-02T00:00:00Z)` submitted at
  2026-08-02 23:44 UTC
- initial run count: 30 PMax transfer runs, covering 2026-07-03 through
  2026-08-01; the service queued them newest-first

## Initial Acceptance Result

- accepted at: 2026-08-04 01:50 UTC
- accepted source window: 2026-07-03 through 2026-08-01 (30 dates)
- latest transfer-run states: 30 `SUCCEEDED`, 0 incomplete, 0 failed
- date coverage: all three physical reporting views cover every accepted date

Sample quality check for 2026-08-01:

| Report | Rows | Quality result |
| --- | ---: | --- |
| Asset groups | 3,001 (130 campaigns) | 0 null asset-group IDs; 0 negative metric rows |
| Assets | 20,902 | 0 null asset-group, asset, or field-type IDs; 0 negative metric rows |
| Top combinations | 864 | 0 null asset-group IDs or combinations |

The initial rolling window is accepted. Historical implementation is unblocked,
but its transfer configuration and execution require their own contract and
explicit deployment approval.

## Acceptance Checks

Before starting historical work, record an accepted 30-day window in the
transfer run evidence:

1. the transfer has a non-null daily `nextRunTime` and `dataRefreshWindowDays=30`;
2. all three custom PMax reports have succeeded for every accepted date in the
   window;
3. the three expected destination tables contain the date window with no
   unexpected gaps; and
4. the PMax asset-group/asset/combinations quality checks from the creative
   transfer contract still pass on a sample refresh date.

Run `python scripts/validate_pmax_rolling_window.py --window-end-exclusive
YYYY-MM-DD` to test these run and view-coverage requirements for a specific
window. It deliberately returns a non-zero status until every latest transfer
run has succeeded, so it is also the hard gate for historical work.

## Boundary With Historical Backfill

The daily scheduler is the rolling mechanism; it is not the historical queue.
Historical work begins only after the first 30-day window is accepted. Its
newest eligible date is the day immediately before the accepted rolling boundary,
and it proceeds backward to `2025-01-01` under its separate ledgered branch.
It must not submit history to this rolling transfer.

## Non-Goals

- alter the existing `gads_raw` transfer;
- add `asset_group_asset.performance_label` to connector GAQL;
- enqueue historical dates; or
- create a reporting mart or consumer.
