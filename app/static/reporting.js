const DEFAULT_VISIBLE_ROWS = 10;

const state = {
  options: null,
  tables: new Map(),
  tableData: new Map(),
  currentPayload: null,
  currentFreshness: null,
  overviewCampaignSelection: [],
  overviewCampaignOptions: [],
  overviewCampaignSearch: "",
  timingCampaignSelection: [],
  timingCampaignOptions: [],
  timingCampaignSearch: "",
  timingAdGroupSelection: [],
  timingAdGroupOptions: [],
  timingAdGroupSearch: "",
};

const PAGE_KIND = document.body.dataset.pageKind;
const REPORT_KIND = document.body.dataset.reportKind;
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DATE_PRESET_CUSTOM = "custom";

const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const moneyPreciseFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const decimalFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const decimalFixedFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
  cpc_eur: { key: "cpc_eur", label: "CPC", formatter: formatMoneyPrecise },
  roas: { key: "roas", label: "ROAS", formatter: formatRatio },
  conversions: { key: "conversions", label: "Conversions", formatter: formatDecimal },
  conversion_rate: { key: "conversion_rate", label: "Conversion rate", formatter: formatPercent },
  clicks: { key: "clicks", label: "Clicks", formatter: formatInteger },
  impressions: { key: "impressions", label: "Impressions", formatter: formatInteger },
  revenue: { key: "revenue", label: "Revenue", formatter: formatMoney },
  orders: { key: "orders", label: "Orders", formatter: formatInteger },
  items_purchased: { key: "items_purchased", label: "Items purchased", formatter: formatInteger },
  items_added_to_cart: { key: "items_added_to_cart", label: "Added to cart", formatter: formatInteger },
  items_viewed: { key: "items_viewed", label: "Items viewed", formatter: formatInteger },
  aov: { key: "aov", label: "AOV", formatter: formatMoney },
  search_impr_share: { key: "search_impr_share", label: "Search IS", formatter: formatPercentPoint },
  search_overlap_rate: { key: "search_overlap_rate", label: "Overlap", formatter: formatPercentPoint },
  search_outranking_share: { key: "search_outranking_share", label: "Outranking", formatter: formatPercentPoint },
};

const TIMING_MATRIX_METRICS = {
  impressions: { key: "impressions", label: "Impressions", formatter: formatInteger },
  clicks: { key: "clicks", label: "Clicks", formatter: formatInteger },
  cost_eur: { key: "cost_eur", label: "Spend", formatter: formatMoney },
  conversion_value_eur: { key: "conversion_value_eur", label: "Conversion value", formatter: formatMoney },
  roas: { key: "roas", label: "ROAS", formatter: formatRatio },
  conversions: { key: "conversions", label: "Conversions", formatter: formatDecimal },
  conversion_rate: { key: "conversion_rate", label: "Conversion rate", formatter: formatPercent },
  ctr: { key: "ctr", label: "CTR", formatter: formatPercent },
};

const CHART_TOOLTIP_KEYS = ["conversion_value_eur", "cost_eur", "cpc_eur", "roas", "conversions", "conversion_rate", "clicks", "impressions"];


const MONEY_KEYS = new Set([
  "aov",
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
  "revenue",
  "spend_delta_eur",
  "total_cost_eur",
  "value_delta_eur",
]);

const INTEGER_KEYS = new Set(["clicks", "impressions", "items_added_to_cart", "items_purchased", "items_viewed", "orders", "quality_score"]);
const DECIMAL_KEYS = new Set(["conversions", "current_conversions", "previous_conversions"]);
const PERCENT_KEYS = new Set([
  "atc_to_order_rate",
  "conversion_rate",
  "ctr",
  "impression_share",
  "order_share",
  "overlap_rate",
  "outranking_share",
  "position_above_rate",
  "revenue_share",
  "spend_share",
  "view_to_atc_rate",
  "view_to_order_rate",
  "value_share",
]);
const RATIO_KEYS = new Set(["roas", "current_roas", "previous_roas"]);
const DATE_KEYS = new Set(["report_date", "report_date_end", "report_date_start", "bucket_date"]);
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
    showTopMeta: false,
    showFooterCount: true,
    topbarFilters: [
      {
        inputId: "keywords-issue-filter",
        key: "audit_reason",
        options: [
          { value: "", label: "All issues" },
          { value: "low_qs", label: "Low QS" },
          { value: "intent_or_offer", label: "Intent / offer" },
          { value: "low_volume", label: "Low volume" },
          { value: "scale_but_fix_qs", label: "Scale / fix QS" },
          { value: "ok", label: "OK" },
        ],
      },
    ],
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
    searchExcludeInputId: "search-terms-search-exclude",
    searchFields: ["search_term", "campaign_name", "ad_group_name", "search_term_status", "search_term_match_type"],
    extraFilterInputIds: [
      "search-terms-search-exclude",
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
    showSummaryRow: false,
    showFooterCount: true,
    showTopMeta: false,
    topbarFilter: {
      inputId: "alerts-severity-filter",
      key: "severity",
      options: [
        { value: "", label: "All severities" },
        { value: "high", label: "High only" },
        { value: "medium", label: "Medium only" },
        { value: "low", label: "Low only" },
      ],
    },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_type", label: "Type" },
      { key: "alert_message", label: "Message", format: formatAlertMessage },
    ],
  },
  keywordAlerts: {
    searchInputId: null,
    searchFields: ["report_date", "severity", "alert_message"],
    containerId: "alerts-table",
    defaultSort: { key: "report_date", direction: "desc" },
    showSummaryRow: false,
    showFooterCount: true,
    showTopMeta: false,
    topbarFilter: {
      inputId: "keyword-alert-severity-filter",
      key: "severity",
      options: [
        { value: "", label: "All severities" },
        { value: "high", label: "High only" },
        { value: "medium", label: "Medium only" },
        { value: "low", label: "Low only" },
      ],
    },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_message", label: "Message", format: formatAlertMessage },
    ],
  },
  daypart: {
    searchInputId: null,
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
    searchInputId: null,
    searchFields: ["campaign_name", "ad_group_name", "daypart"],
    containerId: "daypart-groups-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
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
    topbarFilter: {
      inputId: "budget-flag-filter",
      key: "budget_exhausted_flag",
      options: [
        { value: "", label: "All flags" },
        { value: "true", label: "Flagged only" },
        { value: "false", label: "Not flagged" },
      ],
    },
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
    showSummaryRow: false,
    showTopMeta: false,
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
    showSummaryRow: false,
    showTopMeta: false,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
    columns: buildDeltaColumns("Campaign"),
  },
  campaignLosers: {
    searchInputId: "campaign-losers-search",
    searchFields: ["campaign_name"],
    containerId: "campaign-losers-table",
    defaultSort: { key: "value_delta_eur", direction: "asc" },
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
    columns: buildDeltaColumns("Campaign"),
  },
  campaignConcentration: {
    searchInputId: "campaign-concentration-search",
    searchFields: ["campaign_name"],
    containerId: "campaign-concentration-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "roas", label: "ROAS", format: formatRatio },
      { key: "spend_share", label: "Spend share", format: formatPercent },
      { key: "value_share", label: "Value share", format: formatPercent },
    ],
  },
  coverageOpportunities: {
    searchInputId: "coverage-opportunities-search",
    searchFields: ["campaign_name", "ad_group_name", "search_term", "search_term_status"],
    containerId: "coverage-opportunities-table",
    defaultSort: { key: "conversion_value_eur", direction: "desc" },
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
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
  timingHourMatrix: {
    searchInputId: null,
    searchFields: ["report_date", "day_label"],
    containerId: "timing-hour-matrix-table",
    defaultSort: { key: "report_date", direction: "desc" },
    collapseThreshold: 7,
    showSummaryRow: false,
    showTopMeta: false,
    hideToggleButton: true,
    columns: buildTimingMatrixColumns("conversion_value_eur"),
  },
  hubAlerts: {
    searchInputId: null,
    searchFields: ["report_date", "severity", "alert_category", "alert_message"],
    containerId: "hub-alerts-list",
    defaultSort: { key: "report_date", direction: "desc" },
    collapseThreshold: DEFAULT_VISIBLE_ROWS,
    showSummaryRow: false,
    showFooterCount: true,
    showTopMeta: false,
    topbarFilters: [
      {
        inputId: "hub-alert-severity-filter",
        key: "severity",
        options: [
          { value: "", label: "All severities" },
          { value: "high", label: "High only" },
          { value: "medium", label: "Medium only" },
          { value: "low", label: "Low only" },
        ],
      },
      {
        inputId: "hub-alert-category-filter",
        key: "alert_category",
        options: [
          { value: "", label: "All categories" },
          { value: "performance", label: "Performance" },
          { value: "budget", label: "Budget / pacing" },
          { value: "intent_offer", label: "Intent / offer" },
          { value: "quality_score", label: "Quality score" },
          { value: "low_volume", label: "Low volume" },
          { value: "scale_opportunity", label: "Scale / fix QS" },
          { value: "keyword_other", label: "Other keyword issues" },
        ],
      },
    ],
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_category_label", label: "Category" },
      { key: "alert_message", label: "Message", format: formatAlertMessage },
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

function buildTimingMatrixColumns(metricKey) {
  const metric = TIMING_MATRIX_METRICS[metricKey] || TIMING_MATRIX_METRICS.conversion_value_eur;
  return [
    { key: "day_label", label: "Date", format: formatTimingMatrixDateLabel },
    ...Array.from({ length: 24 }, (_, hour) => ({
      key: `h${String(hour).padStart(2, "0")}`,
      label: String(hour),
      format: metric.formatter,
      heatmap: true,
    })),
  ];
}

function getDatePresetRange(preset) {
  const anchorIso = getDatePresetAnchor();
  if (!anchorIso) {
    return null;
  }

  const anchor = parseIsoDate(anchorIso);
  let start;
  let end;

  if (preset === "last_7_days") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), anchor.getUTCDate() - 6));
    end = anchor;
  } else if (preset === "last_14_days") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), anchor.getUTCDate() - 13));
    end = anchor;
  } else if (preset === "last_30_days") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), anchor.getUTCDate() - 29));
    end = anchor;
  } else if (preset === "current_month") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 1));
    end = anchor;
  } else if (preset === "past_month") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() - 1, 1));
    end = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 0));
  } else if (preset === "ytd") {
    start = new Date(Date.UTC(anchor.getUTCFullYear(), 0, 1));
    end = anchor;
  } else {
    return null;
  }

  return {
    date_from: toIsoDate(start),
    date_to: toIsoDate(end),
  };
}

