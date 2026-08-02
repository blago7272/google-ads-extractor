# Backfill Runbook — `advertising_platforms` GAds pipeline (blissful-land-485813-e2)

> **Scope:** recovering a missing day for a single Google Ads account in the
> `blissful-land-485813-e2` reporting stack. This pipeline is **external to this
> dbt repo** — it is driven by an Apps Script bound to the master "Core--BQ
> Extractor" Google Sheet. This repo (`Google Ads--Extractor`) does **not**
> produce or schedule it. This runbook only documents how to repair BigQuery
> after the upstream Sheet has been fixed.

## Pipeline overview

```
Google Ads API
  → Apps Script writes per-account tab `GAds--<acct>` in master Sheet
      1_5r2f7QWR5MhmBeUrGmGBeZah74sFbKnSQZ2djaot8w   (cols A:G)
  → BQ EXTERNAL table  advertising_platforms.GAds--<acct>      (GOOGLE_SHEETS / Drive-backed)
  → BQ BASE  table     advertising_platforms.GAds--<acct>--historical   (delete+insert sync, daily ~05:30 Europe/Sofia)
  → BQ table           shopify_reporting.daily_reporting_existing       (per-shop delete+insert, daily ~06:00 & ~18:00)
```

Account ⇄ shop map (`helpers.shopify_shop_marketing_map`):

| Google Ads account | shop_domain | Brand |
|---|---|---|
| 4848659150 (+5732163981, stale) | matraci-bg1.myshopify.com | Matraci |
| **4866322944** | **bgsleepy.myshopify.com** | **Sleepy.BG** |
| 3317731390 | gr-onesleep-com.myshopify.com | Onesleep GR |
| 5746874754 | 1sleep-ro.myshopify.com | Onesleep RO |
| 9078355164 | cyonesleepcom.myshopify.com | Onesleep CY |

Columns of `GAds--<acct>--historical`: `date DATE, campaign_name STRING, campaign_id STRING, impressions INT64, clicks INT64, spend FLOAT64, currency STRING`.

## Ordering dependency (important)

`daily_reporting_existing.ad_spend` reads from `GAds--<acct>--historical`. So the
order is strict:

1. Fix the Sheet tab (upstream — adds the day to the external table). **Manual.**
2. Backfill `GAds--<acct>--historical` from the external table.  ← **Step A**
3. Refresh `daily_reporting_existing` for the affected shop + dates.  ← **Step B**

Running Step B before Step A will write `NULL`/missing ad_spend for the day.

## Credential note

The external tables are **Drive-backed**. Reading them (and therefore Step A's
`INSERT ... SELECT FROM external`) requires a credential with the Drive OAuth
scope. A plain `gcloud`/service-account credential fails with
`Permission denied while getting Drive credentials`. Run Step A either:
- from the **BigQuery console** (browser session has Drive access), or
- with a Drive-scoped credential:
  `gcloud auth login --update-adc --enable-gdrive-access`

The daily pipeline itself runs as `609147420643-compute@developer.gserviceaccount.com`,
which is Drive-authorized for this sheet.

---

## Step 0 — Identify which dates are missing

```sql
-- Compare the external (sheet) feed against the historical table.
SELECT
  e.max_ext   AS external_max_date,   -- needs Drive scope to read external
  h.max_hist  AS historical_max_date
FROM
  (SELECT MAX(date) max_ext  FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944`) e,
  (SELECT MAX(date) max_hist FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`) h;

-- Find specific gaps in historical over a window:
SELECT d AS missing_date
FROM UNNEST(GENERATE_DATE_ARRAY(DATE '2026-06-01', CURRENT_DATE('Europe/Sofia') - 1)) d
LEFT JOIN (
  SELECT DISTINCT date FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`
) h ON h.date = d
WHERE h.date IS NULL
ORDER BY d;
```

Cross-check coverage across all accounts (catches account-specific skips like the
2026-06-10 Sleepy.BG miss):

```sql
SELECT '4866322944' acct, MAX(date) FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`
UNION ALL SELECT '4848659150', MAX(date) FROM `blissful-land-485813-e2.advertising_platforms.GAds--4848659150--historical`
UNION ALL SELECT '3317731390', MAX(date) FROM `blissful-land-485813-e2.advertising_platforms.GAds--3317731390--historical`
UNION ALL SELECT '5746874754', MAX(date) FROM `blissful-land-485813-e2.advertising_platforms.GAds--5746874754--historical`
UNION ALL SELECT '9078355164', MAX(date) FROM `blissful-land-485813-e2.advertising_platforms.GAds--9078355164--historical`
ORDER BY 1;
```

