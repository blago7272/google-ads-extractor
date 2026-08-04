# PMax Labels And History Contract

## Status

- status: `historical controls implemented locally; deployment pending approval`
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

The rolling-refresh implementation is now separately contracted in
[`pmax_rolling_refresh_contract.md`](pmax_rolling_refresh_contract.md). It owns
the native daily, 30-day transfer refresh and its acceptance evidence.

A rolling window advances forward only. It does not create earlier history when
first enabled.

## Historical Backfill

The locally implemented historical controls live on
`codex/pmax-historical-backfill` and are contracted in
[`pmax_historical_backfill_contract.md`](pmax_historical_backfill_contract.md).
They use a separate manual-only transfer and destination dataset, not the
operating rolling transfer. Deployment and execution remain explicitly
approval-gated.

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