function getDatePresetAnchor() {
  const options = state.options;
  if (!options) {
    return null;
  }

  const clientId = document.getElementById("client-select")?.value || "";
  const accountId = document.getElementById("account-select")?.value || "";
  const accounts = options.accounts || [];
  let relevantAccounts = accounts;

  if (accountId) {
    relevantAccounts = accounts.filter((account) => account.account_id === accountId);
  } else if (clientId) {
    relevantAccounts = accounts.filter((account) => account.client_id === clientId);
  }

  const scopedMaxDate = relevantAccounts.reduce((latest, account) => {
    if (!account.max_report_date) {
      return latest;
    }
    if (!latest || account.max_report_date > latest) {
      return account.max_report_date;
    }
    return latest;
  }, "");

  return scopedMaxDate || options.date_bounds?.max_report_date || options.defaults?.date_to || null;
}

function detectDatePreset(dateFrom, dateTo) {
  if (!isIsoDateString(dateFrom) || !isIsoDateString(dateTo)) {
    return DATE_PRESET_CUSTOM;
  }

  const presetKeys = ["last_7_days", "last_14_days", "last_30_days", "current_month", "past_month", "ytd"];
  for (const preset of presetKeys) {
    const range = getDatePresetRange(preset);
    if (range && range.date_from === dateFrom && range.date_to === dateTo) {
      return preset;
    }
  }
  return DATE_PRESET_CUSTOM;
}

function syncDatePresetSelection() {
  const presetSelect = document.getElementById("date-preset-select");
  const dateFromInput = document.getElementById("date-from-input");
  const dateToInput = document.getElementById("date-to-input");
  if (!presetSelect || !dateFromInput || !dateToInput) {
    return;
  }
  presetSelect.value = detectDatePreset(dateFromInput.value.trim(), dateToInput.value.trim());
}

function applyDatePreset(preset, options = {}) {
  const dateFromInput = document.getElementById("date-from-input");
  const dateToInput = document.getElementById("date-to-input");
  const presetSelect = document.getElementById("date-preset-select");
  if (!dateFromInput || !dateToInput || !presetSelect) {
    return false;
  }

  if (!preset || preset === DATE_PRESET_CUSTOM) {
    presetSelect.value = DATE_PRESET_CUSTOM;
    return false;
  }

  const range = getDatePresetRange(preset);
  if (!range) {
    presetSelect.value = DATE_PRESET_CUSTOM;
    return false;
  }

  dateFromInput.value = range.date_from;
  dateToInput.value = range.date_to;
  clearValidatedInputError("date-from-input");
  clearValidatedInputError("date-to-input");
  if (options.syncSelection !== false) {
    presetSelect.value = preset;
  }
  return true;
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
    state.overviewCampaignSelection = [];
    state.overviewCampaignSearch = "";
    state.timingCampaignSelection = [];
    state.timingCampaignSearch = "";
    state.timingAdGroupSelection = [];
    state.timingAdGroupSearch = "";
    syncAccountOptions();
    if (state.options.defaults.account_id) {
      document.getElementById("account-select").value = state.options.defaults.account_id;
    }
    syncFeatureFlags();
    syncDatePresetSelection();
    updateReportLinks();
    await refreshCurrentPage();
  });

  document.getElementById("client-select").addEventListener("change", () => {
    state.overviewCampaignSelection = [];
    state.overviewCampaignSearch = "";
    state.timingCampaignSelection = [];
    state.timingCampaignSearch = "";
    state.timingAdGroupSelection = [];
    state.timingAdGroupSearch = "";
    syncAccountOptions();
    syncFeatureFlags();
    applyDatePreset(document.getElementById("date-preset-select")?.value || DATE_PRESET_CUSTOM, { syncSelection: false });
    syncDatePresetSelection();
    updateReportLinks();
  });

  document.getElementById("account-select").addEventListener("change", () => {
    state.overviewCampaignSelection = [];
    state.overviewCampaignSearch = "";
    state.timingCampaignSelection = [];
    state.timingCampaignSearch = "";
    state.timingAdGroupSelection = [];
    state.timingAdGroupSearch = "";
    syncFeatureFlags();
    applyDatePreset(document.getElementById("date-preset-select")?.value || DATE_PRESET_CUSTOM, { syncSelection: false });
    syncDatePresetSelection();
    updateReportLinks();
  });
  document.getElementById("date-preset-select").addEventListener("change", () => {
    if (applyDatePreset(document.getElementById("date-preset-select").value)) {
      updateReportLinks();
      return;
    }
    updateReportLinks();
  });
  ["date-from-input", "date-to-input"].forEach((inputId) => {
    document.getElementById(inputId).addEventListener("change", () => {
      clearValidatedInputError(inputId);
      syncDatePresetSelection();
      updateReportLinks();
    });
  });
}

function bindPageSpecificEvents() {
  ["hour-metric-select", "weekday-metric-select"].forEach((id) => {
    const input = document.getElementById(id);
    if (input && input.dataset.bound !== "true") {
      input.addEventListener("change", () => {
        if (REPORT_KIND === "timing" && state.currentPayload) {
          renderTimingCharts(state.currentPayload);
          renderTimingMatrix(state.currentPayload);
        }
      });
      input.dataset.bound = "true";
    }
  });

  const timingMatrixSelect = document.getElementById("timing-matrix-metric-select");
  if (timingMatrixSelect && timingMatrixSelect.dataset.bound !== "true") {
    timingMatrixSelect.addEventListener("change", () => {
      if (REPORT_KIND === "timing" && state.currentPayload) {
        renderTimingMatrix(state.currentPayload);
      }
    });
    timingMatrixSelect.dataset.bound = "true";
  }

  const timingMatrixDaysSelect = document.getElementById("timing-matrix-days-select");
  if (timingMatrixDaysSelect && timingMatrixDaysSelect.dataset.bound !== "true") {
    timingMatrixDaysSelect.addEventListener("change", () => {
      refreshTimingMatrixOnly().catch(renderGlobalError);
    });
    timingMatrixDaysSelect.dataset.bound = "true";
  }

  [
    "hub-trend-grain",
    "hub-top-primary-metric",
    "hub-top-secondary-metric",
    "hub-top-compare-metric",
    "hub-bottom-primary-metric",
    "hub-bottom-secondary-metric",
    "hub-bottom-compare-metric",
    "overview-trend-grain",
    "overview-top-primary-metric",
    "overview-top-secondary-metric",
    "overview-top-compare-metric",
    "overview-bottom-primary-metric",
    "overview-bottom-secondary-metric",
    "overview-bottom-compare-metric",
  ].forEach((id) => {
    const input = document.getElementById(id);
  if (input && input.dataset.bound !== "true") {
      input.addEventListener("change", () => {
        if (PAGE_KIND === "hub" && state.currentPayload) {
          renderHubTrendCharts(state.currentPayload);
        } else if (REPORT_KIND === "overview" && state.currentPayload) {
          renderOverviewTrendCharts(state.currentPayload);
        }
      });
      input.dataset.bound = "true";
    }
  });

  bindOverviewCampaignFilterEvents();
  bindTimingCampaignFilterEvents();
  bindTimingAdGroupFilterEvents();
}

function bindOverviewCampaignFilterEvents() {
  const toggle = document.getElementById("campaign-filter-toggle");
  const panel = document.getElementById("campaign-filter-panel");
  const searchInput = document.getElementById("campaign-filter-search");
  const clearButton = document.getElementById("campaign-filter-clear");
  const closeButton = document.getElementById("campaign-filter-close");
  const optionsContainer = document.getElementById("campaign-filter-options");

  if (!toggle || !panel || !searchInput || !clearButton || !closeButton || !optionsContainer) {
    return;
  }

  const selectionSignature = () => normalizeSelectionSignature(getSelectedOverviewCampaigns());
  const closePanel = (applySelection = false) => {
    const shouldRefresh = applySelection && panel.dataset.selectionSignature !== selectionSignature();
    panel.classList.add("is-hidden");
    toggle.classList.remove("is-open");
    if (shouldRefresh) {
      panel.dataset.selectionSignature = selectionSignature();
      refreshCurrentPage().catch(renderGlobalError);
    }
  };

  if (toggle.dataset.bound !== "true") {
    toggle.addEventListener("click", () => {
      const isOpening = panel.classList.contains("is-hidden");
      if (isOpening) {
        panel.dataset.selectionSignature = selectionSignature();
        panel.classList.remove("is-hidden");
        toggle.classList.add("is-open");
        searchInput.focus();
      } else {
        closePanel(true);
      }
    });
    toggle.dataset.bound = "true";
  }

  if (searchInput.dataset.bound !== "true") {
    searchInput.addEventListener("input", () => {
      state.overviewCampaignSearch = searchInput.value.trim();
      renderOverviewCampaignOptions();
    });
    searchInput.dataset.bound = "true";
  }

  if (clearButton.dataset.bound !== "true") {
    clearButton.addEventListener("click", () => {
      state.overviewCampaignSelection = [];
      state.overviewCampaignSearch = "";
      searchInput.value = "";
      renderOverviewCampaignSelector(state.overviewCampaignOptions);
      updateReportLinks();
    });
    clearButton.dataset.bound = "true";
  }

  if (closeButton.dataset.bound !== "true") {
    closeButton.addEventListener("click", () => {
      closePanel(true);
    });
    closeButton.dataset.bound = "true";
  }

  if (optionsContainer.dataset.bound !== "true") {
    optionsContainer.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
        return;
      }
      if (target.checked) {
        state.overviewCampaignSelection = [...new Set([...state.overviewCampaignSelection, target.value])];
      } else {
        state.overviewCampaignSelection = state.overviewCampaignSelection.filter((value) => value !== target.value);
      }
      renderOverviewCampaignToggleLabel();
      updateReportLinks();
    });
    optionsContainer.dataset.bound = "true";
  }

  if (panel.dataset.boundOutside !== "true") {
    document.addEventListener("click", (event) => {
      if (panel.classList.contains("is-hidden")) {
        return;
      }
      if (panel.contains(event.target) || toggle.contains(event.target)) {
        return;
      }
      closePanel(true);
    });
    panel.dataset.boundOutside = "true";
  }
}

