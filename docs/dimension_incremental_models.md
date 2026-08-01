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

`stg_ad_dimension_latest` and `stg_keyword_dimension_latest` were views that ran
`row_number() ... order by loaded_at desc` over the **entire** wildcard with no
partition filter, purely to pick the newest row per entity. Every consumer
re-executed that scan:

- `mart_ads_ad_performance_daily`: **394 GB per run**, built twice a day
  (stage + prod)
- each `not_null_stg_ad_dimension_latest_*` test: a separate full scan
- `mart_ads_keyword_daily`, `mart_ads_keyword_audit_detail`: the same for keywords

That was **$449/month of BigQuery Analysis in `gads-export-all`**, growing by
~$0.04/day because every new day added another full snapshot to rescan.

## The fix

Both models are now **accumulating incremental tables**:

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
| `stg_ad_dimension_latest` build | 370.7 GiB | **1.8 GiB** | 99.5% |
| `stg_keyword_dimension_latest` build | 96.9 GiB | **785.7 MiB** | 99.2% |
| `mart_ads_ad_performance_daily` | 394 GB | **28.3 GiB** | 92.8% |

Correctness verified against the full snapshot history:

- ads: 2,762,314 keys in full history, 2,762,314 rows in the table, **0 missing**
- keywords: 2,559,185 keys in full history, 2,559,185 rows, **0 missing**
- all 2,729,222 ads in the newest snapshot present with **0 attribute mismatches**
- `stg_ad_dimension_latest_unique_grain` and
  `stg_keyword_dimension_latest_unique_grain` pass — no MERGE fan-out

## Operating notes

**First run after deploy rebuilds from full history.** dbt cannot atomically
replace a view with a table, so it drops the view and does a full build —
~370 GiB + ~97 GiB per target, roughly $6 one-off across stage and prod. Every
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

## Not yet converted

`stg_ad_group_dimension_latest` reads `p_ads_AdGroup_*` (43.3 GB, 211M rows) and
has the identical snapshot shape — the same treatment would save a further
~$25/month. `stg_campaign_dimension_latest` reads `p_ads_Campaign_*`, which is
only 0.4 GB and not worth converting.
