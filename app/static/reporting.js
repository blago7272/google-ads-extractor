const DEFAULT_VISIBLE_ROWS = 10;

const state = {
  options: null,
  tables: new Map(),
  tableData: new Map(),
  currentPayload: null,
};

const PAGE_KIND = document.body.dataset.pageKind;
const REPORT_KIND = document.body.dataset.reportKind;

const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const dateFormat = new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "short", day: "numeric" });

const KPI_DEFS = [
  { key: "cost_eur", label: "Spend (EUR)", formatter: formatMoney },
  { key: "conversion_value_eur", label: "Conv. Value (EUR)", formatter: formatMoney },
  { key: "conversions", label: "Conversions", formatter: formatDecimal },
  { key: "roas", label: "ROAS", formatter: formatRatio },
  { key: "clicks", label: "Clicks", formatter: formatInteger },
  { key: "impressions", label: "Impressions", formatter: formatInteger },
  { key: "ctr", label: "CTR", formatter: formatPercent },
  { key: "cpa_eur", label: "CPA (EUR)", formatter: formatMoney },
];

const CHART_METRICS = {
  conversion_value_eur: { key: "conversion_value_eur", label: "Conversion value", formatter: formatMoney },
  cost_eur: { key: "cost_eur", label: "Spend", formatter: formatMoney },
  roas: { key: "roas", label: "ROAS", formatter: formatRatio },
  conversions: { key: "conversions", label: "Conversions", formatter: formatDecimal },
  conversion_rate: { key: "conversion_rate", label: "Conversion rate", formatter: formatPercent },
};

const CHART_TOOLTIP_KEYS = ["conversion_value_eur", "cost_eur", "roas", "conversions", "conversion_rate"];

const MONEY_KEYS = new Set([
  "campaign_budget_eur",
  "campaign_budget_original",
  "conversion_value_eur",
  "conversion_value_original",
  "cost_eur",
  "cost_original",
  "cpa_eur",
  "cpa_original",
  "cpc_eur",
  "cpc_original",
  "current_conversion_value_eur",
  "current_cost_eur",
  "previous_conversion_value_eur",
  "previous_cost_eur",
  "spend_delta_eur",
  "total_cost_eur",
  "value_delta_eur",
]);

const INTEGER_KEYS = new Set(["clicks", "impressions", "quality_score"]);
const DECIMAL_KEYS = new Set(["conversions", "current_conversions", "previous_conversions"]);
const PERCENT_KEYS = new Set([
  "conversion_rate",
  "ctr",
  "impression_share",
  "overlap_rate",
  "outranking_share",
  "position_above_rate",
  "spend_share",
  "value_share",
]);
const RATIO_KEYS = new Set(["roas", "current_roas", "previous_roas"]);
const DATE_KEYS = new Set(["report_date", "report_date_end", "report_date_start"]);
const MONTH_KEYS = new Set(["report_month"]);
const HOUR_KEYS = new Set(["first_active_hour", "last_active_hour", "report_hour"]);
const BOOLEAN_KEYS = new Set(["budget_exhausted_flag"]);

