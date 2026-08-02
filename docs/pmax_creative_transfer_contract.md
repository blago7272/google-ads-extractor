# PMax Creative Transfer Contract

## Status

- status: `approved_test`
- owner: `data-eng`
- approved evidence date: 2026-08-02
- runtime project: `gads-export-all`
- BigQuery location: `EU`
- destination dataset: `gads_pmax_creative_test`
- reporting consumer: none

## Purpose

Maintain an isolated Custom Google Ads BigQuery Transfer for Performance Max
creative evidence. It supplies asset-group performance, asset-level performance,
and Google's served top combinations without changing the existing standard
Google Ads transfer or any production reporting consumer.

## Isolation

The existing `gads_raw` standard Google Ads transfer remains unchanged. Enabling
these reports on that transfer can alter schemas used by existing reporting.

The isolated transfer is:

- MCC: `8179020903`
- display name: `Google Ads MCC 8179020903 PMax Creative Test`
- location: `europe`
- destination dataset: `gads_pmax_creative_test`
- mode: Custom Google Ads transfer
- automatic scheduling: disabled

No object in `blissful-land-485813-e2` may consume this dataset until a separate
reporting-consumer contract is approved.

## Transfer Reports

### `pmax_asset_group_daily`

Grain: `report_date × customer_id × campaign_id × asset_group_id × ad_network_type`.

Captures asset-group identity, status, primary status, ad strength, and daily
impressions, clicks, CTR, cost, conversions, and conversion value.

### `pmax_asset_group_asset_daily`

Grain: `report_date × customer_id × campaign_id × asset_group_id × asset_id × field_type × ad_network_type`.

Captures text, image, and video asset identity, link status, source, field type,
and daily metrics. It includes text, image URL, and YouTube video ID where Google
returns them.

### `pmax_top_combinations_daily`

Grain: `report_date × customer_id × campaign_id × asset_group_id`.

Captures Google's top served asset combinations, equivalent to the PMax
Combinations report.

## Query And Metric Rules

- Custom-transfer GAQL must contain only `SELECT` and `FROM`; it must include
  `segments.date`. BigQuery Data Transfer Service supplies each run's date filter.
- Do not set `exclude_removed_items=true`; removed assets are relevant to
  historical creative review.
- Asset-level metrics are authoritative only at their own grain. Never sum them
  into campaign spend, clicks, conversions, conversion value, or ROAS.
- Existing `gads_reporting_mart` campaign metrics remain authoritative for
  campaign reporting until a separate consumer contract is accepted.

## Performance Label Boundary

`asset_group_asset.performance_label` is intentionally absent. The BigQuery
Google Ads transfer rejected that field in the tested configuration on 2026-08-02.
Performance labels require a separately contracted direct Google Ads API snapshot;
they must not be added to transfer GAQL unless a future dry run proves support.

## Validated Evidence

Transfer configuration:

`projects/638625952730/locations/europe/transferConfigs/6a96a83d-0000-22b6-beb9-14223bb50dc6`

Manual run for 2026-08-01:

| Check | Result |
| --- | --- |
| Transfer state | succeeded |
| Report jobs succeeded / failed | 3 / 0 |
| Asset-group rows | 3,001 |
| Asset-group-asset rows | 20,903 |
| Top-combination rows | 864 |
| PMax campaigns in asset-group report | 130 |
| Matching current PMax campaigns | 130 |
| Null asset-group IDs / asset IDs / field types / top combinations | 0 / 0 / 0 / 0 |
| Negative metric rows | 0 |

The deployment identity could not complete an exhaustive metadata-list check in
`blissful-land-485813-e2`; this is not evidence of a consumer. No consumer is
approved by this contract.

## Validation Requirements

Before any later promotion, verify that:

1. all three transfer reports succeed for the selected run date;
2. PMax asset groups, asset IDs, and field types are populated where eligible;
3. top combinations are populated where Google provides eligible combinations,
   otherwise document the outcome in the transfer log;
4. sampled asset-group-day metrics are non-negative; and
5. no campaign mart aggregates the asset-level metrics.

## Promotion Boundary

The validated transfer remains manual-only. No schedule is enabled by this
contract or its deployment script.

The next approved implementation branch is `codex/pmax-rolling-refresh`. It owns
the proposed daily rolling 30-day refresh and requires separate explicit approval
before any schedule is enabled. The historical queue is a later, distinct branch:
`codex/pmax-historical-backfill`.

## Non-Goals

- modify `gads_raw` or its standard transfer;
- alter Google Sheets history, Meta data, or reporting in `blissful-land-485813-e2`;
- enable a recurring transfer schedule;
- backfill PMax history; or
- use asset metrics as campaign totals.
