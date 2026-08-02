# PMax Labels And History Contract

## Status

- status: `proposed`
- owner: `data-eng`
- related contract: [`pmax_creative_transfer_contract.md`](pmax_creative_transfer_contract.md)
- runtime project: `gads-export-all`
- destination dataset: `gads_pmax_creative_test`
- reporting consumer: none

## Purpose

Define the future, separately approved work needed to retain Google's relative
asset performance labels and to build complete PMax creative history. This is a
planning contract only; it creates no schedule, queue, API extraction, or
reporting consumer.

## Direct API Performance-Label Snapshot

The BigQuery transfer connector cannot provide
`asset_group_asset.performance_label`. A direct Google Ads API snapshot is the
only approved collection path.

Proposed table: `pmax_asset_group_asset_label_snapshot`.

Grain:

`snapshot_date × customer_id × campaign_id × asset_group_id × asset_id × field_type`.

The snapshot must retain the collection date. A label retrieved later must never
be represented as a label for an earlier reporting date.

Labels such as `BEST`, `GOOD`, `LOW`, `LEARNING`, `PENDING`, and
`NOT_APPLICABLE` are relative creative-review signals. They are not additive
performance metrics and must not change campaign totals.

Prerequisites:

- Google Ads API developer token with the necessary production access;
- OAuth refresh-token identity with MCC `8179020903` read access and an
  appropriate login-customer ID;
- secret-managed runtime configuration; and
- no committed developer token, OAuth code, refresh token, or client secret.

## Rolling Creative-Metric Refresh

The proposed rolling-refresh implementation lives only on
`codex/pmax-rolling-refresh`.

- window: 30 days
- cadence: daily, after explicit approval of the transfer evidence
- purpose: reprocess recent dates for late conversions and source corrections
- boundary: no automatic schedule is enabled until separately approved

A rolling window advances forward only. It does not create earlier history when
first enabled.

## Historical Backfill

The proposed historical implementation lives only on
`codex/pmax-historical-backfill`.

- approved start date: 2025-01-01
- first eligible date: the day immediately before the verified rolling 30-day
  boundary
- order: newest eligible date first, then move backward
- daily-segment constraint: do not request dates older than 37 months before
  execution without a separately approved coarser-grain strategy

Required controls:

- dedicated BigQuery completion ledger containing date, transfer run name,
  status, and attempt count;
- skip dates already `SUCCEEDED`, `PENDING`, or `RUNNING`;
- at most 30 dates per submission;
- at most 50 in-flight runs as an operational guardrail, not a platform or
  email quota;
- at most three attempts per date; and
- retry delay of at least 24 hours.

The historical queue must never submit a date inside the active rolling window.
It starts only after the rolling branch demonstrates a complete, accepted 30-day
window.

## Validation And Isolation

- store a non-null label when Google has assigned one and retain every snapshot
  date;
- demonstrate no gaps in the accepted rolling window;
- demonstrate, through the ledger, no historical/rolling date overlap;
- keep asset metrics non-additive; and
- keep `blissful-land-485813-e2` free of consumers until a separate reporting
  contract is approved.

## Non-Goals

- backfill labels that were not snapshotted in the past;
- change the standard `gads_raw` transfer;
- enable rolling refresh, historical backfill, or reporting merely by approving
  this planning contract.
