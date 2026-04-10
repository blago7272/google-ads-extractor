# Report Help Contract

## Purpose

This document is the canonical source for short explanatory notes shown in the report help screen.

The help layer should:

- explain how a report should be interpreted
- clarify where a table is exact versus heuristic
- distinguish keywords from search queries where both exist on the same page
- stay concise and non-technical for end users

## Notes

### Ads Keywords Page

#### Note ID: `ads.keywords.flagged_keyword_opportunities.coverage_end`

- report: `keywords`
- panel: `Flagged keyword opportunities`
- title: `Coverage end`
- text:
  `Coverage end` is the latest date included in that keyword row. It is not always the same as the selected report end date, because the row may stop contributing earlier inside the selected window.

#### Note ID: `ads.keywords.flagged_keyword_opportunities.rollup_overlap`

- report: `keywords`
- panel: `Flagged keyword opportunities`
- title: `How date filtering works`
- text:
  The keyword audit table uses pre-rolled keyword rows and includes rows whose coverage overlaps the selected date range. This makes it suitable for operational review, but not for exact in-window keyword totals.

#### Note ID: `ads.keywords.flagged_keyword_opportunities.keyword_vs_query`

- report: `keywords`
- panel: `Flagged keyword opportunities`
- title: `Keywords versus search queries`
- text:
  `Flagged keyword opportunities` is based on Google Ads keywords, not user search queries. The separate `Terms with the most spend in range` table is the search-query view.

#### Note ID: `ads.keywords.keyword_related_alerts.keyword_scope`

- report: `keywords`
- panel: `Keyword-related alerts`
- title: `What these alerts refer to`
- text:
  `Keyword-related alerts` are generated from the keyword audit logic and only include `keyword_issue` alerts from the same filtered account and date range. They do not come from the search-query table.

### Ads Timing Page

#### Note ID: `ads.timing.budget_flags.pacing_heuristic`

- report: `timing`
- panel: `Potential budget exhaustion days`
- title: `Pacing heuristic`
- text:
  A pacing heuristic means the report is inferring that a campaign may have stopped serving too early in the day from its spend pattern. It is an investigation signal, not proof of a hard budget cap.

### Global App Shell

#### Note ID: `global.reporting_freshness.status_meaning`

- report: `all`
- panel: `Reporting freshness`
- title: `What the freshness status means`
- text:
  `OK` means reporting data is recent enough, `Stale` means data exists but is older than expected, `Error` means the data is well beyond the allowed delay, and `Backfilling` means the account is active but report data is not available yet.

## Change Rules

- Add help entries here before introducing new persistent help text in the UI.
- Prefer one note per user question, not long combined explanations.
- If a note depends on model behavior, keep the wording aligned with the reporting contract.