---

## Step A — Backfill `GAds--<acct>--historical` from the external table

Mirrors the production loader (`DELETE` the affected dates, then re-`INSERT` from
the external sheet), but **scoped to only the missing date(s)** for safety. The
production version operates on *all* dates present in the sheet; scoping to the
missing day touches nothing else and is idempotent.

```sql
-- A1: delete the day to be (re)loaded
DELETE FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`
WHERE `date` = DATE '2026-06-10';

-- A2: re-insert that day straight from the external (sheet) table
INSERT INTO `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`
  (`date`, `campaign_name`, `campaign_id`, `impressions`, `clicks`, `spend`, `currency`)
SELECT d.`date`, d.`campaign_name`, d.`campaign_id`, d.`impressions`, d.`clicks`, d.`spend`, d.`currency`
FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944` d
WHERE d.`date` = DATE '2026-06-10';
```

For a multi-day range, swap both predicates to
`` `date` BETWEEN DATE 'YYYY-MM-DD' AND DATE 'YYYY-MM-DD' ``.

Verify:

```sql
SELECT date, COUNT(*) rows, ROUND(SUM(spend),2) spend
FROM `blissful-land-485813-e2.advertising_platforms.GAds--4866322944--historical`
WHERE date = DATE '2026-06-10' GROUP BY date;
```

---

## Step B — Refresh `daily_reporting_existing` for the shop + window

Reproduces the production per-shop `DELETE` + `INSERT` exactly (idempotent — the
DELETE clears the shop/window before the INSERT, so no duplicates). The captured
production INSERT is large (~24 KB) and self-contained with its date window baked
in; re-run it **unchanged** paired with the matching DELETE.

```sql
-- B1: clear the shop's window
DELETE FROM `blissful-land-485813-e2.shopify_reporting.daily_reporting_existing`
WHERE shop_domain = 'bgsleepy.myshopify.com'
  AND date BETWEEN DATE('2026-06-07') AND DATE('2026-06-10');

-- B2: re-run the production INSERT for bgsleepy (full statement captured from
--     job history; window 2026-06-07..2026-06-10). See the exact job:
--     INFORMATION_SCHEMA.JOBS_BY_PROJECT job_otjteYQNsG-Rp_SLgIFDa6j1wDDj
--     (statement reads ad_spend from GAds--4866322944--historical, so Step A must run first).
```

> To retrieve the exact, current production INSERT for any shop (in case the
> pipeline logic changes), pull it from job history rather than hardcoding:
> ```sql
> SELECT query FROM `blissful-land-485813-e2.region-eu.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
> WHERE destination_table.table_id = 'daily_reporting_existing'
>   AND statement_type = 'INSERT'
>   AND LOWER(query) LIKE '%bgsleepy.myshopify.com%'
> ORDER BY creation_time DESC LIMIT 1;
> ```

Verify:

```sql
SELECT date, source, ad_spend, ga4_purchases, ga4_revenue, loaded_at
FROM `blissful-land-485813-e2.shopify_reporting.daily_reporting_existing`
WHERE shop_domain = 'bgsleepy.myshopify.com' AND date = DATE '2026-06-10'
ORDER BY source;
```

`source = 'Google Ads'` should now show non-null `ad_spend` for 2026-06-10.

---

## Alternative: just wait for the scheduled run

Both loaders are delete+insert and self-healing over a rolling window:
- `…--historical` re-syncs every date in the sheet daily at ~05:30.
- `daily_reporting_existing` rebuilds a trailing window per shop at ~06:00 & ~18:00.

If the Sheet is fixed **before** the next 05:30 historical run, no manual backfill
is needed — the scheduled jobs will pick the day up. Manual backfill is only for
when you don't want to wait for the next cycle.
