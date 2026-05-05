"""Dashboard — multi-panel trading-terminal-style view."""

from __future__ import annotations


def render_dashboard_page() -> str:
    return """
        <html>
            <head>
                <title>MarketAgent – Dashboard</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" />
                <style>
                    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap");
                    * { box-sizing: border-box; margin: 0; padding: 0; }
                    body {
                        font-family: "Space Grotesk", "Noto Sans SC", system-ui, sans-serif;
                        background: #0f1117;
                        color: #e4e4e7;
                        height: 100vh;
                        overflow: hidden;
                        display: flex;
                        flex-direction: column;
                    }
                    .dash-header {
                        display: flex;
                        align-items: center;
                        gap: 16px;
                        padding: 10px 20px;
                        background: #1a1d27;
                        border-bottom: 1px solid #2a2d37;
                        flex-shrink: 0;
                    }
                    .dash-header .back-btn {
                        color: #71717a;
                        text-decoration: none;
                        font-size: 13px;
                        padding: 4px 10px;
                        border: 1px solid #3f3f46;
                        border-radius: 6px;
                    }
                    .dash-header .back-btn:hover { color: #e4e4e7; border-color: #71717a; }
                    .dash-header h1 { font-size: 16px; font-weight: 600; color: #fafafa; }
                    .dash-header .controls { margin-left: auto; display: flex; gap: 10px; align-items: center; }
                    .dash-header select, .dash-header input {
                        padding: 5px 10px; border: 1px solid #3f3f46; border-radius: 6px;
                        background: #27272a; color: #e4e4e7; font-size: 13px;
                    }
                    .dash-grid {
                        display: grid;
                        grid-template-columns: 1fr 1fr;
                        grid-template-rows: 1fr 1fr 1fr;
                        gap: 1px;
                        flex: 1;
                        overflow: hidden;
                        background: #2a2d37;
                    }
                    .panel {
                        background: #1a1d27;
                        display: flex;
                        flex-direction: column;
                        overflow: hidden;
                    }
                    .panel-header {
                        padding: 8px 14px;
                        font-size: 12px;
                        font-weight: 600;
                        color: #a1a1aa;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        border-bottom: 1px solid #2a2d37;
                        flex-shrink: 0;
                        background: #16181f;
                    }
                    .panel-body {
                        flex: 1;
                        overflow-y: auto;
                        padding: 12px 14px;
                        font-size: 13px;
                        line-height: 1.6;
                    }
                    .panel-body::-webkit-scrollbar { width: 6px; }
                    .panel-body::-webkit-scrollbar-track { background: transparent; }
                    .panel-body::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
                    .panel-body h3 { font-size: 14px; color: #fafafa; margin: 12px 0 6px; }
                    .panel-body h3:first-child { margin-top: 0; }
                    .panel-body p { margin: 6px 0; color: #d4d4d8; }
                    .panel-body ul { padding-left: 16px; margin: 4px 0; }
                    .panel-body li { margin-bottom: 3px; color: #d4d4d8; }
                    .panel-body strong { color: #fafafa; }
                    .panel-body a { color: #60a5fa; }
                    .placeholder { color: #71717a; font-style: italic; }
                    .metric-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #27272a; }
                    .metric-label { color: #a1a1aa; }
                    .metric-value { color: #fafafa; font-weight: 500; }
                    .beat { color: #4ade80; }
                    .miss { color: #f87171; }
                    .macro-row { display: flex; gap: 8px; padding: 5px 0; border-bottom: 1px solid #27272a; font-size: 12px; }
                    .macro-date { color: #71717a; white-space: nowrap; min-width: 90px; }
                    .macro-name { color: #d4d4d8; flex: 1; }
                    .macro-importance { color: #fbbf24; font-size: 11px; }
                    .cluster { margin-bottom: 10px; }
                    .cluster-title { font-weight: 600; color: #fafafa; font-size: 13px; }
                    .cluster-summary { color: #a1a1aa; font-size: 12px; margin-top: 2px; }
                    .news-item { padding: 5px 0; border-bottom: 1px solid #27272a; }
                    .news-item a { color: #60a5fa; font-size: 12px; text-decoration: none; }
                    .news-item a:hover { text-decoration: underline; }
                    .news-meta { font-size: 11px; color: #71717a; }
                </style>
            </head>
            <body>
                <div class="dash-header">
                    <a href="/market" class="back-btn">← Back</a>
                    <h1>Dashboard</h1>
                    <div class="controls">
                        <select id="company-select"></select>
                        <input type="text" id="date-picker" style="width:110px;" />
                    </div>
                </div>
                <div class="dash-grid">
                    <div class="panel" id="panel-market">
                        <div class="panel-header">Market Overview</div>
                        <div class="panel-body" id="market-body"><span class="placeholder">Loading...</span></div>
                    </div>
                    <div class="panel" id="panel-macro">
                        <div class="panel-header">Macro Calendar</div>
                        <div class="panel-body" id="macro-body"><span class="placeholder">Loading...</span></div>
                    </div>
                    <div class="panel" id="panel-daily">
                        <div class="panel-header">Company Daily News</div>
                        <div class="panel-body" id="daily-body"><span class="placeholder">Select a company</span></div>
                    </div>
                    <div class="panel" id="panel-earnings">
                        <div class="panel-header">Earnings Summary</div>
                        <div class="panel-body" id="earnings-body"><span class="placeholder">Select a company</span></div>
                    </div>
                    <div class="panel" id="panel-weekly">
                        <div class="panel-header">Weekly Report</div>
                        <div class="panel-body" id="weekly-body"><span class="placeholder">Select a company</span></div>
                    </div>
                    <div class="panel" id="panel-monthly">
                        <div class="panel-header">Monthly Report</div>
                        <div class="panel-body" id="monthly-body"><span class="placeholder">Select a company</span></div>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    let activeCompany = null;
                    let selectedDate = null;

                    function localDateText(d) {
                        if (!d) d = new Date();
                        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
                    }
                    function currentMonth() {
                        const d = new Date();
                        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0");
                    }
                    function renderMd(text) {
                        if (!text) return "";
                        try { return marked.parse(text); } catch { return text; }
                    }

                    const WEEK_START_DAY = 6;
                    function weekBoundaries(d) {
                        const offset = (d.getDay() - WEEK_START_DAY + 7) % 7;
                        const start = new Date(d); start.setDate(d.getDate() - offset);
                        const end = new Date(start); end.setDate(start.getDate() + 6);
                        return [localDateText(start), localDateText(end)];
                    }

                    // --- Load companies ---
                    async function initCompanies() {
                        const resp = await fetch("/api/companies");
                        const data = await resp.json();
                        const names = data.company_names || [];
                        const sel = document.getElementById("company-select");
                        sel.innerHTML = names.map((n) => `<option value="${n}">${n}</option>`).join("");
                        if (names.length) {
                            activeCompany = names[0];
                            sel.value = activeCompany;
                        }
                        sel.addEventListener("change", () => { activeCompany = sel.value; loadCompanyPanels(); });
                    }

                    // --- Panel 1: Market Overview ---
                    async function loadMarketPanel() {
                        const body = document.getElementById("market-body");
                        try {
                            const resp = await fetch(`/api/market/daily-news?date=${selectedDate || localDateText()}`);
                            const data = await resp.json();
                            const summaries = data.summaries || [];
                            const latest = summaries.length ? summaries[summaries.length - 1] : null;
                            if (latest && latest.output_text) {
                                body.innerHTML = renderMd(latest.output_text);
                            } else {
                                body.innerHTML = '<span class="placeholder">No market summary for this date.</span>';
                            }
                        } catch { body.innerHTML = '<span class="placeholder">Failed to load.</span>'; }
                    }

                    // --- Panel 2: Macro Calendar ---
                    async function loadMacroPanel() {
                        const body = document.getElementById("macro-body");
                        try {
                            const resp = await fetch("/api/market/macro?lookback_days=0&lookahead_days=14");
                            const data = await resp.json();
                            const events = data.events || [];
                            if (!events.length) { body.innerHTML = '<span class="placeholder">No upcoming macro events.</span>'; return; }
                            body.innerHTML = events.map((ev) => {
                                const dt = (ev.event_date_time || "").slice(0, 10);
                                const imp = ev.importance ? `<span class="macro-importance">${ev.importance}</span>` : "";
                                return `<div class="macro-row"><span class="macro-date">${dt}</span><span class="macro-name">${ev.event_name || ""}</span>${imp}</div>`;
                            }).join("");
                        } catch { body.innerHTML = '<span class="placeholder">Failed to load.</span>'; }
                    }

                    // --- Panel 3: Company Daily News ---
                    async function loadDailyPanel(groups) {
                        const body = document.getElementById("daily-body");
                        const target = selectedDate || localDateText();
                        const dailyGroups = groups.filter((g) => g.type === "daily");
                        const group = dailyGroups.find((g) => g.label === target || g.key === `day-${target}`);
                        if (!group) { body.innerHTML = `<span class="placeholder">No daily data for ${target}.</span>`; return; }
                        let html = "";
                        if (group.daily_report && group.daily_report.output_text) {
                            html += `<h3>Daily Report</h3>${renderMd(group.daily_report.output_text)}`;
                        }
                        const clusters = group.daily_clusters || [];
                        if (clusters.length) {
                            html += "<h3>Clusters</h3>";
                            html += clusters.map((c) => `<div class="cluster"><div class="cluster-title">${c.cluster_title || ""}</div><div class="cluster-summary">${c.cluster_summary || ""}</div></div>`).join("");
                        }
                        const items = group.items || [];
                        if (items.length) {
                            html += `<h3>News (${items.length})</h3>`;
                            html += items.slice(0, 20).map((item) => {
                                const link = item.news_source_link ? `<a href="${item.news_source_link}" target="_blank">${item.news_title}</a>` : item.news_title;
                                return `<div class="news-item">${link}<div class="news-meta">${item.news_source || ""} · ${(item.news_date_time || "").slice(11, 16)}</div></div>`;
                            }).join("");
                        }
                        body.innerHTML = html || '<span class="placeholder">No data.</span>';
                    }

                    // --- Panel 4: Earnings ---
                    async function loadEarningsPanel() {
                        const body = document.getElementById("earnings-body");
                        if (!activeCompany) { body.innerHTML = '<span class="placeholder">Select a company.</span>'; return; }
                        try {
                            const resp = await fetch(`/api/company/${encodeURIComponent(activeCompany)}/earnings/reports?limit=1`);
                            const data = await resp.json();
                            const report = (data.reports || [])[0];
                            if (!report) { body.innerHTML = '<span class="placeholder">No earnings data.</span>'; return; }
                            const fin = report.financials || {};
                            const est = report.estimates || {};
                            const a = (report.analysis || {}).analysis || {};
                            function xv(v) { if (v == null) return null; if (typeof v === "object") return v.value ?? v.amount ?? null; return v; }
                            function fmtB(n) { if (n == null) return "—"; const abs = Math.abs(n); return abs >= 1000 ? "$" + (n/1000).toFixed(1) + "B" : "$" + n.toLocaleString() + "M"; }
                            const rows = [
                                ["Revenue", fmtB(xv(fin.revenue))],
                                ["EPS", xv(fin.diluted_eps) != null ? "$" + xv(fin.diluted_eps) : "—"],
                                ["Op. Margin", xv(fin.operating_margin_pct) != null ? xv(fin.operating_margin_pct) + "%" : "—"],
                                ["Net Income", fmtB(xv(fin.net_income))],
                                ["FCF", fmtB(xv(fin.free_cash_flow))],
                            ];
                            let html = `<h3>${report.fiscal_year} ${report.fiscal_quarter}</h3>`;
                            html += rows.map(([l,v]) => `<div class="metric-row"><span class="metric-label">${l}</span><span class="metric-value">${v}</span></div>`).join("");
                            if (est.revenue && est.revenue.beat_miss_pct != null) {
                                const cls = est.revenue.beat_miss_pct > 0 ? "beat" : "miss";
                                html += `<div class="metric-row"><span class="metric-label">Rev vs Est</span><span class="metric-value ${cls}">${est.revenue.beat_miss_pct > 0 ? "+" : ""}${est.revenue.beat_miss_pct}%</span></div>`;
                            }
                            if (a.executive_summary) html += `<p style="margin-top:10px;">${a.executive_summary}</p>`;
                            body.innerHTML = html;
                        } catch { body.innerHTML = '<span class="placeholder">Failed to load.</span>'; }
                    }

                    // --- Panel 5: Weekly Report ---
                    async function loadWeeklyPanel(groups) {
                        const body = document.getElementById("weekly-body");
                        const d = selectedDate ? new Date(selectedDate + "T00:00:00") : new Date();
                        const [weekStart] = weekBoundaries(d);
                        const weeklyGroups = groups.filter((g) => g.type === "weekly");
                        const group = weeklyGroups.find((g) => g.report_start === weekStart);
                        if (!group || !group.report) { body.innerHTML = `<span class="placeholder">No weekly report for week of ${weekStart}.</span>`; return; }
                        const report = group.report;
                        const sections = ["summary", "sentiment", "facts", "viewpoint", "reasoning", "trends"];
                        let html = `<h3>Week of ${group.report_start}</h3>`;
                        for (const key of sections) {
                            const val = report[key];
                            if (!val || (Array.isArray(val) && !val.length)) continue;
                            const items = Array.isArray(val) ? val : [val];
                            html += `<strong>${key}:</strong><ul>${items.map((s) => `<li>${s}</li>`).join("")}</ul>`;
                        }
                        body.innerHTML = html || '<span class="placeholder">Report is empty.</span>';
                    }

                    // --- Panel 6: Monthly Report ---
                    async function loadMonthlyPanel(groups) {
                        const body = document.getElementById("monthly-body");
                        const target = selectedDate ? selectedDate.slice(0, 7) : currentMonth();
                        const monthlyGroups = groups.filter((g) => g.type === "monthly");
                        const group = monthlyGroups.find((g) => g.label === target);
                        if (!group || !group.report) { body.innerHTML = `<span class="placeholder">No monthly report for ${target}.</span>`; return; }
                        const report = group.report;
                        const sections = ["summary", "sentiment", "facts", "viewpoint", "reasoning", "trends"];
                        let html = `<h3>${target}</h3>`;
                        for (const key of sections) {
                            const val = report[key];
                            if (!val || (Array.isArray(val) && !val.length)) continue;
                            const items = Array.isArray(val) ? val : [val];
                            html += `<strong>${key}:</strong><ul>${items.map((s) => `<li>${s}</li>`).join("")}</ul>`;
                        }
                        body.innerHTML = html || '<span class="placeholder">Report is empty.</span>';
                    }

                    // --- Load company-dependent panels ---
                    async function loadCompanyPanels() {
                        if (!activeCompany) return;
                        const [dailyBody, weeklyBody, monthlyBody] = ["daily-body", "weekly-body", "monthly-body"].map((id) => document.getElementById(id));
                        dailyBody.innerHTML = weeklyBody.innerHTML = monthlyBody.innerHTML = '<span class="placeholder">Loading...</span>';
                        try {
                            const resp = await fetch(`/api/company/${encodeURIComponent(activeCompany)}/news?output_language=zh-CN`);
                            const data = await resp.json();
                            const groups = data.groups || [];
                            loadDailyPanel(groups);
                            loadWeeklyPanel(groups);
                            loadMonthlyPanel(groups);
                        } catch {
                            dailyBody.innerHTML = weeklyBody.innerHTML = monthlyBody.innerHTML = '<span class="placeholder">Failed to load.</span>';
                        }
                        loadEarningsPanel();
                    }

                    // --- Init ---
                    selectedDate = localDateText();
                    if (window.flatpickr) {
                        window.flatpickr(document.getElementById("date-picker"), {
                            dateFormat: "Y-m-d",
                            defaultDate: selectedDate,
                            maxDate: localDateText(),
                            onChange: function(dates) {
                                if (!dates.length) return;
                                selectedDate = localDateText(dates[0]);
                                loadMarketPanel();
                                loadCompanyPanels();
                            },
                        });
                    }

                    async function init() {
                        await initCompanies();
                        loadMarketPanel();
                        loadMacroPanel();
                        loadCompanyPanels();
                    }
                    init();
                </script>
            </body>
        </html>
    """
