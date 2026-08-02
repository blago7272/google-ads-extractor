# Pipeline cost optimizations

Four changes taking the daily build from **339 GB × 2 targets** to **81.6 GB × 1 target**.
All figures are billed bytes from `INFORMATION_SCHEMA.JOBS_BY_PROJECT` in `region-eu`,
measured on a full `dbt build`, at $6.25/TiB.

| Stage | Per run | Per day | Per month |
|---|---|---|---|
| Original (before the accumulating dimensions) | — | ~2,400 GB | **$449** |
| After the accumulating dimensions | 339 GB × 2 | 679 GB | **$126** |
| After the four changes below | 81.6 GB × 1 | 81.6 GB | **$15** |

## 1. `stg_account_fx_rates_daily` is a table, not a view

Ten marts join to this model for currency conversion. As a view, every one of them
inlined its full definition — and that definition did a `union distinct` across **nine**
fact staging views just to enumerate `(account_id, report_date)` pairs.

It was **237 GB of a 339 GB build (70%)**, to produce ~1 MB of output. That is why
`mart_ads_overview_daily` cost 15.68 GB to build 32,796 rows from a 0.33 GB fact table.

Measured effect of `materialized='table'` alone:

| Mart | As view | As table |
|---|---|---|
| `mart_ads_overview_daily` | 15.68 GB | 71 MiB |
| `mart_ads_campaign_daily` | 16.13 GB | 720 MiB |
| `mart_ads_ad_group_daily` | 16.87 GB | 2.1 GiB |
| `mart_ads_budget_exhaustion` | 16.28 GB | 2.9 GiB |
| `mart_ads_keyword_daily` | 17.78 GB | 3.9 GiB |
| `mart_ads_keyword_audit_detail` | 17.82 GB | 4.0 GiB |
| `mart_ads_ad_performance_daily` | 18.30 GB | 4.3 GiB |
| `mart_ads_hourly_performance_daily` | 18.47 GB | 5.1 GiB |
| `mart_ads_search_terms` | 17.01 GB | 5.7 GiB |
| `mart_ads_adgroup_daypart` | 20.11 GB | 8.9 GiB |
| **10 marts** | **174.5 GB** | **37.7 GB** |
| its 4 `not_null` tests | 62.5 GB | ~0 |

## 2. The FX date spine

The nine-way union existed only to discover which `(account_id, report_date)` pairs
were needed. A dense spine — active accounts × every date from `fx_spine_start_date`
to tomorrow — is a **strict superset** at near-zero cost.

The direction of error matters: over-covering costs a few thousand unused ~1 KB rows;
under-covering would null out `cost_eur` in every mart. The spine deliberately starts
years before any real data.

Building the model: **15.6 GB → 205 KiB**. Output grows 35,682 → 105,876 rows (~3 MB).

Verified against the old union-based view, on identical inputs:

- **0 lost pairs** — every `(account_id, report_date)` the old model produced still exists
- **0 value mismatches** — identical `eur_exchange_rate` and `currency` on every shared pair

`stg_account_fx_rates_daily_covers_reported_dates` guards the spine: it fails if any
account/date with real activity has no FX row. `stg_account_fx_rates_daily_unique_grain`
guards against a duplicate pair fanning out ten marts at once.

### The ECB gap this exposed

The coverage test failed on first run — and found a **pre-existing** bug, not a
regression (the A/B above proves no pair was lost). The ECB feed went dark for 13 days
over **2026-05-26 → 2026-06-07**, longer than the model's 7-day carry-forward window,
and the CSV seed only covers BGN and EUR. Every USD/GBP/RON/MXN account therefore had
null `cost_eur` across 2026-06-02..06-07.

`fx_carry_forward_days` (default **30**) now spans outages of that length. Widening is
provably safe: `rn = 1` still picks the *nearest* prior rate, so a wider window can only
add more-distant candidates that rank lower — it fills gaps and can never change an
already-resolved rate.

Dates preceding the first rate that exists for a currency stay uncovered by definition
(ECB history starts 2020-01-02) and are excluded from the test rather than papered over.

