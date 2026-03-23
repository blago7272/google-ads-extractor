const state = {
  options: null,
  tables: new Map(),
  tableData: new Map(),
};

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

const TABLE_CONFIG = {
  campaigns: {
    searchInputId: "campaigns-search",
    containerId: "campaigns-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "campaign_name", label: "Campaign" },
      { key: "campaign_channel_type", label: "Channel" },
      { key: "bidding_strategy_type", label: "Bid strategy" },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "conversion_value_eur", label: "Conv. value", format: formatMoney },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "roas", label: "ROAS", format: formatRatio },
    ],
  },
  keywords: {
    searchInputId: "keywords-search",
    containerId: "keywords-table",
    defaultSort: { key: "cost_eur", direction: "desc" },
    columns: [
      { key: "audit_reason", label: "Issue", format: formatPill },
      { key: "keyword_text", label: "Keyword" },
      { key: "campaign_name", label: "Campaign" },
      { key: "quality_score", label: "QS", format: formatNullableInteger },
      { key: "cost_eur", label: "Spend", format: formatMoney },
      { key: "conversions", label: "Conv.", format: formatDecimal },
      { key: "cpa_eur", label: "CPA", format: formatMoney },
      { key: "report_date_end", label: "Coverage end", format: formatDate },
    ],
  },
  alerts: {
    searchInputId: "alerts-search",
    containerId: "alerts-table",
    defaultSort: { key: "report_date", direction: "desc" },
    columns: [
      { key: "report_date", label: "Date", format: formatDate },
      { key: "severity", label: "Severity", format: formatPill },
      { key: "alert_type", label: "Type" },
      { key: "alert_message", label: "Message" },
    ],
  },
  searchTerms: {
    searchInputId: "search-terms-search",
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
};

document.addEventListener("DOMContentLoaded", async () => {
  bindFilterEvents();
  showLoadingState();
  try {
    const options = await fetchJson("/api/options");
    state.options = options;
    populateFilters(options);
    await refreshDashboard();
  } catch (error) {
    renderGlobalError(error);
  }
});

function bindFilterEvents() {
  document.getElementById("filters-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDashboard();
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
    await refreshDashboard();
  });

  document.getElementById("client-select").addEventListener("change", () => {
    syncAccountOptions();
  });
}

function showLoadingState() {
  document.getElementById("kpi-grid").innerHTML = '<div class="loading-state">Loading metrics</div>';
  ["campaigns-table", "keywords-table", "alerts-table", "search-terms-table", "trend-chart"].forEach((id) => {
    document.getElementById(id).innerHTML = '<div class="loading-state">Loading data</div>';
  });
}

function populateFilters(options) {
  const clientSelect = document.getElementById("client-select");
  const accountSelect = document.getElementById("account-select");
  const clientIds = options.clients.map((item) => item.client_id);

  clientSelect.innerHTML = [
    '<option value="">All clients</option>',
    ...clientIds.map((clientId) => `<option value="${escapeHtml(clientId)}">${escapeHtml(clientId)}</option>`),
  ].join("");

  applyFilterDefaults(options.defaults);
  syncAccountOptions();

  if (options.defaults.account_id) {
    accountSelect.value = options.defaults.account_id;
  }
}

