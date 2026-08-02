# API & Service Capability Matrix

Date: 2026-04-13

## Data Sources

### BigQuery Data Transfer Service (Primary)
| Capability | Status | Details |
|------------|--------|---------|
| Account-level daily stats | Active | `p_ads_AccountStats_*` |
| Campaign-level daily stats | Active | `p_ads_CampaignStats_*` |
| Campaign-level hourly stats | Active | `p_ads_HourlyCampaignStats_*` |
| Ad group daily stats | Active | `p_ads_AdGroupStats_*` |
| Ad group hourly stats | Active | `p_ads_HourlyAdGroupStats_*` |
| Budget daily stats | Active | `p_ads_BudgetStats_*` |
| Ad-level daily stats | Active | `p_ads_AdStats_*` |
| Keyword daily stats | Active | `p_ads_KeywordStats_*` |
| Search query daily stats | Active | `p_ads_SearchQueryStats_*` |
| Campaign dimensions | Active | `p_ads_Campaign_*` |
| Ad group dimensions | Active | `p_ads_AdGroup_*` |
| Keyword dimensions (incl. QS) | Active | `p_ads_Keyword_*` |
| Ad dimensions (multi-format) | Active | `p_ads_Ad_*` |
| Audience / demographics | Not present | Not in current transfer config |
| Geographic performance | Not present | Not in current transfer config |
| Placement / display network | Not present | Not in current transfer config |
| Shopping / product data | Not present | Not in current transfer config |
| Conversion action detail | Not present | Single aggregated conversions field only |

### External Data Sources (App-Layer Only)
| Source | Status | Details |
|--------|--------|---------|
| Auction insights (daily/weekly/monthly) | Active for 1 account | `experimental-clients.sexwell_analyses.gads--impression_share--*` |
| GA4 historical ecommerce | Active for 1 account | `experimental-clients.sexwell_analyses.GA4-345365542--historical` |
| ERP item categories | Active for 1 account | `experimental-clients.sexwell_analyses.erp_import_item_category_v` |

### Authentication
| Capability | Status | Details |
|------------|--------|---------|
| Google OAuth 2.0 | Implemented | Login, callback, logout, session management |
| Role-based access | Implemented | admin (all access) and viewer (scoped to client/account) |
| User management | Manual BigQuery table | `cfg_app_users` — not in dbt seeds |
| Session management | Cookie-based | 24h TTL, itsdangerous signed cookies |

## Reporting Application API

### Endpoints
| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/` | GET | Yes | Management hub page |
| `/reports/{name}` | GET | Yes | Report page shell (10+ reports) |
| `/api/options` | GET | Yes | Filter options (clients, accounts, date bounds, feature flags) |
| `/api/freshness` | GET | Yes | Data freshness for selected account |
| `/api/hub` | GET | Yes | Hub payload (conclusions, KPIs, trends, alerts) |
| `/api/reports/{name}` | GET | Yes | Report-specific JSON payload |
| `/api/dashboard` | GET | Yes | Alias for overview report (backwards compat) |
| `/auth/login` | GET | No | Initiate OAuth flow |
| `/auth/callback` | GET | No | OAuth token exchange |
| `/auth/logout` | GET | No | Session cleanup |
| `/healthz` | GET | No | Health check |

### Query Parameters
| Parameter | Used By | Default |
|-----------|---------|---------|
| `client_id` | All `/api/*` | First allowed client |
| `account_id` | All `/api/*` | First allowed account |
| `date_from` | All `/api/*` | Today minus `default_window_days` |
| `date_to` | All `/api/*` | Today |
| `campaign_regex` | Keywords report | None |
| `timing_matrix_days` | Timing report | 7 |

### Caching
| Cache | TTL | Max Entries | Purpose |
|-------|-----|-------------|---------|
| Options | 3600s | — | Filter dropdown options |
| Freshness | 300s | — | Per-account freshness status |
| Query | 900s | 256 | BigQuery result caching |

## Orchestration Pipeline

### Release Steps
| Step | Gate Type | Description |
|------|-----------|-------------|
| raw_freshness_gate | Hard gate | Blocks pipeline if any active account has stale raw data |
| stage_seed_bootstrap | Soft | Seeds missing config tables in stage |
| stage_build | Build | dbt run for staging + marts on stage target |
| stage_test | Test | dbt test on stage |
| prod_seed_bootstrap | Soft | Seeds missing config tables in prod |
| prod_build | Build | dbt run for staging + marts on prod target |
| prod_test | Test | dbt test on prod |

### Infrastructure
| Component | Platform | Trigger |
|-----------|----------|---------|
| Release orchestrator | Cloud Run Job | Cloud Scheduler (daily, configurable cron) |
| Reporting app | Local / Cloud Run Service (planned) | HTTP |
| BigQuery | Google Cloud | On-demand queries |
| Data Transfer | BigQuery DTS | Automatic (Google-managed schedule) |

## Rate Limits & Constraints

- BigQuery Data Transfer: Google-managed, typically runs daily with ~24h lag.
- BigQuery queries: Subject to project-level quotas (concurrent slots, bytes scanned).
- Freshness gate: Expects data for yesterday (T-1). Zero-lag tolerance by default.
- Cloud Run Job: 1 CPU, 2 GB RAM, 1-hour timeout.
- App caching: In-process only — no shared cache across replicas (acceptable for single-instance).