const TABLE_CONFIG = {
  campaigns: {
    searchInputId: "campaigns-search",
    searchFields: ["campaign_name", "campaign_channel_type", "bidding_strategy_type", "campaign_status", "campaign_serving_status"],
    containerId: "campaigns-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "campaign_channel_type", label: "Channel" },
      { key: "bidding_strategy_type", label: "Bid strategy" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_rate", label: "Conv. rate", format: formatPercent },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  competition: {
    searchInputId: "competition-search",
    searchFields: ["competitor_domain", "report_month"],
    containerId: "competition-table",
    defaultSort: { key: "report_month", direction: "desc" },
    columns: [
      { key: "report_month", label: "Month", format: formatMonth },
      { key: "competitor_domain", label: "Competitor" },
      { key: "impression_share", label: "IS", format: formatPercent },
      { key: "overlap_rate", label: "Overlap", format: formatPercent },
      { key: "position_above_rate", label: "Above us", format: formatPercent },
      { key: "outranking_share", label: "Outrank share", format: formatPercent },
    ],
  },
  keywords: {
    searchInputId: "keywords-search",
    searchFields: ["keyword_text", "campaign_name", "ad_group_name", "audit_reason", "match_type", "keyword_status"],
    searchMode: "regex",
    containerId: "keywords-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "audit_reason", label: "Issue", format: formatPill },
      { key: "keyword_text", label: "Keyword" },
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "quality_score", label: "QS", format: formatNullableInteger },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "report_date_end", label: "Coverage end", format: formatDate },
    ],
  },
  searchTerms: {
    searchInputId: "search-terms-search",
    searchFields: ["search_term", "campaign_name", "ad_group_name", "search_term_status", "search_term_match_type"],
    extraFilterInputIds: [
      "search-terms-conversions-operator",
      "search-terms-conversions-value",
      "search-terms-spend-operator",
      "search-terms-spend-value",
      "search-terms-roas-operator",
      "search-terms-roas-value",
    ],
    metricFilters: [
      { key: "conversions", operatorId: "search-terms-conversions-operator", valueId: "search-terms-conversions-value" },
      { key: "cost_eur", operatorId: "search-terms-spend-operator", valueId: "search-terms-spend-value" },
      { key: "roas", operatorId: "search-terms-roas-operator", valueId: "search-terms-roas-value" },
    ],
    containerId: "search-terms-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "search_term", label: "Search term" },
      { key: "campaign_name", label: "Campaign" },
      { key: "search_term_status", label: "Status" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  alerts: {
    searchInputId: "alerts-search",
    searchFields: ["report_date", "severity", "alert_type", "alert_message"],
    containerId: "alerts-table",
    defaultSort: { key: "report_date", direction: "desc" },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_type", label: "Type" },
      { key: "alert_message", label: "Message" },
    ],
  },
  daypart: {
    searchInputId: "daypart-search",
    searchFields: ["daypart"],
    containerId: "daypart-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "daypart", label: "Daypart", format: formatPill },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  daypartGroups: {
    searchInputId: "daypart-groups-search",
    searchFields: ["ad_group_name", "daypart"],
    containerId: "daypart-groups-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "ad_group_name", label: "Ad group" },
      { key: "daypart", label: "Daypart", format: formatPill },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  budgetFlags: {
    searchInputId: "budget-search",
    searchFields: ["report_date", "campaign_name", "budget_exhausted_flag"],
    containerId: "budget-table",
    defaultSort: { key: "report_date", direction: "desc" },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "campaign_name", label: "Campaign" },
      { key: "budget_exhausted_flag", label: "Flag", format: formatBooleanPill },
      { key: "last_active_hour", label: "Last active hour", format: formatHour },
      { key: "total_cost_eur", label: "Spend", format: formatMoney },
    ],
  },
  weekpartComparison: {
    searchInputId: null,
    searchFields: ["period_group"],
    containerId: "weekpart-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "period_group", label: "Group" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_rate", label: "Conv. rate", format: formatPercent },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  dayWindowComparison: {
    searchInputId: null,
    searchFields: ["period_group"],
    containerId: "daywindow-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "period_group", label: "Group" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_rate", label: "Conv. rate", format: formatPercent },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  zeroConvCampaigns: {
    searchInputId: "zero-conv-campaigns-search",
    searchFields: ["campaign_name"],
    containerId: "zero-conv-campaigns-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "ctr", label: "CTR", format: formatPercent },
      { key: "conversions", label: "Conv.", format: formatDecimal },
    ],
  },
  zeroConvAdGroups: {
    searchInputId: "zero-conv-adgroups-search",
    searchFields: ["campaign_name", "ad_group_name"],
    containerId: "zero-conv-adgroups-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "ctr", label: "CTR", format: formatPercent },
      { key: "conversions", label: "Conv.", format: formatDecimal },
    ],
  },
  zeroConvKeywords: {
    searchInputId: "zero-conv-keywords-search",
    searchFields: ["campaign_name", "ad_group_name", "keyword_text", "match_type"],
    containerId: "zero-conv-keywords-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "keyword_text", label: "Keyword" },
      { key: "match_type", label: "Match type" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "ctr", label: "CTR", format: formatPercent },
      { key: "conversions", label: "Conv.", format: formatDecimal },
    ],
  },
  zeroConvSearchTerms: {
    searchInputId: "zero-conv-searchterms-search",
    searchFields: ["campaign_name", "ad_group_name", "search_term", "search_term_status"],
    containerId: "zero-conv-searchterms-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "search_term", label: "Search term" },
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "search_term_status", label: "Status" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "ctr", label: "CTR", format: formatPercent },
      { key: "conversions", label: "Conv.", format: formatDecimal },
    ],
  },
  campaignWinners: {
    searchInputId: "campaign-winners-search",
    searchFields: ["campaign_name"],
    containerId: "campaign-winners-table",
    defaultSort: { key: "value_delta_eur", direction: "desc" },
    columns: buildDeltaColumns("Campaign"),
  },
  campaignLosers: {
    searchInputId: "campaign-losers-search",
    searchFields: ["campaign_name"],
    containerId: "campaign-losers-table",
    defaultSort: { key: "value_delta_eur", direction: "asc" },
    columns: buildDeltaColumns("Campaign"),
  },
  campaignConcentration: {
    searchInputId: "campaign-concentration-search",
    searchFields: ["campaign_name"],
    containerId: "campaign-concentration-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "spend_share", label: "Spend share", format: formatPercent },
      { key: "value_share", label: "Value share", format: formatPercent },
    ],
  },
  coverageOpportunities: {
    searchInputId: "coverage-opportunities-search",
    searchFields: ["campaign_name", "ad_group_name", "search_term", "search_term_status"],
    containerId: "coverage-opportunities-table",
    defaultSort: { key: "conversion_value_eur", direction: "desc" },
    columns: [
      { key: "search_term", label: "Search term" },
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "search_term_status", label: "Status" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_rate", label: "Conv. rate", format: formatPercent },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  negativeCandidates: {
    searchInputId: "negative-candidates-search",
    searchFields: ["campaign_name", "ad_group_name", "search_term", "search_term_status"],
    containerId: "negative-candidates-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "search_term", label: "Search term" },
      { key: "campaign_name", label: "Campaign" },
      { key: "ad_group_name", label: "Ad group" },
      { key: "search_term_status", label: "Status" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "clicks", label: "Clicks", format: formatInteger },
      { key: "impressions", label: "Impressions", format: formatInteger },
      { key: "ctr", label: "CTR", format: formatPercent },
      { key: "conversions", label: "Conv.", format: formatDecimal },
    ],
  },
  adWinners: {
    searchInputId: "ad-winners-search",
    searchFields: ["campaign_name", "ad_group_name", "ad_label"],
    containerId: "ad-winners-table",
    defaultSort: { key: "value_delta_eur", direction: "desc" },
    columns: buildDeltaColumns("Ad", { includeAdGroup: true, labelKey: "ad_label" }),
  },
  adLosers: {
    searchInputId: "ad-losers-search",
    searchFields: ["campaign_name", "ad_group_name", "ad_label"],
    containerId: "ad-losers-table",
    defaultSort: { key: "value_delta_eur", direction: "asc" },
    columns: buildDeltaColumns("Ad", { includeAdGroup: true, labelKey: "ad_label" }),
  },
  hubAlerts: {
    searchInputId: null,
    searchFields: ["report_date", "severity", "alert_message"],
    containerId: "hub-alerts-list",
    defaultSort: { key: "report_date", direction: "desc" },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_message", label: "Message" },
    ],
  },
};

