# FX rates: sourcing, gaps, and backfill

## How a rate is resolved

`stg_account_fx_rates_daily` resolves `eur_exchange_rate` per (account, date):

1. **`gads_reporting_cfg.ecb_exchange_rates_daily`** — ECB daily reference rates,
   refreshed by the `ecb_fx_refresh` orchestrator step. Covers USD, GBP, RON, MXN.
   Weekends and ECB holidays carry the most recent prior rate forward — **7 days** on
   this branch. (The cost-optimization branch raises this to a `fx_carry_forward_days`
   var defaulting to 30, which widens the tolerance for the *symptom*; the watermark
   change below is what fixes the *cause*, and the two are independent.)
2. **`cfg_exchange_rates` seed** — fallback. Contains **only EUR (1.0) and BGN
   (0.5112918811962185, the fixed peg)**.

The critical asymmetry: **USD, GBP and RON have no seed fallback.** If ECB coverage
lapses beyond the carry-forward window, those accounts get a null `cost_eur` — there
is nothing else to fall back on.

## The 2026-05-26 → 06-05 incident

Reconstructed from `loaded_at` on the rates table:

| When | What |
|---|---|
| through 2026-04-29 | daily loads, report dates current to 04-24 |
| 2026-04-30 → 05-25 | pipeline frozen on the hard freshness gate — nothing loaded |
| 2026-05-26 | manual `fx_rates_backfill.py` caught up report dates 04-27 → **05-25** |
| 2026-05-26 → 06-14 | pipeline still frozen |
| 2026-06-15 | release resumed; its **7-day lookback** reached back only to **06-08** |

Nothing ever fetched **2026-05-26 → 06-05**. The fixed `today - 7` window slid straight
past the hole and never returned to it.

**Impact:** 5 accounts on USD/GBP/RON had null `cost_eur` across 2026-06-02..06-07
(the dates the 7-day carry-forward could not bridge) — 56,197 in original currency,
~47,600 clicks, spanning 1,120 rows in `mart_ads_campaign_daily`, 3,843 in
`mart_ads_ad_performance_daily`, 6,976 in `mart_ads_keyword_daily` and 5,280 in
`mart_ads_search_terms`. A separate 2020-01-01 gap (318.19 USD) existed because the
rates table began 2020-01-02 and New Year's Day has no ECB observation to carry from.

### Resolution (applied 2026-08-02)

```bash
python scripts/fx_rates_backfill.py --start-date 2026-05-26 --end-date 2026-06-05  #  36 rows
python scripts/fx_rates_backfill.py --start-date 2019-12-01 --end-date 2020-01-01  #  80 rows
```

Table went 9,926 → 10,042 rows, 0 duplicate (currency, date) keys. Verified live against
the deployed view: **0 unresolved (account, date) pairs across all history**, down from
6 affected dates. No deploy was needed — the backfill is a data operation and
`stg_account_fx_rates_daily` was still a view, so it recomputed immediately.

Marts pick the corrected values up automatically: they are `materialized: table` and the
orchestrator passes `--full-refresh` every run, so the next scheduled release recomputes
`cost_eur` across all history.

## The systemic fix

`ecb_fx_refresh` no longer uses a fixed `today - lookback_days` window. It anchors on the
**stored watermark** (`resolve_refresh_window` in `orchestration/ecb_fx_refresh.py`):

```
start = min(today - lookback_days, max(report_date) - watermark_overlap_days)
```

- **Steady state** — watermark current, so the 7-day floor governs and recent days are
  re-fetched in case the ECB published late. Behaviour unchanged.
- **After a gap** — the window stretches back to the watermark, so an outage of any
  length self-heals on the next successful run.
- **Empty table** — falls back to the fixed lookback. A daily job should not try to seed
  all history; that is `scripts/fx_rates_backfill.py`.
- **Corrupt watermark** — capped at `max_catchup_days` (400) with a WARNING rather than
  triggering an unbounded fetch.

The watermark is scoped to the currencies the job manages. The table also holds static
EUR/BGN rows written once by the backfill script, which stop at whatever date that run
covered (currently 2026-04-14); letting those set the watermark would drag every refresh
back ~110 days and re-fetch the same window forever.

## Known non-issues

**40 "missing" business days per currency** are ECB holidays — Good Friday and Easter
Monday, 1 May, 25–26 December, 1 January. The ECB publishes nothing on those days;
carry-forward handles them. Only the run above was a genuine gap.

**EUR/BGN stop at 2026-04-14 in the rates table.** `add_static_rates` in the backfill
script is a one-shot guarded by "skip if EUR rows exist", and the daily refresh does not
manage those currencies. It has no numerical effect: the ECB rows for EUR and BGN hold
exactly the seed values (1.0 and 0.5112918811962185), so the seed fallback produces
identical results for later dates.

## Backfilling in future

`scripts/fx_rates_backfill.py` is idempotent — it deletes the fetched date range for the
managed currencies, then appends — so re-running a window is safe.

```bash
python scripts/fx_rates_backfill.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --dry-run
```

To find gaps, compare against business days:

```sql
WITH cal AS (
  SELECT d FROM UNNEST(GENERATE_DATE_ARRAY('2020-01-02', CURRENT_DATE())) d
  WHERE EXTRACT(DAYOFWEEK FROM d) BETWEEN 2 AND 6
)
SELECT cal.d
FROM cal
LEFT JOIN `gads-export-all.gads_reporting_cfg.ecb_exchange_rates_daily` e
  ON e.report_date = cal.d AND e.currency = 'USD'
WHERE e.report_date IS NULL
ORDER BY cal.d
```

Runs of 1–2 days around Easter, 1 May, Christmas and New Year are expected. Anything
longer is a real gap.
