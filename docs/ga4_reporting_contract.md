# GA4 Reporting Contract

## Scope

This contract defines the standalone GA4 reporting layer built from the BigQuery source table:

- `experimental-clients.sexwell_analyses.GA4-345365542--historical`
- `experimental-clients.sexwell_analyses.erp_import_item_category_v`

The GA4 pages are intentionally siloed from the Google Ads marts and the Auction Insights source pages. They share the same application shell, but they do not reuse Ads business logic or Ads metrics.

## Source Coverage

- Source grain: ecommerce item-event rows
- Time field: `dateHourMinute`
- Current comparison default: last `28` days
- Previous comparison default: previous `28` days immediately before the current window

## Available Fields

Core source fields used in V1:

- `dateHourMinute`
- `sessionSourceMedium`
- `sessionCampaignName`
- `itemName`
- `itemRevenue`
- `itemsViewed`
- `itemsAddedToCart`
- `itemsPurchased`
- `transactionId`

## Known Source Limits

The current GA4 historical export supports product-commerce reporting well, but it is not a full GA4 reporting export.

Not available or not usable in this source:

- sessions
- landing pages
- bounce metrics
- Ads cost / clicks / impressions
- checkout step

Important note:

- `itemsCheckedOut` is not populated in the current source, so checkout-stage reporting is intentionally excluded.
- purchase-bearing rows still resolve `itemBrand` / `itemCategory` to `(not set)` frequently, so the reporting layer derives a reusable item catalog instead of trusting purchase rows directly.

## Enriched Item Catalog

The GA4 report layer now restores product taxonomy with a combined-source item dimension:

- `itemBrand`
  Derived from GA4 view-bearing rows by `itemId`
- `itemCategory`
  Derived primarily from `erp_import_item_category_v.category_l1` by `item_id`
  Fallback: GA4-only category when a product has exactly one observed non-`(not set)` category in GA4

Current observed coverage on commerce-bearing GA4 items:

- derived brand:
  about `97.83%` of revenue
  about `98.20%` of orders
- derived category:
  about `96.91%` of revenue from ERP mapping alone
  effectively `99%+` once the conservative fallback path is allowed

## Normalized Channel Groups

`sessionSourceMedium` is grouped into these reporting buckets:

- `Google Ads`
  Rule: exact `google / cpc`
- `Direct`
  Rule: exact `(direct) / (none)`
- `Organic`
  Rule: values ending in ` / organic`
- `Referral`
  Rule: values ending in ` / referral`
- `Email`
  Rule: values ending in ` / email`
- `Other`
  Rule: everything else

## Page Definitions

### 1. `GA4 Overview`

Purpose:

- high-level commerce status
- source and campaign contribution
- top products
- channel mix by month

Main components:

- KPI cards:
  - Revenue
  - Orders
  - AOV
  - Items purchased
  - Added to cart
  - Items viewed
  - View to order rate
  - ATC to order rate
- Daily trend:
  - Revenue and Orders
  - Added to cart and Items purchased
- Source / medium summary
- Campaign summary
- Top products
- Monthly channel mix

### 2. `GA4 Impact`

Purpose:

- show which sources and campaigns drive products, categories, and brands

Main components:

- Source / medium -> Item
- Campaign -> Item
- Source / medium -> Category
- Campaign -> Category
- Source / medium -> Brand
- Campaign -> Brand

Main metrics:

- Revenue
- Orders
- Items purchased
- Added to cart
- Items viewed
- AOV

### 3. `GA4 Funnel`

Purpose:

- show funnel progression without a checkout step

Main components:

- Funnel by channel group
- Funnel by source / medium

Main metrics:

- Revenue
- Orders
- Items viewed
- Added to cart
- Items purchased
- View to ATC rate
- View to order rate
- ATC to order rate

### 4. `GA4 Timing`

Purpose:

- reproduce the useful hourly logic from the Excel workbook with GA4-native ecommerce metrics

Main components:

- Revenue by hour
- Orders by hour
- Hourly summary table
- Night versus day summary
- Revenue by Date x Hour matrix
- Orders by Date x Hour matrix

Matrix rule:

- the date x hour matrices always use the last `28` days inside the selected filter window

## Workbook Mapping

This GA4 scope is intended to cover the GA4-compatible parts of these workbook tabs:

- `Обозр_акаунт`
  Partial coverage: commerce overview only
- `Приход_×_Час`
  Covered by revenue date x hour matrix
- `Дата_×_Час`
  Covered by orders date x hour matrix
- `Резюме_часови_анализ`
  Covered by hourly summary and night/day split
- `Бюджет_Лимит`
  Not covered from GA4 alone

## Explicit Non-Scope In V1

These items remain out of scope until a richer GA4 export or blended model is added:

- session-based conversion rate
- landing-page reporting
- checkout funnel
- budget-limit logic
- blended Ads + GA4 views on the same page

## Implementation Rule

The GA4 pages must stay standalone:

- separate page routes
- source-local query logic
- no reuse of Ads marts
- no mixing with Auction Insights tables

The app shell may link to the pages, but the page data itself must come only from the GA4 source table above.