document.addEventListener("DOMContentLoaded", async () => {
  bindFilterEvents();
  bindPageSpecificEvents();
  try {
    const options = await fetchJson("/api/options");
    state.options = options;
    populateFilters(options);
    await refreshCurrentPage();
  } catch (error) {
    renderGlobalError(error);
  }
});

function buildDeltaColumns(primaryLabel, options = {}) {
  const columns = [{ key: options.labelKey || `${primaryLabel.toLowerCase()}_name`, label: primaryLabel }];
  if (options.includeAdGroup) {
    columns.unshift({ key: "campaign_name", label: "Campaign" });
    columns.push({ key: "ad_group_name", label: "Ad group" });
  }
  return [
    ...columns,
    { key: "current_cost_eur", label: "Current spend", format: formatMoney },
    { key: "previous_cost_eur", label: "Previous spend", format: formatMoney },
    { key: "current_conversions", label: "Current conv.", format: formatDecimal },
    { key: "previous_conversions", label: "Previous conv.", format: formatDecimal },
    { key: "current_conversion_value_eur", label: "Current value", format: formatMoney },
    { key: "previous_conversion_value_eur", label: "Previous value", format: formatMoney },
    { key: "current_roas", label: "Current ROAS", format: formatRatio },
    { key: "previous_roas", label: "Previous ROAS", format: formatRatio },
    { key: "value_delta_eur", label: "Value delta", format: formatMoney },
    { key: "roas_delta", label: "ROAS delta", format: formatDeltaRatio },
  ];
}

function bindFilterEvents() {
  document.getElementById("filters-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshCurrentPage();
  });

  document.getElementById("reset-button").addEventListener("click", async () => {
    if (!state.options) {
      return;
    }
    applyFilterDefaults(state.options.defaults);
    syncAccountOptions();
    if (state.options.defaults.account_id) {
      document.getElementById("account-select").value = state.options.defaults.account_id;
    }
    updateReportLinks();
    await refreshCurrentPage();
  });

  document.getElementById("client-select").addEventListener("change", () => {
    syncAccountOptions();
    updateReportLinks();
  });

  document.getElementById("account-select").addEventListener("change", updateReportLinks);
  document.getElementById("date-from-input").addEventListener("change", updateReportLinks);
  document.getElementById("date-to-input").addEventListener("change", updateReportLinks);
}

function bindPageSpecificEvents() {
  ["hour-metric-select", "weekday-metric-select"].forEach((id) => {
    const input = document.getElementById(id);
    if (input && input.dataset.bound !== "true") {
      input.addEventListener("change", () => {
        if (REPORT_KIND === "timing" && state.currentPayload) {
          renderTimingCharts(state.currentPayload);
        }
      });
      input.dataset.bound = "true";
    }
  });

  const campaignRegexInput = document.getElementById("campaign-regex-input");
  if (campaignRegexInput && campaignRegexInput.dataset.bound !== "true") {
    campaignRegexInput.addEventListener("input", () => {
      clearInputError("campaign-regex-input");
      campaignRegexInput.setCustomValidity("");
      updateReportLinks();
    });
    campaignRegexInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await refreshCurrentPage();
      }
    });
    campaignRegexInput.dataset.bound = "true";
  }
}

function showLoadingState() {
  if (document.getElementById("kpi-grid")) {
    document.getElementById("kpi-grid").innerHTML = '<div class="loading-state">Loading metrics</div>';
  }
  [
    "trend-chart",
    "campaigns-table",
    "competition-table",
    "keywords-table",
    "search-terms-table",
    "alerts-table",
    "daypart-table",
    "daypart-groups-table",
    "budget-table",
    "hub-alerts-list",
    "report-card-grid",
    "conclusions-grid",
    "status-card-grid",
    "timing-highlights",
    "hour-chart",
    "weekday-chart",
    "weekpart-table",
    "daywindow-table",
    "zero-conv-campaigns-table",
    "zero-conv-adgroups-table",
    "zero-conv-keywords-table",
    "zero-conv-searchterms-table",
    "campaign-winners-table",
    "campaign-losers-table",
    "campaign-concentration-table",
    "coverage-opportunities-table",
    "negative-candidates-table",
    "ad-winners-table",
    "ad-losers-table",
  ].forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.innerHTML = '<div class="loading-state">Loading data</div>';
    }
  });
}

function populateFilters(options) {
  const clientSelect = document.getElementById("client-select");
  const clientIds = options.clients.map((item) => item.client_id);

  clientSelect.innerHTML = [
    '<option value="">All clients</option>',
    ...clientIds.map((clientId) => `<option value="${escapeHtml(clientId)}">${escapeHtml(clientId)}</option>`),
  ].join("");

  const urlFilters = readFiltersFromUrl();
  applyFilterDefaults({
    ...options.defaults,
    ...urlFilters,
  });
  syncAccountOptions();
  if (urlFilters.account_id || options.defaults.account_id) {
    document.getElementById("account-select").value = urlFilters.account_id || options.defaults.account_id;
  }
  const campaignRegexInput = document.getElementById("campaign-regex-input");
  if (campaignRegexInput) {
    campaignRegexInput.value = urlFilters.campaign_regex || "";
  }
  updateReportLinks();
}

function readFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    client_id: params.get("client_id") || undefined,
    account_id: params.get("account_id") || undefined,
    date_from: params.get("date_from") || undefined,
    date_to: params.get("date_to") || undefined,
    campaign_regex: params.get("campaign_regex") || undefined,
  };
}

function applyFilterDefaults(defaults) {
  document.getElementById("client-select").value = defaults.client_id || "";
  document.getElementById("date-from-input").value = defaults.date_from || "";
  document.getElementById("date-to-input").value = defaults.date_to || "";
}