function renderOverviewCampaignSelector(campaignNames) {
  const toggle = document.getElementById("campaign-filter-toggle");
  const panel = document.getElementById("campaign-filter-panel");
  const searchInput = document.getElementById("campaign-filter-search");
  if (!toggle || !panel || !searchInput) {
    return;
  }
  const mergedOptions = [...new Set([...(campaignNames || []), ...state.overviewCampaignSelection])];
  state.overviewCampaignOptions = mergedOptions.slice(0, Math.max(10, mergedOptions.length));
  searchInput.value = state.overviewCampaignSearch;
  panel.dataset.selectionSignature = normalizeSelectionSignature(getSelectedOverviewCampaigns());
  renderOverviewCampaignToggleLabel();
  renderOverviewCampaignOptions();
}

function bindTimingCampaignFilterEvents() {
  const toggle = document.getElementById("timing-campaign-filter-toggle");
  const panel = document.getElementById("timing-campaign-filter-panel");
  const searchInput = document.getElementById("timing-campaign-filter-search");
  const clearButton = document.getElementById("timing-campaign-filter-clear");
  const closeButton = document.getElementById("timing-campaign-filter-close");
  const optionsContainer = document.getElementById("timing-campaign-filter-options");

  if (!toggle || !panel || !searchInput || !clearButton || !closeButton || !optionsContainer) {
    return;
  }

  const selectionSignature = () => normalizeSelectionSignature(getSelectedTimingCampaigns());
  const closePanel = (applySelection = false) => {
    const shouldRerender = applySelection && panel.dataset.selectionSignature !== selectionSignature();
    panel.classList.add("is-hidden");
    toggle.classList.remove("is-open");
    if (shouldRerender) {
      panel.dataset.selectionSignature = selectionSignature();
      renderTable("daypartGroups", state.tableData.get("daypartGroups") || []);
    }
  };

  if (toggle.dataset.bound !== "true") {
    toggle.addEventListener("click", () => {
      const isOpening = panel.classList.contains("is-hidden");
      if (isOpening) {
        panel.dataset.selectionSignature = selectionSignature();
        panel.classList.remove("is-hidden");
        toggle.classList.add("is-open");
        searchInput.focus();
      } else {
        closePanel(true);
      }
    });
    toggle.dataset.bound = "true";
  }

  if (searchInput.dataset.bound !== "true") {
    searchInput.addEventListener("input", () => {
      state.timingCampaignSearch = searchInput.value.trim();
      renderTimingCampaignOptions();
    });
    searchInput.dataset.bound = "true";
  }

  if (clearButton.dataset.bound !== "true") {
    clearButton.addEventListener("click", () => {
      state.timingCampaignSelection = [];
      state.timingCampaignSearch = "";
      searchInput.value = "";
      renderTimingCampaignSelector(state.tableData.get("daypartGroups") || []);
      renderTimingAdGroupSelector(state.tableData.get("daypartGroups") || []);
    });
    clearButton.dataset.bound = "true";
  }

  if (closeButton.dataset.bound !== "true") {
    closeButton.addEventListener("click", () => {
      closePanel(true);
    });
    closeButton.dataset.bound = "true";
  }

  if (optionsContainer.dataset.bound !== "true") {
    optionsContainer.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
        return;
      }
      if (target.checked) {
        state.timingCampaignSelection = [...new Set([...state.timingCampaignSelection, target.value])];
      } else {
        state.timingCampaignSelection = state.timingCampaignSelection.filter((value) => value !== target.value);
      }
      renderTimingCampaignToggleLabel();
      renderTimingAdGroupSelector(state.tableData.get("daypartGroups") || []);
    });
    optionsContainer.dataset.bound = "true";
  }

  if (panel.dataset.boundOutside !== "true") {
    document.addEventListener("click", (event) => {
      if (panel.classList.contains("is-hidden")) {
        return;
      }
      if (panel.contains(event.target) || toggle.contains(event.target)) {
        return;
      }
      closePanel(true);
    });
    panel.dataset.boundOutside = "true";
  }
}

function renderTimingCampaignSelector(rows) {
  const toggle = document.getElementById("timing-campaign-filter-toggle");
  const panel = document.getElementById("timing-campaign-filter-panel");
  const searchInput = document.getElementById("timing-campaign-filter-search");
  if (!toggle || !panel || !searchInput) {
    return;
  }
  const spendByCampaign = new Map();
  (rows || []).forEach((row) => {
    if (!row?.campaign_name) {
      return;
    }
    spendByCampaign.set(
      row.campaign_name,
      (spendByCampaign.get(row.campaign_name) || 0) + Number(row.cost_eur || 0),
    );
  });
  const sortedCampaigns = [...spendByCampaign.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], undefined, { sensitivity: "base" }))
    .map(([campaignName]) => campaignName);
  const mergedOptions = [...new Set([...sortedCampaigns, ...state.timingCampaignSelection])];
  state.timingCampaignOptions = mergedOptions;
  searchInput.value = state.timingCampaignSearch;
  panel.dataset.selectionSignature = normalizeSelectionSignature(getSelectedTimingCampaigns());
  renderTimingCampaignToggleLabel();
  renderTimingCampaignOptions();
}

function renderTimingCampaignToggleLabel() {
  const toggle = document.getElementById("timing-campaign-filter-toggle");
  if (!toggle) {
    return;
  }
  const count = getSelectedTimingCampaigns().length;
  toggle.textContent = count ? `${count} campaign${count === 1 ? "" : "s"} selected` : "All campaigns";
}

function renderTimingCampaignOptions() {
  const container = document.getElementById("timing-campaign-filter-options");
  if (!container) {
    return;
  }
  const query = state.timingCampaignSearch || "";
  let options = state.timingCampaignOptions;
  if (query) {
    const pattern = compileRegex(query, "timing-campaign-filter-search");
    if (!pattern) {
      container.innerHTML = '<div class="empty-state">The campaign search is not a valid regular expression.</div>';
      return;
    }
    options = options.filter((campaignName) => pattern.test(campaignName));
  } else {
    clearInputError("timing-campaign-filter-search");
  }

  if (!options.length) {
    container.innerHTML = '<div class="empty-state">No campaign names match the current filter.</div>';
    return;
  }

  const selected = new Set(getSelectedTimingCampaigns());
  container.innerHTML = options.map((campaignName) => `
    <label class="campaign-filter-option">
      <input type="checkbox" value="${escapeHtml(campaignName)}"${selected.has(campaignName) ? " checked" : ""}>
      <span>${escapeHtml(campaignName)}</span>
    </label>
  `).join("");
}

function getSelectedTimingCampaigns() {
  return Array.isArray(state.timingCampaignSelection) ? state.timingCampaignSelection : [];
}

function bindTimingAdGroupFilterEvents() {
  const toggle = document.getElementById("timing-adgroup-filter-toggle");
  const panel = document.getElementById("timing-adgroup-filter-panel");
  const searchInput = document.getElementById("timing-adgroup-filter-search");
  const clearButton = document.getElementById("timing-adgroup-filter-clear");
  const closeButton = document.getElementById("timing-adgroup-filter-close");
  const optionsContainer = document.getElementById("timing-adgroup-filter-options");

  if (!toggle || !panel || !searchInput || !clearButton || !closeButton || !optionsContainer) {
    return;
  }

  const selectionSignature = () => normalizeSelectionSignature(getSelectedTimingAdGroups());
  const closePanel = (applySelection = false) => {
    const shouldRerender = applySelection && panel.dataset.selectionSignature !== selectionSignature();
    panel.classList.add("is-hidden");
    toggle.classList.remove("is-open");
    if (shouldRerender) {
      panel.dataset.selectionSignature = selectionSignature();
      renderTable("daypartGroups", state.tableData.get("daypartGroups") || []);
    }
  };

  if (toggle.dataset.bound !== "true") {
    toggle.addEventListener("click", () => {
      const isOpening = panel.classList.contains("is-hidden");
      if (isOpening) {
        panel.dataset.selectionSignature = selectionSignature();
        panel.classList.remove("is-hidden");
        toggle.classList.add("is-open");
        searchInput.focus();
      } else {
        closePanel(true);
      }
    });
    toggle.dataset.bound = "true";
  }

  if (searchInput.dataset.bound !== "true") {
    searchInput.addEventListener("input", () => {
      state.timingAdGroupSearch = searchInput.value.trim();
      renderTimingAdGroupOptions();
    });
    searchInput.dataset.bound = "true";
  }

  if (clearButton.dataset.bound !== "true") {
    clearButton.addEventListener("click", () => {
      state.timingAdGroupSelection = [];
      state.timingAdGroupSearch = "";
      searchInput.value = "";
      renderTimingAdGroupSelector(state.tableData.get("daypartGroups") || []);
    });
    clearButton.dataset.bound = "true";
  }

  if (closeButton.dataset.bound !== "true") {
    closeButton.addEventListener("click", () => {
      closePanel(true);
    });
    closeButton.dataset.bound = "true";
  }

  if (optionsContainer.dataset.bound !== "true") {
    optionsContainer.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
        return;
      }
      if (target.checked) {
        state.timingAdGroupSelection = [...new Set([...state.timingAdGroupSelection, target.value])];
      } else {
        state.timingAdGroupSelection = state.timingAdGroupSelection.filter((value) => value !== target.value);
      }
      renderTimingAdGroupToggleLabel();
    });
    optionsContainer.dataset.bound = "true";
  }

  if (panel.dataset.boundOutside !== "true") {
    document.addEventListener("click", (event) => {
      if (panel.classList.contains("is-hidden")) {
        return;
      }
      if (panel.contains(event.target) || toggle.contains(event.target)) {
        return;
      }
      closePanel(true);
    });
    panel.dataset.boundOutside = "true";
  }
}

