# Accumulating dimension models

## The problem

The Google Ads Data Transfer writes the `p_ads_Ad_*` and `p_ads_Keyword_*`
dimension tables as **daily full snapshots**: every partition repeats every ad
and keyword that existed on that day.

Measured 2026-08-01:

| Raw table | Size | Rows | Distinct entities | Partitions |
|---|---|---|---|---|
| `p_ads_Ad_8179020903` | 606 GB | 881M | 2.75M | 327 |
| `p_ads_Keyword_8179020903` | 200 GB | 788M | 2.56M | 327 |
| `p_ads_AdGroup_8179020903` | 43.3 GB | 211M | 667K | 327 |

`stg_ad_dimension_latest`, `stg_keyword_dimension_latest` and
`stg_ad_group_dimension_latest` were views that ran `row_number() ... order by
loaded_at desc` over the **entire** wildcard with no partition filter, purely to
pick the newest row per entity. Every consumer re-executed that scan:

- `mart_ads_ad_performance_daily`: **394 GB per run**, built twice a day
  (stage + prod)
- each `not_null_stg_ad_dimension_latest_*` test: a separate full scan
- `mart_ads_keyword_daily`, `mart_ads_keyword_audit_detail`: the same for keywords

That was **$449/month of BigQuery Analysis in `gads-export-all`**, growing by
~$0.04/day because every new day added another full snapshot to rescan.

## The fix

All three models are now **accumulating incremental tables**:

```yaml
materialized: incremental
incremental_strategy: merge
unique_key: [transfer_source, account_id, campaign_id, ad_group_id, ad_id]
cluster_by: [account_id, campaign_id]
```

Each run reads only the last `dimension_snapshot_lookback_days` (default 7) of
snapshot partitions and merges them onto the stored state.

### Why not just add a partition filter to the view?

Because it silently loses data. 31,887 ads (1.2%) exist in the snapshot history
but no longer appear in recent partitions — paused or removed ads that still
have historical stats rows. A bare `WHERE _PARTITIONDATE >= ...` on a view would
null out their names, types and landing pages via the marts' left joins.

The accumulating table keeps them: rows not present in the incoming batch are
left untouched by the MERGE, so removed entities retain their last-known
attributes forever.

## Measured results

| | Before | After | Reduction |
|---|---|---|---|
| `stg_ad_dimension_latest` build | 370.7 GiB | **10.58 GB** | 97.1% |
| `stg_keyword_dimension_latest` build | 96.9 GiB | **2.90 GB** | 97.0% |
| `stg_ad_group_dimension_latest` build | 15.1 GiB | **0.46 GB** | 97.0% |
| `mart_ads_ad_performance_daily` | 394 GB | **28.3 GiB** | 92.8% |
| `mart_ads_ad_group_daily` | 26.8 GB | **16.9 GiB** | 37% |

The "after" figures are **billed** bytes for the whole model, taken from
`INFORMATION_SCHEMA.JOBS_BY_PROJECT`. dbt-bigquery's `merge` strategy issues *two*
jobs per incremental run — a `CREATE TABLE AS SELECT` for the temp batch, then the
`MERGE` — and the per-model line dbt prints only reports the second one. For
`stg_ad_dimension_latest` that is 8.80 GB (temp) + 1.78 GB (merge) = 10.58 GB.
Measure incremental models from `JOBS_BY_PROJECT`, not from dbt's log line.

Correctness verified against the full snapshot history:

| Model | Keys in history | Rows in table | Missing |
|---|---|---|---|
| `stg_ad_dimension_latest` | 2,762,314 | 2,762,314 | **0** |
| `stg_keyword_dimension_latest` | 2,559,185 | 2,559,185 | **0** |
| `stg_ad_group_dimension_latest` | 667,255 | 667,255 | **0** |

- all 2,729,222 ads and 662,809 ad groups in the newest snapshot present with
  **0 attribute mismatches**
- every entity that survives only in older partitions is retained — 31,887 ads
  and 4,446 ad groups
- all three `stg_*_dimension_latest_unique_grain` tests pass — no MERGE fan-out

## Operating notes

**First run after deploy rebuilds from full history.** dbt cannot atomically
replace a view with a table, so it drops the view and does a full build —
~370 + ~97 + ~15 GiB per target, roughly $6 one-off across stage and prod. Every
run after that is incremental.

**The lookback window must exceed the longest gap between releases.** The daily
orchestrator makes 7 days generous. If the release is paused for longer than the
window, entities that changed during the gap keep stale attributes until they
next appear in a snapshot — nothing is dropped, updates are just delayed. Raise
`dimension_snapshot_lookback_days` in `dbt_project.yml` before a long pause, or
run `dbt run --full-refresh --select stg_ad_dimension_latest
stg_keyword_dimension_latest` once afterwards to resynchronise.

**The grain tests are load-bearing.** A MERGE whose key contains a NULL fails to
match and appends a duplicate instead of updating, which would fan out the
downstream marts. `tests/stg_*_dimension_latest_unique_grain.sql` catch that.

**Full refresh is safe at any time** and is the recovery path for any suspected
drift.

## Not converted

`stg_campaign_dimension_latest` reads `p_ads_Campaign_*`, which is only 0.4 GB /
1.8M rows. Converting it would add an incremental table to maintain for no
meaningful saving, so it stays a view.