function syncAccountOptions() {
  const accountSelect = document.getElementById("account-select");
  const clientId = document.getElementById("client-select").value;
  const accounts = (state.options?.accounts || []).filter((account) => !clientId || account.client_id === clientId);
  const previousValue = accountSelect.value;
  accountSelect.innerHTML = [
    '<option value="">All accounts</option>',
    ...accounts.map((account) => (
      `<option value="${escapeHtml(account.account_id)}">${escapeHtml(account.account_name)} (${escapeHtml(account.account_id)})</option>`
    )),
  ].join("");
  if (accounts.some((account) => account.account_id === previousValue)) {
    accountSelect.value = previousValue;
  } else if (accounts[0]) {
    accountSelect.value = accounts[0].account_id;
  } else {
    accountSelect.value = "";
  }
}

function currentFilterQuery() {
  const params = new URLSearchParams();
  const clientId = document.getElementById("client-select").value;
  const accountId = document.getElementById("account-select").value;
  const dateFrom = document.getElementById("date-from-input").value;
  const dateTo = document.getElementById("date-to-input").value;
  const campaignRegex = document.getElementById("campaign-regex-input")?.value.trim();
  if (clientId) {
    params.set("client_id", clientId);
  }
  if (accountId) {
    params.set("account_id", accountId);
  }
  if (dateFrom) {
    params.set("date_from", dateFrom);
  }
  if (dateTo) {
    params.set("date_to", dateTo);
  }
  if (campaignRegex) {
    params.set("campaign_regex", campaignRegex);
  }
  return params;
}

function updateReportLinks() {
  const query = currentFilterQuery().toString();
  const hubLink = document.getElementById("hub-link");
  if (hubLink) {
    hubLink.href = query ? `/?${query}` : "/";
  }
  document.querySelectorAll("[data-report-link]").forEach((link) => {
    const reportName = link.dataset.reportName;
    link.href = query ? `/reports/${reportName}?${query}` : `/reports/${reportName}`;
  });
}

async function refreshCurrentPage() {
  if (!validatePageFilters()) {
    return;
  }

  updateReportLinks();
  showLoadingState();

  const params = currentFilterQuery();
  const endpoint = PAGE_KIND === "hub"
    ? `/api/hub?${params.toString()}`
    : `/api/reports/${REPORT_KIND}?${params.toString()}`;
  const payload = await fetchJson(endpoint);
  state.currentPayload = payload;

  renderScope(payload.scope, payload.summary);
  renderKpis(payload.summary, payload.previous_summary);

  if (PAGE_KIND === "hub") {
    renderHub(payload);
    return;
  }

  if (REPORT_KIND === "overview") {
    renderStatusCards(payload.status_cards || [], "status-card-grid");
    renderTrendChart(payload.trend || [], "trend-chart");
    renderTable("campaigns", payload.campaigns || []);
    renderTable("competition", payload.competition || []);
    return;
  }

  if (REPORT_KIND === "keywords") {
    renderNote("keyword-alerts-note", payload.alerts_definition);
    renderTable("keywords", payload.keywords || []);
    renderTable("searchTerms", payload.search_terms || []);
    renderTable("alerts", payload.alerts || []);
    return;
  }

  if (REPORT_KIND === "timing") {
    renderInsights(payload.timing_highlights || [], "timing-highlights");
    renderNote("budget-definition-note", payload.budget_flags_definition);
    renderTimingCharts(payload);
    renderTable("weekpartComparison", payload.weekpart_comparison || []);
    renderTable("dayWindowComparison", payload.day_window_comparison || []);
    renderTable("daypart", payload.daypart || []);
    renderTable("daypartGroups", payload.daypart_ad_groups || []);
    renderTable("budgetFlags", payload.budget_flags || []);
    return;
  }

  if (REPORT_KIND === "efficiency") {
    renderTable("zeroConvCampaigns", payload.zero_conv_campaigns || []);
    renderTable("zeroConvAdGroups", payload.zero_conv_ad_groups || []);
    renderTable("zeroConvKeywords", payload.zero_conv_keywords || []);
    renderTable("zeroConvSearchTerms", payload.zero_conv_search_terms || []);
    renderTable("campaignWinners", payload.campaign_winners || []);
    renderTable("campaignLosers", payload.campaign_losers || []);
    renderTable("campaignConcentration", payload.campaign_concentration || []);
    return;
  }

  if (REPORT_KIND === "coverage") {
    renderTable("coverageOpportunities", payload.coverage_opportunities || []);
    renderTable("negativeCandidates", payload.negative_candidates || []);
    return;
  }

  if (REPORT_KIND === "creative") {
    renderTable("adWinners", payload.ad_winners || []);
    renderTable("adLosers", payload.ad_losers || []);
    return;
  }

  if (REPORT_KIND === "alerts") {
    renderTable("alerts", payload.alerts || []);
    renderTable("budgetFlags", payload.budget_flags || []);
  }
}