function renderTimingAdGroupSelector(rows) {
  const toggle = document.getElementById("timing-adgroup-filter-toggle");
  const panel = document.getElementById("timing-adgroup-filter-panel");
  const searchInput = document.getElementById("timing-adgroup-filter-search");
  if (!toggle || !panel || !searchInput) {
    return;
  }
  const selectedCampaigns = getSelectedTimingCampaigns();
  const scopedRows = selectedCampaigns.length
    ? (rows || []).filter((row) => selectedCampaigns.includes(row.campaign_name))
    : (rows || []);
  const spendByAdGroup = new Map();
  scopedRows.forEach((row) => {
    if (!row?.ad_group_name) {
      return;
    }
    spendByAdGroup.set(
      row.ad_group_name,
      (spendByAdGroup.get(row.ad_group_name) || 0) + Number(row.cost_eur || 0),
    );
  });
  const sortedAdGroups = [...spendByAdGroup.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], undefined, { sensitivity: "base" }))
    .map(([adGroupName]) => adGroupName);
  const allowedSet = new Set(sortedAdGroups);
  state.timingAdGroupSelection = getSelectedTimingAdGroups().filter((adGroupName) => allowedSet.has(adGroupName));
  const mergedOptions = [...new Set([...sortedAdGroups, ...state.timingAdGroupSelection])];
  state.timingAdGroupOptions = mergedOptions;
  searchInput.value = state.timingAdGroupSearch;
  panel.dataset.selectionSignature = normalizeSelectionSignature(getSelectedTimingAdGroups());
  renderTimingAdGroupToggleLabel();
  renderTimingAdGroupOptions();
}

function renderTimingAdGroupToggleLabel() {
  const toggle = document.getElementById("timing-adgroup-filter-toggle");
  if (!toggle) {
    return;
  }
  const count = getSelectedTimingAdGroups().length;
  toggle.textContent = count ? `${count} ad group${count === 1 ? "" : "s"} selected` : "All ad groups";
}

function renderTimingAdGroupOptions() {
  const container = document.getElementById("timing-adgroup-filter-options");
  if (!container) {
    return;
  }
  const query = state.timingAdGroupSearch || "";
  let options = state.timingAdGroupOptions;
  if (query) {
    const pattern = compileRegex(query, "timing-adgroup-filter-search");
    if (!pattern) {
      container.innerHTML = '<div class="empty-state">The ad group search is not a valid regular expression.</div>';
      return;
    }
    options = options.filter((adGroupName) => pattern.test(adGroupName));
  } else {
    clearInputError("timing-adgroup-filter-search");
  }

  if (!options.length) {
    container.innerHTML = '<div class="empty-state">No ad groups match the current filter.</div>';
    return;
  }

  const selected = new Set(getSelectedTimingAdGroups());
  container.innerHTML = options.map((adGroupName) => `
    <label class="campaign-filter-option">
      <input type="checkbox" value="${escapeHtml(adGroupName)}"${selected.has(adGroupName) ? " checked" : ""}>
      <span>${escapeHtml(adGroupName)}</span>
    </label>
  `).join("");
}

function getSelectedTimingAdGroups() {
  return Array.isArray(state.timingAdGroupSelection) ? state.timingAdGroupSelection : [];
}

function renderOverviewCampaignToggleLabel() {
  const toggle = document.getElementById("campaign-filter-toggle");
  if (!toggle) {
    return;
  }
  const count = getSelectedOverviewCampaigns().length;
  toggle.textContent = count ? `${count} campaign${count === 1 ? "" : "s"} selected` : "All top campaigns";
}

function renderOverviewCampaignOptions() {
  const container = document.getElementById("campaign-filter-options");
  if (!container) {
    return;
  }
  const query = state.overviewCampaignSearch || "";
  let options = state.overviewCampaignOptions;
  if (query) {
    const pattern = compileRegex(query, "campaign-filter-search");
    if (!pattern) {
      container.innerHTML = '<div class="empty-state">The campaign search is not a valid regular expression.</div>';
      return;
    }
    options = options.filter((campaignName) => pattern.test(campaignName));
  } else {
    clearInputError("campaign-filter-search");
  }

  if (!options.length) {
    container.innerHTML = '<div class="empty-state">No campaign names match the current filter.</div>';
    return;
  }

  const selected = new Set(getSelectedOverviewCampaigns());
  container.innerHTML = options.map((campaignName) => `
    <label class="campaign-filter-option">
      <input type="checkbox" value="${escapeHtml(campaignName)}"${selected.has(campaignName) ? " checked" : ""}>
      <span>${escapeHtml(campaignName)}</span>
    </label>
  `).join("");
}

function getSelectedOverviewCampaigns() {
  return Array.isArray(state.overviewCampaignSelection) ? state.overviewCampaignSelection : [];
}

function buildExactCampaignRegex(campaignNames) {
  return `^(${campaignNames.map((name) => escapeRegex(name)).join("|")})$`;
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeSelectionSignature(values) {
  return [...new Set(values || [])].sort().join("\u0001");
}

function showLoadingState() {
  if (document.getElementById("kpi-grid")) {
    document.getElementById("kpi-grid").innerHTML = '<div class="loading-state">Loading metrics</div>';
  }
  [
    "trend-chart",
    "trend-secondary-chart",
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
    "timing-hour-matrix-table",
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
  state.overviewCampaignSelection = urlFilters.campaign_names || [];
  state.overviewCampaignSearch = "";
  syncFeatureFlags();
  syncDatePresetSelection();
  updateReportLinks();
}

function readFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    client_id: params.get("client_id") || undefined,
    account_id: params.get("account_id") || undefined,
    date_from: params.get("date_from") || undefined,
    date_to: params.get("date_to") || undefined,
    campaign_names: params.getAll("campaign_name"),
    campaign_regex: params.get("campaign_regex") || undefined,
  };
}

function applyFilterDefaults(defaults) {
  document.getElementById("client-select").value = defaults.client_id || "";
  document.getElementById("date-from-input").value = defaults.date_from || "";
  document.getElementById("date-to-input").value = defaults.date_to || "";
}

function syncFeatureFlags() {
  const clientSelect = document.getElementById("client-select");
  const accountSelect = document.getElementById("account-select");
  if (!clientSelect || !accountSelect) {
    return;
  }

  const clientId = clientSelect.value;
  const accountId = accountSelect.value;
  const accounts = state.options?.accounts || [];
  const relevantAccounts = accounts.filter((account) => {
    if (accountId) return account.account_id === accountId;
    if (clientId) return account.client_id === clientId;
    return true;
  });

  const activeFeatures = {
    has_ga4: relevantAccounts.some((account) => account.has_ga4),
    has_auction_insights: relevantAccounts.some((account) => account.has_auction_insights),
  };

  document.querySelectorAll("[data-feature]").forEach((link) => {
    const feature = link.dataset.feature;
    link.style.display = activeFeatures[feature] ? "" : "none";
  });
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
  const dateFrom = document.getElementById("date-from-input").value.trim();
  const dateTo = document.getElementById("date-to-input").value.trim();
  if (clientId) {
    params.set("client_id", clientId);
  }
  if (accountId) {
    params.set("account_id", accountId);
  }
  if (isIsoDateString(dateFrom)) {
    params.set("date_from", dateFrom);
  }
  if (isIsoDateString(dateTo)) {
    params.set("date_to", dateTo);
  }
  const selectedCampaigns = REPORT_KIND === "overview" ? getSelectedOverviewCampaigns() : [];
  selectedCampaigns.forEach((campaignName) => params.append("campaign_name", campaignName));
  return params;
}