function applyFilterDefaults(defaults) {
  document.getElementById("client-select").value = defaults.client_id || "";
  document.getElementById("date-from-input").value = defaults.date_from;
  document.getElementById("date-to-input").value = defaults.date_to;
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

async function refreshDashboard() {
  const params = new URLSearchParams();
  const clientId = document.getElementById("client-select").value;
  const accountId = document.getElementById("account-select").value;
  const dateFrom = document.getElementById("date-from-input").value;
  const dateTo = document.getElementById("date-to-input").value;

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

  showLoadingState();
  const data = await fetchJson(`/api/dashboard?${params.toString()}`);
  renderDashboard(data);
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

function renderDashboard(payload) {
  renderScope(payload.scope, payload.summary);
  renderKpis(payload.summary, payload.previous_summary);
  renderTrendChart(payload.trend);
  renderTable("campaigns", payload.campaigns);
  renderTable("keywords", payload.keywords);
  renderTable("alerts", payload.alerts);
  renderTable("searchTerms", payload.search_terms);
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
  const html = KPI_DEFS.map((definition) => {
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
  document.getElementById("kpi-grid").innerHTML = html;
}

function renderTrendChart(rows) {
  const host = document.getElementById("trend-chart");
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
      <defs>
        <linearGradient id="fill-a" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(191, 90, 54, 0.28)"></stop>
          <stop offset="100%" stop-color="rgba(191, 90, 54, 0)"></stop>
        </linearGradient>
      </defs>
      ${buildGridLines(width, height, padding)}
      <polyline fill="none" stroke="#285e54" stroke-width="4" points="${pointsB}"></polyline>
      <polyline fill="none" stroke="#bf5a36" stroke-width="4" points="${pointsA}"></polyline>
      <text x="${padding.left}" y="${padding.top - 4}" fill="#66766a" font-size="12">Spend vs conversion value (EUR)</text>
      <circle cx="${pointX(valuesA.length - 1, valuesA.length, width, padding)}" cy="${pointY(Number(lastRow.cost_eur || 0), height, padding, maxValue)}" r="5" fill="#bf5a36"></circle>
      <circle cx="${pointX(valuesB.length - 1, valuesB.length, width, padding)}" cy="${pointY(Number(lastRow.conversion_value_eur || 0), height, padding, maxValue)}" r="5" fill="#285e54"></circle>
    </svg>
  `;
}

function renderTable(name, rows) {
  const config = TABLE_CONFIG[name];
  const container = document.getElementById(config.containerId);
  state.tableData.set(name, rows);
  const query = document.getElementById(config.searchInputId).value.toLowerCase();

  const tableState = state.tables.get(name) || { sortKey: config.defaultSort.key, direction: config.defaultSort.direction };
  const filteredRows = rows.filter((row) => {
    if (!query) {
      return true;
    }
    return JSON.stringify(row).toLowerCase().includes(query);
  });
  const sortedRows = [...filteredRows].sort((left, right) => compareRows(left, right, tableState.sortKey, tableState.direction));

  if (!sortedRows.length) {
    container.innerHTML = '<div class="empty-state">No rows for the selected range.</div>';
    return;
  }

  container.innerHTML = `
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
        ${sortedRows.map((row) => `
          <tr>
            ${config.columns.map((column) => `<td>${formatCell(row[column.key], column.format)}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  state.tables.set(name, tableState);
  bindTableInteractions(name, rows);
}

function bindTableInteractions(name, sourceRows) {
  const config = TABLE_CONFIG[name];
  document.querySelectorAll(`button[data-table="${name}"]`).forEach((button) => {
    button.addEventListener("click", () => {
      const tableState = state.tables.get(name) || { sortKey: config.defaultSort.key, direction: config.defaultSort.direction };
      const key = button.dataset.key;
      const direction = tableState.sortKey === key && tableState.direction === "desc" ? "asc" : "desc";
      state.tables.set(name, { sortKey: key, direction });
      renderTable(name, state.tableData.get(name) || sourceRows);
    });
  });

  const searchInput = document.getElementById(config.searchInputId);
  if (searchInput.dataset.bound !== "true") {
    searchInput.addEventListener("input", () => renderTable(name, state.tableData.get(name) || []));
    searchInput.dataset.bound = "true";
  }
}

function compareRows(left, right, key, direction) {
  const a = left?.[key];
  const b = right?.[key];
  let comparison = 0;
  if (typeof a === "number" || typeof b === "number") {
    comparison = Number(a || 0) - Number(b || 0);
  } else {
    comparison = String(a || "").localeCompare(String(b || ""), undefined, { numeric: true, sensitivity: "base" });
  }
  return direction === "asc" ? comparison : -comparison;
}

function renderSortMarker(tableState, key) {
  if (tableState.sortKey !== key) {
    return "";
  }
  return tableState.direction === "desc" ? " ↓" : " ↑";
}

function formatCell(value, formatter) {
  if (formatter) {
    return formatter(value);
  }
  return escapeHtml(value ?? "—");
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

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `€${moneyFormat.format(Number(value))}`;
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

function formatPill(value) {
  const safe = escapeHtml(String(value ?? "—"));
  const className = String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return `<span class="pill ${className}">${safe}</span>`;
}

function renderGlobalError(error) {
  document.getElementById("kpi-grid").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