function validatePageFilters() {
  const campaignRegexInput = document.getElementById("campaign-regex-input");
  if (!campaignRegexInput) {
    return true;
  }
  const query = campaignRegexInput.value.trim();
  if (!query) {
    clearInputError("campaign-regex-input");
    campaignRegexInput.setCustomValidity("");
    return true;
  }
  try {
    // Validate the pattern locally before it reaches BigQuery regexp_contains.
    new RegExp(query, "i");
    clearInputError("campaign-regex-input");
    campaignRegexInput.setCustomValidity("");
    return true;
  } catch {
    campaignRegexInput.classList.add("is-invalid");
    campaignRegexInput.setCustomValidity("Campaign regexp is invalid.");
    campaignRegexInput.reportValidity();
    return false;
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail || `Request failed with status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}

function renderHub(payload) {
  renderInsights(payload.management_conclusions || [], "conclusions-grid");
  renderStatusCards(payload.status_cards || [], "status-card-grid");
  renderTrendChart(payload.trend || [], "trend-chart");
  renderTable("hubAlerts", payload.top_alerts || []);
  renderReportCards(payload.report_cards || []);
}

function renderScope(scope, summary) {
  document.getElementById("selected-range-label").textContent = `${formatDate(scope.date_from)} to ${formatDate(scope.date_to)}`;
  document.getElementById("comparison-range-label").textContent = `${formatDate(scope.previous_date_from)} to ${formatDate(scope.previous_date_to)}`;
  document.getElementById("scope-label").textContent = scope.account_id || scope.client_id || "All active accounts";
  const start = summary.report_date_start ? formatDate(summary.report_date_start) : formatDate(scope.date_from);
  const end = summary.report_date_end ? formatDate(summary.report_date_end) : formatDate(scope.date_to);
  document.getElementById("coverage-badge").textContent = `${start} to ${end}`;
}

function renderKpis(summary, previousSummary) {
  const container = document.getElementById("kpi-grid");
  if (!container) {
    return;
  }
  container.innerHTML = KPI_DEFS.map((definition) => {
    const currentValue = summary?.[definition.key];
    const previousValue = previousSummary?.[definition.key];
    const delta = buildDelta(currentValue, previousValue);
    return `
      <article class="kpi-card">
        <p class="kpi-title">${definition.label}</p>
        <div class="kpi-value">${definition.formatter(currentValue)}</div>
        <div class="kpi-delta ${delta.className}">${delta.label}</div>
      </article>
    `;
  }).join("");
}

function renderStatusCards(cards, containerId) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = cards.length
    ? cards.map((card) => `
      <article class="status-card ${escapeHtml(card.tone || "neutral")}">
        <h3>${escapeHtml(card.title)}</h3>
        <p>${escapeHtml(card.detail)}</p>
      </article>
    `).join("")
    : '<div class="empty-state">No status cards available.</div>';
}

function renderInsights(items, containerId) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = items.length
    ? items.map((item) => `
      <article class="insight-card">
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.detail)}</p>
      </article>
    `).join("")
    : '<div class="empty-state">No insights available.</div>';
}

function renderReportCards(cards) {
  const container = document.getElementById("report-card-grid");
  if (!container) {
    return;
  }
  const query = currentFilterQuery().toString();
  container.innerHTML = cards.map((card) => `
    <a class="report-card" href="/reports/${escapeHtml(card.report_name)}${query ? `?${query}` : ""}">
      <h3>${escapeHtml(card.title)}</h3>
      <p>${escapeHtml(card.description)}</p>
      <span class="report-card-meta">${escapeHtml(card.meta)}</span>
    </a>
  `).join("");
}

function renderTrendChart(rows, containerId) {
  const host = document.getElementById(containerId);
  if (!host) {
    return;
  }
  if (!rows.length) {
    host.innerHTML = '<div class="empty-state">No trend data in the selected range.</div>';
    return;
  }

  const width = 1080;
  const height = 320;
  const padding = { top: 24, right: 24, bottom: 36, left: 48 };
  const valuesA = rows.map((row) => Number(row.cost_eur || 0));
  const valuesB = rows.map((row) => Number(row.conversion_value_eur || 0));
  const maxValue = Math.max(...valuesA, ...valuesB, 1);
  const pointsA = buildLinePoints(valuesA, width, height, padding, maxValue);
  const pointsB = buildLinePoints(valuesB, width, height, padding, maxValue);
  const lastRow = rows[rows.length - 1];

  host.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trend chart">
      ${buildGridLines(width, height, padding)}
      <polyline fill="none" stroke="#285e54" stroke-width="4" points="${pointsB}"></polyline>
      <polyline fill="none" stroke="#bf5a36" stroke-width="4" points="${pointsA}"></polyline>
      <text x="${padding.left}" y="${padding.top - 4}" fill="#66766a" font-size="12">Spend vs conversion value (EUR)</text>
      <circle cx="${pointX(valuesA.length - 1, valuesA.length, width, padding)}" cy="${pointY(Number(lastRow.cost_eur || 0), height, padding, maxValue)}" r="5" fill="#bf5a36"></circle>
      <circle cx="${pointX(valuesB.length - 1, valuesB.length, width, padding)}" cy="${pointY(Number(lastRow.conversion_value_eur || 0), height, padding, maxValue)}" r="5" fill="#285e54"></circle>
    </svg>
  `;
}

function renderTimingCharts(payload) {
  const hourMetric = getChartMetric(document.getElementById("hour-metric-select")?.value);
  const weekdayMetric = getChartMetric(document.getElementById("weekday-metric-select")?.value);

  renderBarChart("hour-chart", payload.hour_of_day || [], {
    labelKey: "report_hour",
    valueKey: hourMetric.key,
    valueLabel: hourMetric.label,
    valueFormatter: hourMetric.formatter,
    tooltipKeys: CHART_TOOLTIP_KEYS,
    labelFormatter: (value) => `${String(value).padStart(2, "0")}:00`,
  });
  renderBarChart("weekday-chart", payload.weekday_profile || [], {
    labelKey: "weekday_name",
    valueKey: weekdayMetric.key,
    valueLabel: weekdayMetric.label,
    valueFormatter: weekdayMetric.formatter,
    tooltipKeys: CHART_TOOLTIP_KEYS,
    labelFormatter: shortWeekday,
  });
}