function currentApiQuery() {
  const params = currentFilterQuery();
  const selectedCampaigns = REPORT_KIND === "overview" ? getSelectedOverviewCampaigns() : [];
  const campaignRegex = selectedCampaigns.length
    ? buildExactCampaignRegex(selectedCampaigns)
    : document.getElementById("campaign-regex-input")?.value.trim() || "";
  if (campaignRegex) {
    params.set("campaign_regex", campaignRegex);
  }
  if (REPORT_KIND === "timing") {
    const timingMatrixDays = document.getElementById("timing-matrix-days-select")?.value;
    if (timingMatrixDays) {
      params.set("timing_matrix_days", timingMatrixDays);
    }
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

  const freshnessPromise = fetchFreshness(currentFilterQuery());
  const params = currentApiQuery();
  const endpoint = PAGE_KIND === "hub"
    ? `/api/hub?${params.toString()}`
    : `/api/reports/${REPORT_KIND}?${params.toString()}`;
  const payload = await fetchJson(endpoint);
  const freshness = await freshnessPromise;
  state.currentPayload = payload;
  state.currentFreshness = freshness;
  renderFreshness(freshness);

  renderScope(payload.scope, payload.summary);
  renderKpis(payload.summary, payload.previous_summary, KPI_DEFS);

  if (PAGE_KIND === "hub") {
    renderHub(payload);
    return;
  }

  if (REPORT_KIND === "overview") {
    renderOverviewCampaignSelector(payload.campaign_filter_options || []);
    renderCompetitionNote(payload.competition_note || "", payload.competition || []);
    renderStatusCards(payload.status_cards || [], "status-card-grid");
    renderOverviewTrendCharts(payload);
    renderTable("campaigns", payload.campaigns || []);
    renderTable("competition", payload.competition || []);
    return;
  }

  if (REPORT_KIND === "keywords") {
    renderNote("keyword-alerts-note", payload.alerts_definition);
    renderTable("keywords", payload.keywords || []);
    renderTable("searchTerms", payload.search_terms || []);
    renderTable("keywordAlerts", payload.alerts || []);
    return;
  }

  if (REPORT_KIND === "timing") {
    renderInsights(payload.timing_highlights || [], "timing-highlights");
    renderNote("budget-definition-note", payload.budget_flags_definition);
    renderTimingCharts(payload);
    renderTimingMatrix(payload);
    renderTimingCampaignSelector(payload.daypart_ad_groups || []);
    renderTimingAdGroupSelector(payload.daypart_ad_groups || []);
    renderTable("weekpartComparison", payload.weekpart_comparison || []);
    renderTable("dayWindowComparison", payload.day_window_comparison || []);
    renderTable("daypart", payload.daypart || []);
    renderTable("daypartGroups", payload.daypart_ad_groups || []);
    renderTable("budgetFlags", payload.budget_flags || []);
    return;
  }

  if (REPORT_KIND === "efficiency") {
    resetTableStates([
      "zeroConvCampaigns",
      "zeroConvAdGroups",
      "zeroConvKeywords",
      "zeroConvSearchTerms",
      "campaignWinners",
      "campaignLosers",
      "campaignConcentration",
    ]);
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
    resetTableStates([
      "coverageOpportunities",
      "negativeCandidates",
    ]);
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

async function refreshTimingMatrixOnly() {
  if (REPORT_KIND !== "timing" || !validatePageFilters()) {
    return;
  }

  const container = document.getElementById("timing-hour-matrix-table");
  if (container) {
    container.innerHTML = '<div class="loading-state">Loading data</div>';
  }

  const params = currentApiQuery();
  const payload = await fetchJson(`/api/reports/timing?${params.toString()}`);
  state.currentPayload = {
    ...(state.currentPayload || {}),
    timing_matrices: payload.timing_matrices || {},
    timing_matrix_scope: payload.timing_matrix_scope || null,
  };
  renderTimingMatrix(state.currentPayload);
}

function validatePageFilters() {
  const dateFromInput = document.getElementById("date-from-input");
  const dateToInput = document.getElementById("date-to-input");
  const dateFromValue = dateFromInput?.value.trim() || "";
  const dateToValue = dateToInput?.value.trim() || "";

  if (dateFromInput) {
    dateFromInput.value = dateFromValue;
  }
  if (dateToInput) {
    dateToInput.value = dateToValue;
  }

  if (!validateIsoDateInput("date-from-input", "Date from")) {
    return false;
  }
  if (!validateIsoDateInput("date-to-input", "Date to")) {
    return false;
  }
  if (dateFromValue && dateToValue && dateFromValue > dateToValue) {
    const input = document.getElementById("date-to-input");
    if (input) {
      input.classList.add("is-invalid");
      input.setCustomValidity("Date to must be on or after Date from.");
      input.reportValidity();
    }
    return false;
  }

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

async function fetchFreshness(params) {
  const query = params.toString();
  const endpoint = query ? `/api/freshness?${query}` : "/api/freshness";
  try {
    return await fetchJson(endpoint);
  } catch (_error) {
    return null;
  }
}

function renderHub(payload) {
  renderInsights(payload.management_conclusions || [], "conclusions-grid");
  renderStatusCards(payload.status_cards || [], "status-card-grid");
  renderHubTrendCharts(payload);
  renderTable("hubAlerts", enrichHubAlerts(payload.top_alerts || []));
  renderReportCards(payload.report_cards || []);
}

function enrichHubAlerts(rows) {
  return rows.map((row) => {
    const { category, label } = deriveAlertCategory(row);
    return {
      ...row,
      alert_category: category,
      alert_category_label: label,
    };
  });
}

function deriveAlertCategory(row) {
  const alertType = String(row.alert_type || "").toLowerCase();
  const message = String(row.alert_message || "").toLowerCase();

  if (alertType === "conversion_drop") {
    return { category: "performance", label: "Performance" };
  }
  if (alertType === "budget_exhausted") {
    return { category: "budget", label: "Budget / pacing" };
  }
  if (alertType === "keyword_issue") {
    if (message.includes("intent_or_offer")) {
      return { category: "intent_offer", label: "Intent / offer" };
    }
    if (message.includes("low_qs")) {
      return { category: "quality_score", label: "Quality score" };
    }
    if (message.includes("low_volume")) {
      return { category: "low_volume", label: "Low volume" };
    }
    if (message.includes("scale_but_fix_qs")) {
      return { category: "scale_opportunity", label: "Scale / fix QS" };
    }
    return { category: "keyword_other", label: "Other keyword issues" };
  }

  return { category: "other", label: "Other" };
}

function renderScope(scope, summary) {
  document.getElementById("selected-range-label").textContent = `${formatDate(scope.date_from)} to ${formatDate(scope.date_to)}`;
  document.getElementById("comparison-range-label").textContent = `${formatDate(scope.previous_date_from)} to ${formatDate(scope.previous_date_to)}`;
  document.getElementById("scope-label").textContent = scope.scope_label || scope.account_id || scope.client_id || "All active accounts";
  const start = summary.report_date_start ? formatDate(summary.report_date_start) : formatDate(scope.date_from);
  const end = summary.report_date_end ? formatDate(summary.report_date_end) : formatDate(scope.date_to);
  document.getElementById("coverage-badge").textContent = `${start} to ${end}`;
}

function renderFreshness(freshness) {
  const badge = document.getElementById("freshness-badge");
  const detail = document.getElementById("freshness-detail");
  const banner = document.getElementById("freshness-banner");
  const bannerTitle = document.getElementById("freshness-banner-title");
  const bannerDetail = document.getElementById("freshness-banner-detail");

  if (!badge || !detail || !banner || !bannerTitle || !bannerDetail) {
    return;
  }

  if (!freshness) {
    badge.className = "badge badge-muted";
    badge.textContent = "Freshness unavailable";
    detail.textContent = "Reporting freshness could not be loaded.";
    banner.className = "freshness-banner is-hidden";
    bannerTitle.textContent = "";
    bannerDetail.textContent = "";
    return;
  }

  if (freshness.scope_type === "unscoped") {
    badge.className = "badge badge-muted";
    badge.textContent = "Select an account";
    detail.textContent = "Freshness is shown for the selected account only.";
    banner.className = "freshness-banner is-hidden";
    bannerTitle.textContent = "";
    bannerDetail.textContent = "";
    return;
  }

  const status = String(freshness.freshness_status || "").toLowerCase();
  const statusLabel = {
    ok: "OK",
    stale: "Stale",
    error: "Error",
    backfilling: "Backfilling",
  }[status] || "Unknown";

  badge.className = `badge badge-${status || "muted"}`;
  badge.textContent = statusLabel;

  const detailParts = [];
  if (freshness.last_data_date) {
    detailParts.push(`Last data date ${formatDate(freshness.last_data_date)}`);
  } else {
    detailParts.push("No report data is available yet.");
  }
  if (freshness.hours_since_last_data != null) {
    detailParts.push(`${formatInteger(freshness.hours_since_last_data)} hours since last data`);
  }
  detail.textContent = detailParts.join(" · ");

  if (status === "ok") {
    banner.className = "freshness-banner is-hidden";
    bannerTitle.textContent = "";
    bannerDetail.textContent = "";
    return;
  }

  banner.className = `freshness-banner ${status}`;
  if (status === "stale") {
    bannerTitle.textContent = "Reporting data is stale";
    bannerDetail.textContent = freshness.last_data_date
      ? `The selected account last has reporting data on ${formatDate(freshness.last_data_date)}. The page is still usable, but the numbers are older than expected.`
      : "The selected account is older than expected and should be checked.";
    return;
  }
  if (status === "error") {
    bannerTitle.textContent = "Reporting freshness needs attention";
    bannerDetail.textContent = freshness.last_data_date
      ? `The selected account last has reporting data on ${formatDate(freshness.last_data_date)}. This is beyond the error threshold and likely indicates a pipeline issue.`
      : "Freshness is in an error state for the selected account.";
    return;
  }

  bannerTitle.textContent = "Reporting data is still being prepared";
  bannerDetail.textContent = "This account is active, but report data is not available yet. The initial backfill or onboarding process may still be running.";
}

function renderKpis(summary, previousSummary, defs = KPI_DEFS) {
  const container = document.getElementById("kpi-grid");
  if (!container) {
    return;
  }
  container.innerHTML = defs.map((definition) => {
    const currentValue = summary?.[definition.key];
    const previousValue = previousSummary?.[definition.key];
    const delta = buildDelta(currentValue, previousValue);
    return `
      <article class="kpi-card">
        <p class="kpi-title">${definition.label}</p>
        <div class="kpi-value">${definition.formatter(currentValue)}</div>
        <div class="kpi-delta-row">
          <div class="kpi-delta ${delta.className}">${delta.label}</div>
          <div class="kpi-reference">Prev ${definition.formatter(previousValue)}</div>
        </div>
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

function renderHubTrendCharts(payload) {
  renderControlledTrendCharts(payload, {
    grainId: "hub-trend-grain",
    topPrimaryId: "hub-top-primary-metric",
    topSecondaryId: "hub-top-secondary-metric",
    topCompareId: "hub-top-compare-metric",
    bottomPrimaryId: "hub-bottom-primary-metric",
    bottomSecondaryId: "hub-bottom-secondary-metric",
    bottomCompareId: "hub-bottom-compare-metric",
  });
}

function renderOverviewTrendCharts(payload) {
  renderControlledTrendCharts(payload, {
    grainId: "overview-trend-grain",
    topPrimaryId: "overview-top-primary-metric",
    topSecondaryId: "overview-top-secondary-metric",
    topCompareId: "overview-top-compare-metric",
    bottomPrimaryId: "overview-bottom-primary-metric",
    bottomSecondaryId: "overview-bottom-secondary-metric",
    bottomCompareId: "overview-bottom-compare-metric",
  });
}

function renderControlledTrendCharts(payload, config) {
  const grain = document.getElementById(config.grainId)?.value || "day";
  const currentRows = aggregateTrendRows(payload?.trend || [], grain);
  const previousRows = aggregateTrendRows(payload?.previous_trend || [], grain);
  renderMetricTrendChart(
    "trend-chart",
    currentRows,
    getTrendMetricKeys(config.topPrimaryId, config.topSecondaryId),
    {
      compareMetricKey: getTrendCompareMetric(config.topPrimaryId, config.topSecondaryId, config.topCompareId),
      previousRows,
    },
  );
  renderMetricTrendChart(
    "trend-secondary-chart",
    currentRows,
    getTrendMetricKeys(config.bottomPrimaryId, config.bottomSecondaryId),
    {
      compareMetricKey: getTrendCompareMetric(config.bottomPrimaryId, config.bottomSecondaryId, config.bottomCompareId),
      previousRows,
    },
  );
}

function renderTrendChart(rows, containerId) {
  renderMetricTrendChart(containerId, rows, ["cost_eur", "conversion_value_eur"]);
}

function getTrendMetricKeys(primaryId, secondaryId) {
  const selected = [];
  [primaryId, secondaryId].forEach((id) => {
    const value = document.getElementById(id)?.value;
    if (value && !selected.includes(value)) {
      selected.push(value);
    }
  });
  return selected.slice(0, 2);
}

function getTrendCompareMetric(primaryId, secondaryId, compareId) {
  const mode = document.getElementById(compareId)?.value || "";
  return getTrendCompareMetricFromMode(
    document.getElementById(primaryId)?.value || null,
    document.getElementById(secondaryId)?.value || null,
    mode,
  );
}

function getTrendCompareMetricFromMode(primaryKey, secondaryKey, mode) {
  if (mode === "primary") {
    return primaryKey || null;
  }
  if (mode === "secondary") {
    return secondaryKey || null;
  }
  return null;
}

function renderMetricTrendChart(containerId, rows, metricKeys, options = {}) {
  const host = document.getElementById(containerId);
  if (!host) {
    return;
  }
  const metrics = metricKeys.map((key) => CHART_METRICS[key]).filter(Boolean);
  if (!rows.length || !metrics.length) {
    host.innerHTML = '<div class="empty-state">No trend data in the selected range.</div>';
    return;
  }

  const width = options.width || 1080;
  const height = options.height || 280;
  const padding = {
    top: options.padding?.top ?? 28,
    right: options.padding?.right ?? (metrics[1] ? 78 : 24),
    bottom: options.padding?.bottom ?? 38,
    left: options.padding?.left ?? 78,
  };
  const primaryMetric = metrics[0];
  const secondaryMetric = metrics[1] || null;
  const compareMetric = options.compareMetricKey ? CHART_METRICS[options.compareMetricKey] || null : null;
  const previousRows = Array.isArray(options.previousRows) ? options.previousRows : [];
  const compareSide = compareMetric && secondaryMetric && compareMetric.key === secondaryMetric.key ? "right" : "left";
  const compareSeriesLabel = compareMetric ? `Previous period (${compareMetric.label})` : null;
  const primaryValues = rows.map((row) => Number(row[primaryMetric.key] || 0));
  const compareValues = compareMetric ? previousRows.map((row) => Number(row[compareMetric.key] || 0)) : [];
  const primaryDomain = buildTrendDomain(
    primaryValues,
    compareMetric && compareSide === "left" ? compareValues : [],
  );
  const primaryPoints = buildTrendLinePoints(primaryValues, width, height, padding, primaryDomain);
  const primaryLast = rows[rows.length - 1];

  let secondaryPoints = "";
  let secondaryLastCircle = "";
  let secondaryAxis = "";
  let secondaryDomain = buildTrendDomain([]);
  if (secondaryMetric) {
    const secondaryValues = rows.map((row) => Number(row[secondaryMetric.key] || 0));
    secondaryDomain = buildTrendDomain(
      secondaryValues,
      compareMetric && compareSide === "right" ? compareValues : [],
    );
    secondaryPoints = buildTrendLinePoints(secondaryValues, width, height, padding, secondaryDomain);
    secondaryLastCircle = `
      <circle
        cx="${pointX(secondaryValues.length - 1, secondaryValues.length, width, padding)}"
        cy="${pointYForDomain(Number(primaryLast[secondaryMetric.key] || 0), height, padding, secondaryDomain)}"
        r="5"
        fill="#285e54"
      ></circle>
    `;
    secondaryAxis = buildTrendAxis({
      domain: secondaryDomain,
      formatter: secondaryMetric.formatter,
      side: "right",
      width,
      height,
      padding,
    });
  }

  let comparePoints = "";
  let compareLastCircle = "";
  let compareLegend = "";
  let hoverTargets = "";
  if (compareMetric && compareValues.length) {
    const compareDomain = compareSide === "right" ? secondaryDomain : primaryDomain;
    const compareColor = compareSide === "right" ? "#285e54" : "#bf5a36";
    comparePoints = buildTrendLinePoints(compareValues, width, height, padding, compareDomain);
    compareLastCircle = `
      <circle
        cx="${pointX(compareValues.length - 1, compareValues.length, width, padding)}"
        cy="${pointYForDomain(compareValues[compareValues.length - 1] || 0, height, padding, compareDomain)}"
        r="4"
        fill="${compareColor}"
        opacity="0.55"
      ></circle>
    `;
    compareLegend = `
      <text x="${width - padding.right}" y="${padding.top - 8}" fill="#66766a" font-size="12" text-anchor="end">
        ${escapeHtml(`Previous period (dashed): ${compareMetric.label}`)}
      </text>
    `;
  }
  hoverTargets = buildTrendHoverTargets({
    rows,
    previousRows,
    primaryMetric,
    secondaryMetric,
    compareMetric,
    compareSeriesLabel,
    width,
    height,
    padding,
  });

  host.innerHTML = `
    <div class="trend-tooltip" data-trend-tooltip></div>
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trend chart">
      ${buildGridLines(width, height, padding)}
      ${buildTrendAxis({
        domain: primaryDomain,
        formatter: primaryMetric.formatter,
        side: "left",
        width,
        height,
        padding,
      })}
      ${secondaryAxis}
      ${comparePoints ? `<polyline fill="none" stroke="${compareSide === "right" ? "#285e54" : "#bf5a36"}" stroke-width="3" stroke-dasharray="8 8" opacity="0.55" points="${comparePoints}"></polyline>` : ""}
      <polyline fill="none" stroke="#bf5a36" stroke-width="4" points="${primaryPoints}"></polyline>
      ${secondaryMetric ? `<polyline fill="none" stroke="#285e54" stroke-width="4" points="${secondaryPoints}"></polyline>` : ""}
      <text x="${padding.left}" y="${padding.top - 8}" fill="#66766a" font-size="12">
        ${escapeHtml(secondaryMetric ? `${primaryMetric.label} (left axis) vs ${secondaryMetric.label} (right axis)` : primaryMetric.label)}
      </text>
      ${compareLegend}
      ${buildTrendXAxisLabels(rows, width, height, padding)}
      <circle
        cx="${pointX(primaryValues.length - 1, primaryValues.length, width, padding)}"
        cy="${pointYForDomain(Number(primaryLast[primaryMetric.key] || 0), height, padding, primaryDomain)}"
        r="5"
        fill="#bf5a36"
      ></circle>
      ${secondaryLastCircle}
      ${compareLastCircle}
      ${hoverTargets}
    </svg>
  `;
  bindTrendTooltip(host);
}

function buildTrendAxis({ domain, formatter, side, width, height, padding }) {
  const anchor = side === "left" ? "end" : "start";
  const x = side === "left" ? padding.left - 14 : width - padding.right + 14;
  const values = [domain.max, (domain.max + domain.min) / 2, domain.min];
  const yPositions = [
    padding.top + 4,
    padding.top + ((height - padding.top - padding.bottom) / 2) + 4,
    height - padding.bottom,
  ];

  return values.map((value, index) => `
    <text x="${x}" y="${yPositions[index]}" fill="#66766a" font-size="11" text-anchor="${anchor}">
      ${escapeHtml(stripHtml(formatter(value)))}
    </text>
  `).join("");
}

function renderTimingCharts(payload) {
  const hourMetric = getChartMetric(document.getElementById("hour-metric-select")?.value);
  const weekdayMetric = getChartMetric(document.getElementById("weekday-metric-select")?.value);
  const hourTitle = document.getElementById("hour-chart-title");
  const weekdayTitle = document.getElementById("weekday-chart-title");

  if (hourTitle) {
    hourTitle.textContent = `${hourMetric.label} by hour`;
  }
  if (weekdayTitle) {
    weekdayTitle.textContent = `${weekdayMetric.label} by weekday`;
  }

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

function renderTimingMatrix(payload) {
  const metricKey = document.getElementById("timing-matrix-metric-select")?.value || "conversion_value_eur";
  const selectedDays = Number(document.getElementById("timing-matrix-days-select")?.value || 7);
  const metric = TIMING_MATRIX_METRICS[metricKey] || TIMING_MATRIX_METRICS.conversion_value_eur;
  const title = document.getElementById("timing-matrix-title");
  const note = document.getElementById("timing-matrix-note");
  const rows = payload.timing_matrices?.[metric.key] || [];

  if (title) {
    title.textContent = `${metric.label} by date and hour`;
  }
  if (note) {
    const scope = payload.timing_matrix_scope || {};
    const requestedDays = Number(scope.matrix_requested_days || selectedDays || 7);
    const resolvedDays = Number(scope.matrix_resolved_days ?? rows.length ?? 0);
    note.textContent = scope.matrix_date_from && scope.matrix_date_to
      ? `Shows ${resolvedDays} complete ${resolvedDays === 1 ? "day" : "days"} in scope, from ${formatDate(scope.matrix_date_from)} to ${formatDate(scope.matrix_date_to)}. Selected matrix window: ${requestedDays} days.`
      : `No complete days are available in scope for the selected ${requestedDays}-day matrix window.`;
  }

  TABLE_CONFIG.timingHourMatrix.columns = buildTimingMatrixColumns(metric.key);
  renderTable("timingHourMatrix", rows);
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
  const padding = { top: 26, right: 16, bottom: 48, left: 78 };
  const values = rows.map((row) => Number(row[options.valueKey] || 0));
  const domain = buildBarDomain(values);
  const barSpace = (width - padding.left - padding.right) / rows.length;
  const barWidth = Math.max(Math.min(barSpace * 0.62, 42), 12);

  const bars = rows.map((row, index) => {
    const value = Number(row[options.valueKey] || 0);
    const x = padding.left + index * barSpace + (barSpace - barWidth) / 2;
    const y = pointYForDomain(value, height, padding, domain);
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
      ${buildTrendAxis({
        domain,
        formatter: options.valueFormatter || formatDecimal,
        side: "left",
        width,
        height,
        padding,
      })}
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
  const topbarFilters = config.topbarFilters || (config.topbarFilter ? [config.topbarFilter] : []);
  const topbarFilterHtml = topbarFilters.map((filter) => {
    const selectedValue = document.getElementById(filter.inputId)?.value || "";
    return `
      <select class="table-filter-select" id="${filter.inputId}" data-table-filter="${name}" aria-label="Filter table rows">
        ${filter.options.map((option) => `
          <option value="${escapeHtml(option.value)}"${option.value === selectedValue ? " selected" : ""}>${escapeHtml(option.label)}</option>
        `).join("")}
      </select>
    `;
  }).join("");
  if (filterError) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(filterError)}</div>`;
    return;
  }

  const sortedRows = [...filteredRows].sort((left, right) => compareRows(left, right, tableState.sortKey, tableState.direction));
  if (!sortedRows.length) {
    const emptyTopMetaHtml = config.showTopMeta === false ? "" : '<div class="table-meta">0 filtered rows</div>';
    const hasEmptyTopbarContent = Boolean(emptyTopMetaHtml || topbarFilterHtml);
    container.innerHTML = `
      ${hasEmptyTopbarContent ? `
      <div class="table-topbar">
        ${emptyTopMetaHtml}
        <div class="table-actions">
          ${topbarFilterHtml}
        </div>
      </div>` : ""}
      <div class="empty-state">No rows for the selected range.</div>
    `;
    bindTableInteractions(name);
    return;
  }

  const collapseThreshold = config.collapseThreshold || DEFAULT_VISIBLE_ROWS;
  const isCollapsible = sortedRows.length > collapseThreshold;
  const expanded = isCollapsible ? tableState.expanded : true;
  const metaLabel = expanded || !isCollapsible
    ? `${formatInteger(sortedRows.length)} filtered rows`
    : `Showing first ${formatInteger(collapseThreshold)} of ${formatInteger(sortedRows.length)} filtered rows`;
  const toggleButtonHtml = isCollapsible && !config.hideToggleButton
    ? `<button type="button" class="table-toggle-button" data-table-toggle="${name}">${expanded ? "Show first 10" : "Expand all"}</button>`
    : "";
  const tableShellClass = expanded || !isCollapsible ? "table-shell is-expanded" : "table-shell is-collapsed";
  const visibleRowsStyle = `--visible-rows:${collapseThreshold};`;
  const topMetaHtml = config.showTopMeta === false ? "" : `<div class="table-meta">${metaLabel}</div>`;
  const hasTopbarContent = Boolean(topMetaHtml || topbarFilterHtml || toggleButtonHtml);
  const footerHtml = config.showFooterCount
    ? `<div class="table-footer-meta">${formatInteger(sortedRows.length)} filtered rows</div>`
    : "";
  const summaryRowHtml = config.showSummaryRow === false ? "" : buildSummaryRow(name, filteredRows, config);
  const heatmapScale = buildHeatmapScale(config, sortedRows);

  container.innerHTML = `
    ${hasTopbarContent ? `
    <div class="table-topbar">
      ${topMetaHtml}
      <div class="table-actions">
        ${topbarFilterHtml}
        ${toggleButtonHtml}
      </div>
    </div>` : ""}
    <div class="${tableShellClass}" data-table-shell="${name}" style="${visibleRowsStyle}" tabindex="0" aria-label="Scrollable table">
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
          ${summaryRowHtml}
          ${sortedRows.map((row) => `
            <tr>
              ${config.columns.map((column) => renderTableCell(column, row, heatmapScale)).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    ${footerHtml}
  `;

  state.tables.set(name, { ...tableState, expanded });
  bindTableInteractions(name);
}

function renderTableCell(column, row, heatmapScale) {
  const value = row[column.key];
  const content = formatCell(value, column.format);
  if (!column.heatmap) {
    return `<td>${content}</td>`;
  }
  const style = buildHeatmapCellStyle(value, heatmapScale);
  const className = style ? "heatmap-cell" : "heatmap-cell is-empty";
  return `<td class="${className}"${style ? ` style="${style}"` : ""}>${content}</td>`;
}

function buildHeatmapScale(config, rows) {
  if (!config.columns.some((column) => column.heatmap)) {
    return null;
  }
  const values = rows.flatMap((row) => config.columns
    .filter((column) => column.heatmap)
    .map((column) => Number(row[column.key]))
    .filter((value) => Number.isFinite(value) && value > 0));
  if (!values.length) {
    return null;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { min, max };
}

function buildHeatmapCellStyle(value, scale) {
  const numericValue = Number(value);
  if (!scale || !Number.isFinite(numericValue) || numericValue <= 0) {
    return "";
  }
  const span = Math.max(scale.max - scale.min, 1);
  const ratio = Math.max(0, Math.min(1, (numericValue - scale.min) / span));
  const hue = 132;
  const saturation = 44 + ratio * 24;
  const lightness = 96 - ratio * 34;
  const borderAlpha = 0.08 + ratio * 0.18;
  return `background-color: hsl(${hue}deg ${saturation}% ${lightness}%); border-color: rgba(34, 84, 52, ${borderAlpha.toFixed(2)});`;
}

function resetTableStates(names) {
  (names || []).forEach((name) => state.tables.delete(name));
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

  document.querySelectorAll(`select[data-table-filter="${name}"]`).forEach((select) => {
    if (select.dataset.bound === "true") {
      return;
    }
    select.addEventListener("change", () => renderTable(name, state.tableData.get(name) || []));
    select.dataset.bound = "true";
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
  const excludeSearch = config.searchExcludeInputId ? Boolean(document.getElementById(config.searchExcludeInputId)?.checked) : false;

  if (query) {
    if (config.searchMode === "regex") {
      const pattern = compileRegex(query, config.searchInputId);
      if (!pattern) {
        return { filteredRows: [], filterError: "The filter is not a valid regular expression." };
      }
      filteredRows = filteredRows.filter((row) => {
        const matched = pattern.test(getRowSearchText(row, config));
        return excludeSearch ? !matched : matched;
      });
    } else {
      clearInputError(config.searchInputId);
      const normalizedQuery = query.toLowerCase();
      filteredRows = filteredRows.filter((row) => {
        const matched = getRowSearchText(row, config).toLowerCase().includes(normalizedQuery);
        return excludeSearch ? !matched : matched;
      });
    }
  } else {
    clearInputError(config.searchInputId);
  }

  const topbarFilters = config.topbarFilters || (config.topbarFilter ? [config.topbarFilter] : []);
  topbarFilters.forEach((filter) => {
    const selectedValue = document.getElementById(filter.inputId)?.value || "";
    if (selectedValue) {
      filteredRows = filteredRows.filter((row) => String(row[filter.key] ?? "").toLowerCase() === selectedValue.toLowerCase());
    }
  });

  if (name === "daypartGroups") {
    const selectedCampaigns = getSelectedTimingCampaigns();
    if (selectedCampaigns.length) {
      const selectedSet = new Set(selectedCampaigns);
      filteredRows = filteredRows.filter((row) => selectedSet.has(row.campaign_name));
    }
    const selectedAdGroups = getSelectedTimingAdGroups();
    if (selectedAdGroups.length) {
      const selectedSet = new Set(selectedAdGroups);
      filteredRows = filteredRows.filter((row) => selectedSet.has(row.ad_group_name));
    }
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

function renderCompetitionNote(text, rows) {
  renderNote("competition-note", text);
  const input = document.getElementById("competition-search");
  if (!input) {
    return;
  }
  const hasRows = Array.isArray(rows) && rows.length > 0;
  input.disabled = !hasRows;
  input.placeholder = hasRows ? "Search competitors" : "No auction insights data available";
}

function buildGridLines(width, height, padding) {
  const lines = [];
  for (let step = 0; step < 4; step += 1) {
    const y = padding.top + ((height - padding.top - padding.bottom) / 3) * step;
    lines.push(`<line x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}" stroke="rgba(216,206,183,0.85)" stroke-width="1"></line>`);
  }
  return lines.join("");
}

function buildTrendDomain(primaryValues, secondaryValues = []) {
  const values = [...primaryValues, ...secondaryValues]
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (!values.length) {
    return { min: 0, max: 1 };
  }

  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    if (max === 0) {
      return { min: 0, max: 1 };
    }
    const pad = Math.abs(max) * 0.12 || 1;
    const lowerBound = min >= 0 ? Math.max(0, min - pad) : min - pad;
    return { min: lowerBound, max: max + pad };
  }

  const span = max - min;
  const pad = span * 0.12;
  min = min >= 0 ? Math.max(0, min - pad) : min - pad;
  max += pad;
  return { min, max };
}

function buildBarDomain(values) {
  const finiteValues = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (!finiteValues.length) {
    return { min: 0, max: 1 };
  }
  const max = Math.max(...finiteValues);
  if (max <= 0) {
    return { min: 0, max: 1 };
  }
  const pad = max * 0.08 || 1;
  return { min: 0, max: max + pad };
}

function buildTrendLinePoints(values, width, height, padding, domain) {
  return values
    .map((value, index) => `${pointX(index, values.length, width, padding)},${pointYForDomain(value, height, padding, domain)}`)
    .join(" ");
}

function buildTrendHoverTargets({ rows, previousRows, primaryMetric, secondaryMetric, compareMetric, compareSeriesLabel, width, height, padding }) {
  if (!rows.length) {
    return "";
  }
  const plotHeight = height - padding.top - padding.bottom;
  return rows.map((row, index) => {
    const currentX = pointX(index, rows.length, width, padding);
    const leftX = index === 0
      ? padding.left
      : (pointX(index - 1, rows.length, width, padding) + currentX) / 2;
    const rightX = index === rows.length - 1
      ? width - padding.right
      : (currentX + pointX(index + 1, rows.length, width, padding)) / 2;
    const tooltipLines = [
      `__TITLE__${row.hover_label || formatDate(row.report_date)}`,
      `${primaryMetric.label}: ${formatTrendMetric(primaryMetric, row[primaryMetric.key])}`,
    ];
    if (secondaryMetric) {
      tooltipLines.push(`${secondaryMetric.label}: ${formatTrendMetric(secondaryMetric, row[secondaryMetric.key])}`);
    }
    if (compareMetric && previousRows[index]) {
      tooltipLines.push(
        `${compareSeriesLabel || compareMetric.label}: ${formatTrendMetric(compareMetric, previousRows[index][compareMetric.key])} (${previousRows[index].hover_label || formatDate(previousRows[index].report_date)})`,
      );
    }
    return `
      <rect
        class="trend-hover-target"
        x="${leftX}"
        y="${padding.top}"
        width="${Math.max(rightX - leftX, 6)}"
        height="${plotHeight}"
        fill="rgba(255,255,255,0.001)"
        pointer-events="all"
        data-tooltip="${encodeTooltipLines(tooltipLines)}"
      >
      </rect>
    `;
  }).join("");
}

function buildTrendXAxisLabels(rows, width, height, padding) {
  if (!rows.length) {
    return "";
  }
  const indexes = buildAxisLabelIndexes(rows.length);
  return indexes.map((index) => {
    const row = rows[index];
    const x = pointX(index, rows.length, width, padding);
    const anchor = index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle";
    return `
      <text x="${x}" y="${height - 10}" fill="#66766a" font-size="11" text-anchor="${anchor}">
        ${escapeHtml(row.x_axis_label || formatShortDate(row.report_date))}
      </text>
    `;
  }).join("");
}

function buildAxisLabelIndexes(length) {
  if (length <= 1) {
    return [0];
  }
  const maxLabels = length <= 6 ? length : 5;
  if (length <= maxLabels) {
    return Array.from({ length }, (_, index) => index);
  }
  const lastIndex = length - 1;
  const indexes = new Set([0, lastIndex]);
  for (let step = 1; step < maxLabels - 1; step += 1) {
    indexes.add(Math.round((lastIndex * step) / (maxLabels - 1)));
  }
  return [...indexes].sort((left, right) => left - right);
}

function aggregateTrendRows(rows, grain) {
  if (!Array.isArray(rows) || !rows.length) {
    return [];
  }
  if (grain === "day") {
    return rows.map((row) => ({
      ...row,
      report_date_start: row.report_date,
      report_date_end: row.report_date,
      x_axis_label: formatShortDate(row.report_date),
      hover_label: formatDate(row.report_date),
    }));
  }

  const buckets = new Map();
  rows.forEach((row) => {
    const bucketKey = trendBucketKey(row.report_date, grain);
    const current = buckets.get(bucketKey) || {
      report_date: bucketKey,
      report_date_start: row.report_date,
      report_date_end: row.report_date,
      cost_eur: 0,
      clicks: 0,
      impressions: 0,
      conversions: 0,
      conversion_value_eur: 0,
    };
    current.report_date_start = current.report_date_start < row.report_date ? current.report_date_start : row.report_date;
    current.report_date_end = current.report_date_end > row.report_date ? current.report_date_end : row.report_date;
    current.cost_eur += Number(row.cost_eur || 0);
    current.clicks += Number(row.clicks || 0);
    current.impressions += Number(row.impressions || 0);
    current.conversions += Number(row.conversions || 0);
    current.conversion_value_eur += Number(row.conversion_value_eur || 0);
    buckets.set(bucketKey, current);
  });

  return [...buckets.values()]
    .sort((left, right) => String(left.report_date).localeCompare(String(right.report_date)))
    .map((bucket) => {
      const isoWeekParts = grain === "week" ? getIsoWeekParts(bucket.report_date_start) : null;
      const enrichedBucket = {
        ...bucket,
        iso_week: isoWeekParts?.isoWeek,
        iso_week_year: isoWeekParts?.isoYear,
        cpc_eur: bucket.clicks ? bucket.cost_eur / bucket.clicks : 0,
        roas: bucket.cost_eur ? bucket.conversion_value_eur / bucket.cost_eur : 0,
        conversion_rate: bucket.clicks ? bucket.conversions / bucket.clicks : 0,
      };
      return {
        ...enrichedBucket,
        x_axis_label: formatTrendBucketAxisLabel(enrichedBucket, grain),
        hover_label: formatTrendBucketHoverLabel(enrichedBucket, grain),
      };
    });
}

function trendBucketKey(dateValue, grain) {
  if (grain === "month") {
    return dateValue.slice(0, 7);
  }
  return getWeekStartIso(dateValue);
}

function getWeekStartIso(dateValue) {
  const date = parseIsoDate(dateValue);
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday);
  return toIsoDate(date);
}

function getIsoWeekParts(dateValue) {
  const date = parseIsoDate(dateValue);
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday + 3);
  const isoYear = date.getUTCFullYear();
  const firstThursday = new Date(Date.UTC(isoYear, 0, 4));
  const firstWeekday = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstWeekday + 3);
  const isoWeek = 1 + Math.round((date - firstThursday) / 604800000);
  return { isoYear, isoWeek };
}