## 3. One `not_null_columns` test per model

dbt issues one query per test, so five `not_null` tests on a view re-execute that view
five times. `stg_ad_group_stats_hourly` cost 4.44 GB per test — **22.2 GB to check one
table**.

The `not_null_columns` generic test (`macros/test_not_null_columns.sql`) checks all
required columns in a single pass. Coverage is identical — a row violating any column
still fails — and failing rows carry a `null_columns` label naming the offenders, so the
per-column diagnostics survive.

| Model | Tests | Before | After |
|---|---|---|---|
| `stg_ad_group_stats_hourly` | 5 | 22.18 GB | 4.44 GB |
| `stg_search_query_stats_daily` | 5 | 21.70 GB | 4.34 GB |
| `stg_ad_stats_daily` | 6 | 9.86 GB | 1.64 GB |
| `stg_campaign_stats_hourly` | 4 | 9.09 GB | 2.27 GB |
| `stg_keyword_performance_daily` | 5 | 8.84 GB | 1.77 GB |
| `stg_ad_group_stats_daily` | 4 | 3.56 GB | 0.89 GB |

Test node count drops 203 → 155. Column-specific tests (`unique`, `accepted_values`)
stay inline — only `not_null` collapses.

## 4. Stage off the daily path

**Nothing reads the stage datasets except dbt's own tests.** Over 30 days,
`gads_reporting_mart_stage` had 3,780 reads, all from `dbt-runner`;
`reporting-app-prod` reads only `gads_reporting_mart`. Stage was an exact byte-for-byte
duplicate of prod — a flat 50% of the bill.

Stage validates *code*, and the daily refresh runs unchanged code against new data, so
it now runs only when asked:

```bash
# daily (what Cloud Scheduler invokes — bare args)
python scripts/release_orchestrator.py

# validate a code change: stage, then prod
python scripts/release_orchestrator.py --include-stage

# validate a code change without touching prod
python scripts/release_orchestrator.py --skip-prod
```

`--skip-prod` implies stage — a stage-only run must not become a no-op — as does
`--stop-after-step stage_build|stage_test`. `INCLUDE_STAGE=true` works as an env var.

### The tradeoff, stated plainly

Stage was a real gate: it built and tested before prod was touched, so a bad build never
reached prod. Now `prod_test` is the gate, and it runs *after* `prod_build` — since marts
are `--full-refresh`, a bad build overwrites good prod data and is caught immediately
afterwards rather than prevented. Recovery is re-running the job once the cause is fixed.

This was an explicit decision to trade that gate for 50% of the bill. Run with
`--include-stage` on any release that changes model SQL.

**No CI pipeline exists in this repo yet** (`.github/workflows` is absent). Until one is
added, `--include-stage` has to be run by hand when model code changes. That is the main
loose end here.

### Stage datasets go stale

`gads_reporting_{cfg,stg,mart}_stage` stop being refreshed. Nothing reads them, but they
still cost storage — drop them, or run `--include-stage` periodically, if that matters.

## What was considered and rejected

**Incremental marts.** After change 1 the marts total only ~37 GB per target, so the
ceiling is ~$7/month. Against that, Google Ads restates conversions retroactively through
its attribution windows, so a naive incremental would freeze stale conversion figures.
Doing it safely needs `insert_overwrite` on `report_date` partitions with a ≥90-day
lookback *and* partition-filtering the staging views — they read `segments_date`, not
`_PARTITIONDATE`, so a mart-level date filter prunes nothing on its own. Poor
risk-to-reward.

**Expiring raw snapshot partitions.** Storage is $36.46/month and the three snapshot
tables are 849 GB of ~982 GB. A 180-day expiry would save ~$8/month and halt the ~3 GB/day
growth — but it permanently destroys the ability to full-refresh beyond the window,
making the accumulating dimension tables the sole record of older entity attributes.
Rejected as data loss.

**Partitioning and clustering the marts.** No meaningful saving on its own — the app reads
only 16.4 GB/month — but worth doing for query latency and as a prerequisite if incremental
marts are ever revisited.