function renderBarChart(containerId, rows, options) {
  const host = document.getElementById(containerId);
  if (!host) {
    return;
  }
  if (!rows.length) {
    host.innerHTML = '<div class="empty-state">No timing data in the selected range.</div>';
    return;
  }

  const width = 1080;
  const height = 320;
  const padding = { top: 26, right: 16, bottom: 48, left: 28 };
  const maxValue = Math.max(...rows.map((row) => Number(row[options.valueKey] || 0)), 1);
  const barSpace = (width - padding.left - padding.right) / rows.length;
  const barWidth = Math.max(Math.min(barSpace * 0.62, 42), 12);

  const bars = rows.map((row, index) => {
    const value = Number(row[options.valueKey] || 0);
    const x = padding.left + index * barSpace + (barSpace - barWidth) / 2;
    const y = pointY(value, height, padding, maxValue);
    const barHeight = height - padding.bottom - y;
    const label = options.labelFormatter ? options.labelFormatter(row[options.labelKey]) : row[options.labelKey];
    const title = buildChartTooltip(label, row, options);
    return `
      <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="8" fill="#bf5a36">
        <title>${escapeHtml(title)}</title>
      </rect>
      <text class="chart-label" x="${x + barWidth / 2}" y="${height - 20}" text-anchor="middle">${escapeHtml(String(label))}</text>
    `;
  }).join("");

  host.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Bar chart">
      ${buildGridLines(width, height, padding)}
      <text x="${padding.left}" y="${padding.top - 6}" fill="#66766a" font-size="12">${escapeHtml(options.valueLabel)} by ${escapeHtml(options.labelKey)}</text>
      ${bars}
    </svg>
  `;
}

function buildChartTooltip(label, row, options) {
  const parts = [
    `${label}: ${options.valueLabel} ${stripHtml((options.valueFormatter || formatDecimal)(row[options.valueKey]))}`,
  ];
  (options.tooltipKeys || []).forEach((key) => {
    if (key === options.valueKey) {
      return;
    }
    parts.push(`${metricLabel(key)} ${stripHtml(formatMetricValue(key, row[key]))}`);
  });
  return parts.join(" | ");
}

function renderTable(name, rows) {
  const config = TABLE_CONFIG[name];
  const container = document.getElementById(config.containerId);
  if (!container) {
    return;
  }

  state.tableData.set(name, rows);
  const tableState = state.tables.get(name) || {
    sortKey: config.defaultSort.key,
    direction: config.defaultSort.direction,
    expanded: false,
  };
  const { filteredRows, filterError } = filterRowsForTable(name, rows);

  if (filterError) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(filterError)}</div>`;
    return;
  }

  const sortedRows = [...filteredRows].sort((left, right) => compareRows(left, right, tableState.sortKey, tableState.direction));
  if (!sortedRows.length) {
    container.innerHTML = '<div class="empty-state">No rows for the selected range.</div>';
    return;
  }

  const collapseThreshold = config.collapseThreshold || DEFAULT_VISIBLE_ROWS;
  const isCollapsible = sortedRows.length > collapseThreshold;
  const expanded = isCollapsible ? tableState.expanded : true;
  const visibleRows = expanded ? sortedRows : sortedRows.slice(0, collapseThreshold);
  const metaLabel = expanded || !isCollapsible
    ? `${formatInteger(sortedRows.length)} filtered rows`
    : `Showing first ${formatInteger(visibleRows.length)} of ${formatInteger(sortedRows.length)} filtered rows`;

  container.innerHTML = `
    <div class="table-topbar">
      <div class="table-meta">${metaLabel}</div>
      ${isCollapsible ? `<button type="button" class="table-toggle-button" data-table-toggle="${name}">${expanded ? "Show first 10" : "Expand all"}</button>` : ""}
    </div>
    <div class="table-shell">
      <table class="data-table">
        <thead>
          <tr>
            ${config.columns.map((column) => `
              <th>
                <button type="button" data-table="${name}" data-key="${column.key}">
                  ${column.label}${renderSortMarker(tableState, column.key)}
                </button>
              </th>
            `).join("")}
          </tr>
        </thead>
        <tbody>
          ${buildSummaryRow(name, filteredRows, config)}
          ${visibleRows.map((row) => `
            <tr>
              ${config.columns.map((column) => `<td>${formatCell(row[column.key], column.format)}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  state.tables.set(name, { ...tableState, expanded });
  bindTableInteractions(name);
}

function bindTableInteractions(name) {
  const config = TABLE_CONFIG[name];
  document.querySelectorAll(`button[data-table="${name}"]`).forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.addEventListener("click", () => {
      const tableState = state.tables.get(name) || {
        sortKey: config.defaultSort.key,
        direction: config.defaultSort.direction,
        expanded: false,
      };
      const key = button.dataset.key;
      const direction = tableState.sortKey === key && tableState.direction === "desc" ? "asc" : "desc";
      state.tables.set(name, { ...tableState, sortKey: key, direction });
      renderTable(name, state.tableData.get(name) || []);
    });
    button.dataset.bound = "true";
  });

  document.querySelectorAll(`button[data-table-toggle="${name}"]`).forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.addEventListener("click", () => {
      const tableState = state.tables.get(name) || {
        sortKey: config.defaultSort.key,
        direction: config.defaultSort.direction,
        expanded: false,
      };
      state.tables.set(name, { ...tableState, expanded: !tableState.expanded });
      renderTable(name, state.tableData.get(name) || []);
    });
    button.dataset.bound = "true";
  });

  if (config.searchInputId) {
    const searchInput = document.getElementById(config.searchInputId);
    if (searchInput && searchInput.dataset.bound !== "true") {
      searchInput.addEventListener("input", () => renderTable(name, state.tableData.get(name) || []));
      searchInput.dataset.bound = "true";
    }
  }

  (config.extraFilterInputIds || []).forEach((inputId) => {
    const filterInput = document.getElementById(inputId);
    if (filterInput && filterInput.dataset.bound !== "true") {
      const rerender = () => renderTable(name, state.tableData.get(name) || []);
      filterInput.addEventListener("input", rerender);
      filterInput.addEventListener("change", rerender);
      filterInput.dataset.bound = "true";
    }
  });
}

function filterRowsForTable(name, rows) {
  const config = TABLE_CONFIG[name];
  let filteredRows = [...rows];
  const query = config.searchInputId ? document.getElementById(config.searchInputId)?.value.trim() || "" : "";

  if (query) {
    if (config.searchMode === "regex") {
      const pattern = compileRegex(query, config.searchInputId);
      if (!pattern) {
        return { filteredRows: [], filterError: "The filter is not a valid regular expression." };
      }
      filteredRows = filteredRows.filter((row) => pattern.test(getRowSearchText(row, config)));
    } else {
      clearInputError(config.searchInputId);
      const normalizedQuery = query.toLowerCase();
      filteredRows = filteredRows.filter((row) => getRowSearchText(row, config).toLowerCase().includes(normalizedQuery));
    }
  } else {
    clearInputError(config.searchInputId);
  }

  (config.metricFilters || []).forEach((filter) => {
    const operator = document.getElementById(filter.operatorId)?.value;
    const rawValue = document.getElementById(filter.valueId)?.value;
    if (!operator || rawValue === "" || rawValue === null || rawValue === undefined) {
      return;
    }
    const threshold = Number(rawValue);
    if (Number.isNaN(threshold)) {
      return;
    }
    filteredRows = filteredRows.filter((row) => compareMetric(Number(row[filter.key] || 0), operator, threshold));
  });

  return { filteredRows, filterError: null };
}

function getRowSearchText(row, config) {
  const keys = config.searchFields?.length ? config.searchFields : config.columns.map((column) => column.key);
  return keys
    .map((key) => row?.[key] ?? "")
    .join(" ");
}

function buildSummaryRow(name, rows, config) {
  const cells = config.columns.map((column, index) => `<td>${buildSummaryCell(name, column.key, rows, index)}</td>`).join("");
  return `<tr class="summary-row">${cells}</tr>`;
}

function buildSummaryCell(name, key, rows, index) {
  if (index === 0) {
    return `<div class="summary-label">Filtered total</div><div class="summary-meta">${formatInteger(rows.length)} rows</div>`;
  }

  if (BOOLEAN_KEYS.has(key)) {
    return formatInteger(rows.filter((row) => row[key]).length);
  }

  if (key === "ctr") {
    const totalClicks = sumRows(rows, "clicks");
    const totalImpressions = sumRows(rows, "impressions");
    return totalImpressions ? formatPercent(totalClicks / totalImpressions) : "—";
  }

  if (key === "conversion_rate") {
    const totalConversions = sumRows(rows, "conversions");
    const totalClicks = sumRows(rows, "clicks");
    return totalClicks ? formatPercent(totalConversions / totalClicks) : "—";
  }

  if (key === "cpa_eur") {
    const totalCost = sumRows(rows, "cost_eur") || sumRows(rows, "total_cost_eur");
    const totalConversions = sumRows(rows, "conversions");
    return totalConversions ? formatMoney(totalCost / totalConversions) : "—";
  }

  if (key === "cpa_original") {
    const totalCost = sumRows(rows, "cost_original");
    const totalConversions = sumRows(rows, "conversions");
    return totalConversions ? formatMoney(totalCost / totalConversions) : "—";
  }

  if (key === "cpc_eur") {
    const totalCost = sumRows(rows, "cost_eur");
    const totalClicks = sumRows(rows, "clicks");
    return totalClicks ? formatMoney(totalCost / totalClicks) : "—";
  }

  if (key === "cpc_original") {
    const totalCost = sumRows(rows, "cost_original");
    const totalClicks = sumRows(rows, "clicks");
    return totalClicks ? formatMoney(totalCost / totalClicks) : "—";
  }

  if (key === "roas") {
    const totalValue = sumRows(rows, "conversion_value_eur");
    const totalCost = sumRows(rows, "cost_eur") || sumRows(rows, "total_cost_eur");
    return totalCost ? formatRatio(totalValue / totalCost) : "—";
  }

  if (key === "current_roas") {
    const totalValue = sumRows(rows, "current_conversion_value_eur");
    const totalCost = sumRows(rows, "current_cost_eur");
    return totalCost ? formatRatio(totalValue / totalCost) : "—";
  }

  if (key === "previous_roas") {
    const totalValue = sumRows(rows, "previous_conversion_value_eur");
    const totalCost = sumRows(rows, "previous_cost_eur");
    return totalCost ? formatRatio(totalValue / totalCost) : "—";
  }

  if (key === "roas_delta") {
    const currentValue = sumRows(rows, "current_conversion_value_eur");
    const currentCost = sumRows(rows, "current_cost_eur");
    const previousValue = sumRows(rows, "previous_conversion_value_eur");
    const previousCost = sumRows(rows, "previous_cost_eur");
    const currentRoas = currentCost ? currentValue / currentCost : 0;
    const previousRoas = previousCost ? previousValue / previousCost : 0;
    return formatDeltaRatio(currentRoas - previousRoas);
  }

  if (MONEY_KEYS.has(key)) {
    return formatMoney(sumRows(rows, key));
  }

  if (INTEGER_KEYS.has(key)) {
    return formatInteger(sumRows(rows, key));
  }

  if (DECIMAL_KEYS.has(key)) {
    return formatDecimal(sumRows(rows, key));
  }

  if (PERCENT_KEYS.has(key)) {
    return formatPercent(sumRows(rows, key));
  }

  if (RATIO_KEYS.has(key)) {
    return formatRatio(sumRows(rows, key));
  }

  if (DATE_KEYS.has(key) || MONTH_KEYS.has(key) || HOUR_KEYS.has(key)) {
    return "—";
  }

  return "—";
}

function compareRows(left, right, key, direction) {
  const a = left?.[key];
  const b = right?.[key];
  let comparison = 0;
  if (typeof a === "boolean" || typeof b === "boolean") {
    comparison = Number(Boolean(a)) - Number(Boolean(b));
  } else if (typeof a === "number" || typeof b === "number" || (!Number.isNaN(Number(a)) && !Number.isNaN(Number(b)))) {
    comparison = Number(a || 0) - Number(b || 0);
  } else {
    comparison = String(a || "").localeCompare(String(b || ""), undefined, { numeric: true, sensitivity: "base" });
  }
  return direction === "asc" ? comparison : -comparison;
}

function sumRows(rows, key) {
  return rows.reduce((total, row) => total + Number(row[key] || 0), 0);
}

function compareMetric(value, operator, threshold) {
  if (operator === "gte") {
    return value >= threshold;
  }
  if (operator === "lte") {
    return value <= threshold;
  }
  return true;
}

function compileRegex(query, inputId) {
  try {
    const pattern = new RegExp(query, "i");
    clearInputError(inputId);
    return pattern;
  } catch {
    const input = inputId ? document.getElementById(inputId) : null;
    if (input) {
      input.classList.add("is-invalid");
    }
    return null;
  }
}

function clearInputError(inputId) {
  if (!inputId) {
    return;
  }
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.remove("is-invalid");
  }
}

function renderSortMarker(tableState, key) {
  if (tableState.sortKey !== key) {
    return "";
  }
  return tableState.direction === "desc" ? " ↓" : " ↑";
}

function buildDelta(currentValue, previousValue) {
  const current = Number(currentValue || 0);
  const previous = Number(previousValue || 0);
  if (!previous) {
    return { label: "No previous baseline", className: "neutral" };
  }
  const deltaPct = ((current - previous) / previous) * 100;
  const sign = deltaPct > 0 ? "+" : "";
  return {
    label: `${sign}${decimalFormat.format(deltaPct)}% vs previous`,
    className: deltaPct > 0 ? "positive" : deltaPct < 0 ? "negative" : "neutral",
  };
}

function getChartMetric(metricKey) {
  return CHART_METRICS[metricKey] || CHART_METRICS.conversion_value_eur;
}

function renderNote(containerId, text) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.textContent = text || "";
}

function buildGridLines(width, height, padding) {
  const lines = [];
  for (let step = 0; step < 4; step += 1) {
    const y = padding.top + ((height - padding.top - padding.bottom) / 3) * step;
    lines.push(`<line x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}" stroke="rgba(216,206,183,0.85)" stroke-width="1"></line>`);
  }
  return lines.join("");
}