function parseIsoDate(dateValue) {
  const [year, month, day] = String(dateValue).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function toIsoDate(dateValue) {
  return dateValue.toISOString().slice(0, 10);
}

function isIsoDateString(value) {
  if (!value || !ISO_DATE_RE.test(String(value))) {
    return false;
  }
  return toIsoDate(parseIsoDate(value)) === String(value);
}

function validateIsoDateInput(inputId, label) {
  const input = document.getElementById(inputId);
  if (!input) {
    return true;
  }
  const value = input.value.trim();
  if (!value) {
    clearValidatedInputError(inputId);
    return true;
  }
  if (!isIsoDateString(value)) {
    input.classList.add("is-invalid");
    input.setCustomValidity(`${label} must use YYYY-MM-DD.`);
    input.reportValidity();
    return false;
  }
  clearValidatedInputError(inputId);
  return true;
}

function clearValidatedInputError(inputId) {
  const input = document.getElementById(inputId);
  if (!input) {
    return;
  }
  input.setCustomValidity("");
  clearInputError(inputId);
}

function formatShortDate(value) {
  return formatDate(value);
}

function formatTrendBucketAxisLabel(bucket, grain) {
  if (grain === "month") {
    return formatMonth(bucket.report_date_start);
  }
  return `W${String(bucket.iso_week || 0).padStart(2, "0")}`;
}

function formatTrendBucketHoverLabel(bucket, grain) {
  if (grain === "month") {
    return formatMonth(bucket.report_date_start);
  }
  return `${bucket.iso_week_year || ""} W${String(bucket.iso_week || 0).padStart(2, "0")} (${formatDateSpan(bucket.report_date_start, bucket.report_date_end, { includeYear: true })})`;
}

function formatDateSpan(startValue, endValue, options = {}) {
  if (startValue === endValue) {
    return formatDate(startValue);
  }
  return `${formatDate(startValue)} to ${formatDate(endValue)}`;
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

function pointYForDomain(value, height, padding, domain) {
  const drawableHeight = height - padding.top - padding.bottom;
  const span = domain.max - domain.min;
  if (!span) {
    return padding.top + drawableHeight / 2;
  }
  return padding.top + drawableHeight - (drawableHeight * (value - domain.min)) / span;
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
    revenue: "Revenue",
    orders: "Orders",
    aov: "AOV",
    items_purchased: "Items purchased",
    items_added_to_cart: "Added to cart",
    items_viewed: "Items viewed",
    revenue_share: "Revenue share",
    order_share: "Order share",
    view_to_atc_rate: "View to ATC",
    view_to_order_rate: "View to order",
    atc_to_order_rate: "ATC to order",
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

function formatMoneyPrecise(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const number = Number(value);
  const sign = number < 0 ? "-" : "";
  return `${sign}€${moneyPreciseFormat.format(Math.abs(number))}`;
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

function formatPercentPoint(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${formatFixedTwo(roundHalfUp(Number(value), 2))}%`;
}

function formatDate(value) {
  if (!value || !isIsoDateString(value)) {
    return "—";
  }
  return String(value);
}

function formatTimingMatrixDateLabel(value) {
  if (!value) {
    return "—";
  }
  const text = String(value);
  const match = text.match(/^(\d{4}-\d{2}-\d{2})\s+([A-Za-z]{3})$/);
  if (!match) {
    return escapeHtml(text);
  }
  return `<span class="matrix-date-label"><span>${escapeHtml(match[1])}</span><small>${escapeHtml(match[2])}</small></span>`;
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

function formatTrendMetric(metric, value) {
  return stripHtml((metric?.formatter || formatDecimal)(value));
}

function encodeTooltipLines(lines) {
  return encodeURIComponent(lines.join("\n"));
}

function decodeTooltipLines(value) {
  return decodeURIComponent(String(value || ""))
    .split("\n")
    .filter(Boolean);
}

function bindTrendTooltip(host) {
  const tooltip = host.querySelector("[data-trend-tooltip]");
  if (!tooltip) {
    return;
  }

  const hideTooltip = () => {
    tooltip.classList.remove("is-visible");
    tooltip.innerHTML = "";
  };

  const positionTooltip = (event) => {
    const hostRect = host.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const offset = 14;
    let left = event.clientX - hostRect.left + offset;
    const top = 12;

    if (left + tooltipRect.width > hostRect.width - 8) {
      left = Math.max(8, hostRect.width - tooltipRect.width - 8);
    }
    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${top}px`;
  };

  host.querySelectorAll(".trend-hover-target").forEach((target) => {
    const renderTooltip = (event) => {
      const lines = decodeTooltipLines(target.dataset.tooltip);
      if (!lines.length) {
        hideTooltip();
        return;
      }
      tooltip.innerHTML = lines.map((line, index) => {
        const safeLine = escapeHtml(line.replace(/^__TITLE__/, ""));
        return index === 0 && line.startsWith("__TITLE__") ? `<strong>${safeLine}</strong>` : `<div>${safeLine}</div>`;
      }).join("");
      tooltip.classList.add("is-visible");
      positionTooltip(event);
    };

    target.addEventListener("mouseenter", renderTooltip);
    target.addEventListener("mousemove", renderTooltip);
    target.addEventListener("mouseleave", hideTooltip);
  });

  host.onmouseleave = hideTooltip;
}

function formatAlertMessage(value) {
  const raw = String(value ?? "—");
  const rounded = raw.replace(/-?\d+\.\d+/g, (match) => formatFixedTwo(roundHalfUp(Number(match), 2)));
  return escapeHtml(rounded);
}

function roundHalfUp(value, digits = 2) {
  const factor = 10 ** digits;
  const absolute = Math.abs(Number(value));
  const rounded = Math.round((absolute + Number.EPSILON) * factor) / factor;
  return Math.sign(Number(value)) * rounded;
}

function formatFixedTwo(value) {
  return decimalFixedFormat.format(Number(value));
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