function buildLinePoints(values, width, height, padding, maxValue) {
  return values
    .map((value, index) => `${pointX(index, values.length, width, padding)},${pointY(value, height, padding, maxValue)}`)
    .join(" ");
}

function pointX(index, total, width, padding) {
  if (total <= 1) {
    return width / 2;
  }
  return padding.left + ((width - padding.left - padding.right) * index) / (total - 1);
}

function pointY(value, height, padding, maxValue) {
  const drawableHeight = height - padding.top - padding.bottom;
  return padding.top + drawableHeight - (drawableHeight * value) / maxValue;
}

function formatCell(value, formatter) {
  if (formatter) {
    return formatter(value);
  }
  return escapeHtml(value ?? "—");
}

function formatMetricValue(key, value) {
  if (BOOLEAN_KEYS.has(key)) {
    return value ? "Flagged" : "OK";
  }
  if (DATE_KEYS.has(key)) {
    return formatDate(value);
  }
  if (MONTH_KEYS.has(key)) {
    return formatMonth(value);
  }
  if (HOUR_KEYS.has(key)) {
    return formatHour(value);
  }
  if (key === "roas_delta") {
    return formatDeltaRatio(value);
  }
  if (MONEY_KEYS.has(key)) {
    return formatMoney(value);
  }
  if (DECIMAL_KEYS.has(key)) {
    return formatDecimal(value);
  }
  if (INTEGER_KEYS.has(key)) {
    return formatInteger(value);
  }
  if (RATIO_KEYS.has(key)) {
    return formatRatio(value);
  }
  if (PERCENT_KEYS.has(key)) {
    return formatPercent(value);
  }
  return String(value ?? "—");
}

function metricLabel(key) {
  const labels = {
    conversion_rate: "Conv. rate",
    conversion_value_eur: "Conv. value",
    cost_eur: "Spend",
    ctr: "CTR",
    impressions: "Impressions",
    clicks: "Clicks",
    conversions: "Conversions",
    roas: "ROAS",
    cpa_eur: "CPA",
    cpc_eur: "CPC",
    current_cost_eur: "Current spend",
    previous_cost_eur: "Previous spend",
    current_conversions: "Current conversions",
    previous_conversions: "Previous conversions",
    current_conversion_value_eur: "Current value",
    previous_conversion_value_eur: "Previous value",
    current_roas: "Current ROAS",
    previous_roas: "Previous ROAS",
    value_delta_eur: "Value delta",
    roas_delta: "ROAS delta",
    spend_share: "Spend share",
    value_share: "Value share",
  };
  return labels[key] || key;
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const number = Number(value);
  const sign = number < 0 ? "-" : "";
  return `${sign}€${moneyFormat.format(Math.abs(number))}`;
}

function formatDecimal(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return decimalFormat.format(Number(value));
}

function formatInteger(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return numberFormat.format(Number(value));
}

function formatNullableInteger(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return numberFormat.format(Number(value));
}

function formatRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${decimalFormat.format(Number(value))}x`;
}

function formatDeltaRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${decimalFormat.format(number)}x`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${decimalFormat.format(Number(value) * 100)}%`;
}

function formatDate(value) {
  if (!value) {
    return "—";
  }
  return dateFormat.format(new Date(`${value}T00:00:00`));
}

function formatMonth(value) {
  if (!value) {
    return "—";
  }
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-GB", { year: "numeric", month: "short" });
}

function formatHour(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${String(Number(value)).padStart(2, "0")}:00`;
}

function formatPill(value) {
  const safe = escapeHtml(String(value ?? "—"));
  const className = String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return `<span class="pill ${className}">${safe}</span>`;
}

function formatBooleanPill(value) {
  return value ? '<span class="pill medium">Flagged</span>' : '<span class="pill ok">OK</span>';
}

function shortWeekday(value) {
  return String(value || "").slice(0, 3);
}

function renderGlobalError(error) {
  const target = document.getElementById("kpi-grid") || document.querySelector(".page-shell");
  if (target) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function stripHtml(value) {
  return String(value).replace(/<[^>]*>/g, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
