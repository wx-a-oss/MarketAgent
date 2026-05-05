"""Dashboard v2 — configurable, draggable, resizable panels."""

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
                    body { font-family: "Space Grotesk", "Noto Sans SC", system-ui, sans-serif; background: #0f1117; color: #e4e4e7; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
                    .dash-header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #1a1d27; border-bottom: 1px solid #2a2d37; flex-shrink: 0; }
                    .dash-header .back-btn { color: #71717a; text-decoration: none; font-size: 13px; padding: 4px 10px; border: 1px solid #3f3f46; border-radius: 6px; }
                    .dash-header .back-btn:hover { color: #e4e4e7; border-color: #71717a; }
                    .dash-header h1 { font-size: 15px; font-weight: 600; color: #fafafa; }
                    .dash-header .spacer { flex: 1; }
                    .dash-header .add-btn { padding: 4px 12px; border: 1px solid #3f3f46; border-radius: 6px; background: #27272a; color: #e4e4e7; cursor: pointer; font-size: 12px; }
                    .dash-header .add-btn:hover { border-color: #60a5fa; color: #60a5fa; }
                    .dash-header .reset-btn { padding: 4px 10px; border: 1px solid #3f3f46; border-radius: 6px; background: transparent; color: #71717a; cursor: pointer; font-size: 11px; }
                    .dash-header .reset-btn:hover { color: #f87171; border-color: #f87171; }
                    .dash-grid { display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: minmax(280px, 1fr); gap: 2px; flex: 1; overflow: auto; background: #2a2d37; padding: 2px; }
                    .panel { background: #1a1d27; display: flex; flex-direction: column; overflow: hidden; border-radius: 4px; transition: box-shadow 0.15s; }
                    .panel.drag-over { box-shadow: inset 0 0 0 2px #60a5fa; }
                    .panel-header { display: flex; align-items: center; gap: 4px; padding: 5px 8px; border-bottom: 1px solid #2a2d37; background: #16181f; flex-shrink: 0; flex-wrap: wrap; }
                    .panel-header .drag-handle { cursor: grab; color: #71717a; font-size: 14px; padding: 0 4px; user-select: none; }
                    .panel-header .drag-handle:active { cursor: grabbing; }
                    .panel-header select, .panel-header input { padding: 2px 6px; border: 1px solid #3f3f46; border-radius: 4px; background: #27272a; color: #d4d4d8; font-size: 11px; }
                    .panel-header select { max-width: 120px; }
                    .panel-header input { width: 90px; text-align: center; }
                    .panel-header .size-btn { padding: 1px 6px; border: 1px solid #3f3f46; border-radius: 4px; background: transparent; color: #71717a; cursor: pointer; font-size: 12px; line-height: 1.2; }
                    .panel-header .size-btn:hover { color: #60a5fa; border-color: #60a5fa; }
                    .panel-header .size-btn.active { color: #60a5fa; border-color: #60a5fa; background: #1e3a5f; }
                    .panel-header .close-btn { padding: 1px 6px; border: none; background: transparent; color: #71717a; cursor: pointer; font-size: 14px; margin-left: auto; }
                    .panel-header .close-btn:hover { color: #f87171; }
                    .panel-body { flex: 1; overflow-y: auto; padding: 10px 12px; font-size: 13px; line-height: 1.6; }
                    .panel-body::-webkit-scrollbar { width: 5px; }
                    .panel-body::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
                    .panel-body h3 { font-size: 13px; color: #fafafa; margin: 10px 0 4px; }
                    .panel-body h3:first-child { margin-top: 0; }
                    .panel-body p { margin: 4px 0; color: #d4d4d8; }
                    .panel-body ul { padding-left: 14px; margin: 4px 0; }
                    .panel-body li { margin-bottom: 2px; color: #d4d4d8; font-size: 12px; }
                    .panel-body strong { color: #fafafa; }
                    .panel-body a { color: #60a5fa; text-decoration: none; }
                    .placeholder { color: #71717a; font-style: italic; font-size: 12px; }
                    .metric-row { display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid #27272a; font-size: 12px; }
                    .metric-label { color: #a1a1aa; }
                    .metric-value { color: #fafafa; }
                    .macro-row { display: flex; gap: 6px; padding: 4px 0; border-bottom: 1px solid #27272a; font-size: 11px; }
                    .macro-date { color: #71717a; min-width: 80px; }
                    .macro-name { color: #d4d4d8; flex: 1; }
                    .cluster { margin-bottom: 8px; }
                    .cluster-title { font-weight: 600; color: #fafafa; font-size: 12px; }
                    .cluster-summary { color: #a1a1aa; font-size: 11px; margin-top: 2px; }
                    .news-item { padding: 4px 0; border-bottom: 1px solid #27272a; }
                    .news-item a { font-size: 12px; }
                    .news-meta { font-size: 10px; color: #71717a; }
                    .add-dropdown { position: absolute; top: 40px; right: 80px; background: #27272a; border: 1px solid #3f3f46; border-radius: 8px; padding: 6px 0; z-index: 100; display: none; }
                    .add-dropdown.show { display: block; }
                    .add-dropdown button { display: block; width: 100%; padding: 6px 16px; border: none; background: transparent; color: #d4d4d8; cursor: pointer; font-size: 12px; text-align: left; }
                    .add-dropdown button:hover { background: #3f3f46; }
                </style>
            </head>
            <body>
                <div class="dash-header">
                    <a href="/market" class="back-btn">← Back</a>
                    <h1>Dashboard</h1>
                    <span class="spacer"></span>
                    <button class="add-btn" id="add-btn">+ Add Panel</button>
                    <button class="reset-btn" id="reset-btn">Reset</button>
                </div>
                <div class="add-dropdown" id="add-dropdown">
                    <button data-type="market_overview">Market Overview</button>
                    <button data-type="macro">Macro Calendar</button>
                    <button data-type="daily_news">Daily News</button>
                    <button data-type="weekly_report">Weekly Report</button>
                    <button data-type="monthly_report">Monthly Report</button>
                    <button data-type="earnings">Earnings</button>
                </div>
                <div class="dash-grid" id="dash-grid"></div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    const STORAGE_KEY = "dashboard_v2_layout";
                    const PANEL_TYPES = [
                        { value: "market_overview", label: "Market Overview", needsCompany: false, needsDate: true },
                        { value: "macro", label: "Macro Calendar", needsCompany: false, needsDate: false },
                        { value: "daily_news", label: "Daily News", needsCompany: true, needsDate: true },
                        { value: "weekly_report", label: "Weekly Report", needsCompany: true, needsDate: true },
                        { value: "monthly_report", label: "Monthly Report", needsCompany: true, needsDate: true },
                        { value: "earnings", label: "Earnings", needsCompany: true, needsDate: false },
                    ];
                    let companies = [];
                    let panels = [];
                    let dragId = null;
                    let nextId = 100;

                    function localDateText(d) { if (!d) d = new Date(); return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0"); }
                    function currentMonth() { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0"); }
                    function renderMd(t) { if (!t) return ""; try { return marked.parse(t); } catch { return t; } }
                    const WEEK_START_DAY = 6;
                    function weekBoundaries(d) { const o = (d.getDay() - WEEK_START_DAY + 7) % 7; const s = new Date(d); s.setDate(d.getDate()-o); return [localDateText(s), localDateText(new Date(s.getTime()+6*86400000))]; }

                    function defaultLayout() {
                        const co = companies[0] || null;
                        return [
                            { id: "p1", type: "market_overview", company: null, date: null, colSpan: 1, rowSpan: 1 },
                            { id: "p2", type: "macro", company: null, date: null, colSpan: 1, rowSpan: 1 },
                            { id: "p3", type: "daily_news", company: co, date: null, colSpan: 1, rowSpan: 1 },
                            { id: "p4", type: "earnings", company: co, date: null, colSpan: 1, rowSpan: 1 },
                            { id: "p5", type: "weekly_report", company: co, date: null, colSpan: 1, rowSpan: 1 },
                            { id: "p6", type: "monthly_report", company: co, date: null, colSpan: 1, rowSpan: 1 },
                        ];
                    }
                    function saveLayout() { localStorage.setItem(STORAGE_KEY, JSON.stringify(panels)); }
                    function loadLayout() {
                        try { const s = localStorage.getItem(STORAGE_KEY); if (s) { panels = JSON.parse(s); return; } } catch {}
                        panels = defaultLayout();
                    }

                    async function fetchCompanies() {
                        const r = await fetch("/api/companies"); const d = await r.json();
                        companies = d.company_names || [];
                    }

                    function renderGrid() {
                        const grid = document.getElementById("dash-grid");
                        grid.innerHTML = panels.map((p) => {
                            const typeCfg = PANEL_TYPES.find((t) => t.value === p.type) || PANEL_TYPES[0];
                            const typeOpts = PANEL_TYPES.map((t) => `<option value="${t.value}" ${t.value === p.type ? "selected" : ""}>${t.label}</option>`).join("");
                            const companyOpts = companies.map((c) => `<option value="${c}" ${c === p.company ? "selected" : ""}>${c}</option>`).join("");
                            const companySelect = typeCfg.needsCompany ? `<select class="panel-company" data-id="${p.id}">${companyOpts}</select>` : "";
                            const dateInput = typeCfg.needsDate ? `<input class="panel-date" data-id="${p.id}" type="text" value="${p.date || localDateText()}" />` : "";
                            const wideActive = p.colSpan > 1 ? " active" : "";
                            const tallActive = p.rowSpan > 1 ? " active" : "";
                            return `<div class="panel" draggable="true" data-id="${p.id}" style="grid-column:span ${p.colSpan};grid-row:span ${p.rowSpan};">
                                <div class="panel-header">
                                    <span class="drag-handle">≡</span>
                                    <select class="panel-type" data-id="${p.id}">${typeOpts}</select>
                                    ${companySelect}
                                    ${dateInput}
                                    <button class="size-btn${wideActive}" data-id="${p.id}" data-dir="wide" title="Wide">⇔</button>
                                    <button class="size-btn${tallActive}" data-id="${p.id}" data-dir="tall" title="Tall">⇕</button>
                                    <button class="close-btn" data-id="${p.id}">×</button>
                                </div>
                                <div class="panel-body" id="body-${p.id}"><span class="placeholder">Loading...</span></div>
                            </div>`;
                        }).join("");
                        wireEvents();
                        panels.forEach((p) => loadPanelData(p));
                    }

                    function wireEvents() {
                        document.querySelectorAll(".panel-type").forEach((sel) => { sel.addEventListener("change", (e) => { const p = panels.find((x) => x.id === e.target.dataset.id); if (p) { p.type = e.target.value; saveLayout(); renderGrid(); } }); });
                        document.querySelectorAll(".panel-company").forEach((sel) => { sel.addEventListener("change", (e) => { const p = panels.find((x) => x.id === e.target.dataset.id); if (p) { p.company = e.target.value; saveLayout(); loadPanelData(p); } }); });
                        document.querySelectorAll(".panel-date").forEach((input) => {
                            if (window.flatpickr) { window.flatpickr(input, { dateFormat: "Y-m-d", maxDate: localDateText(), onChange: (dates) => { if (!dates.length) return; const p = panels.find((x) => x.id === input.dataset.id); if (p) { p.date = localDateText(dates[0]); saveLayout(); loadPanelData(p); } } }); }
                        });
                        document.querySelectorAll(".size-btn").forEach((btn) => { btn.addEventListener("click", () => { const p = panels.find((x) => x.id === btn.dataset.id); if (!p) return; if (btn.dataset.dir === "wide") p.colSpan = p.colSpan > 1 ? 1 : 2; else p.rowSpan = p.rowSpan > 1 ? 1 : 2; saveLayout(); renderGrid(); }); });
                        document.querySelectorAll(".close-btn").forEach((btn) => { btn.addEventListener("click", () => { panels = panels.filter((x) => x.id !== btn.dataset.id); saveLayout(); renderGrid(); }); });
                        // Drag and drop
                        document.querySelectorAll(".panel[draggable]").forEach((el) => {
                            el.addEventListener("dragstart", (e) => { dragId = el.dataset.id; e.dataTransfer.effectAllowed = "move"; });
                            el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drag-over"); });
                            el.addEventListener("dragleave", () => { el.classList.remove("drag-over"); });
                            el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("drag-over"); const targetId = el.dataset.id; if (dragId && dragId !== targetId) { const fromIdx = panels.findIndex((p) => p.id === dragId); const toIdx = panels.findIndex((p) => p.id === targetId); if (fromIdx >= 0 && toIdx >= 0) { const [moved] = panels.splice(fromIdx, 1); panels.splice(toIdx, 0, moved); saveLayout(); renderGrid(); } } dragId = null; });
                            el.addEventListener("dragend", () => { dragId = null; document.querySelectorAll(".drag-over").forEach((x) => x.classList.remove("drag-over")); });
                        });
                    }

                    // --- Data loading per panel ---
                    async function loadPanelData(p) {
                        const body = document.getElementById("body-" + p.id);
                        if (!body) return;
                        body.innerHTML = '<span class="placeholder">Loading...</span>';
                        try {
                            if (p.type === "market_overview") await loadMarket(body, p);
                            else if (p.type === "macro") await loadMacro(body);
                            else if (p.type === "daily_news") await loadDaily(body, p);
                            else if (p.type === "weekly_report") await loadWeekly(body, p);
                            else if (p.type === "monthly_report") await loadMonthly(body, p);
                            else if (p.type === "earnings") await loadEarnings(body, p);
                        } catch { body.innerHTML = '<span class="placeholder">Failed to load.</span>'; }
                    }

                    async function loadMarket(body, p) {
                        const date = p.date || localDateText();
                        const r = await fetch(`/api/market/daily-news?date=${date}`); const d = await r.json();
                        const summaries = d.summaries || []; const latest = summaries[summaries.length - 1];
                        body.innerHTML = latest && latest.output_text ? renderMd(latest.output_text) : '<span class="placeholder">No market summary.</span>';
                    }
                    async function loadMacro(body) {
                        const r = await fetch("/api/market/macro?lookback_days=0&lookahead_days=14"); const d = await r.json();
                        const events = d.events || [];
                        if (!events.length) { body.innerHTML = '<span class="placeholder">No macro events.</span>'; return; }
                        body.innerHTML = events.map((e) => `<div class="macro-row"><span class="macro-date">${(e.event_date_time||"").slice(0,10)}</span><span class="macro-name">${e.event_name||""}</span></div>`).join("");
                    }
                    async function loadDaily(body, p) {
                        if (!p.company) { body.innerHTML = '<span class="placeholder">Select a company.</span>'; return; }
                        const r = await fetch(`/api/company/${encodeURIComponent(p.company)}/news?output_language=zh-CN`); const d = await r.json();
                        const date = p.date || localDateText();
                        const group = (d.groups || []).find((g) => g.type === "daily" && (g.label === date || g.key === `day-${date}`));
                        if (!group) { body.innerHTML = `<span class="placeholder">No daily data for ${date}.</span>`; return; }
                        let html = "";
                        if (group.daily_report && group.daily_report.output_text) html += renderMd(group.daily_report.output_text);
                        const clusters = group.daily_clusters || [];
                        if (clusters.length) html += "<h3>Clusters</h3>" + clusters.map((c) => `<div class="cluster"><div class="cluster-title">${c.cluster_title||""}</div><div class="cluster-summary">${c.cluster_summary||""}</div></div>`).join("");
                        const items = group.items || [];
                        if (items.length) html += `<h3>News (${items.length})</h3>` + items.slice(0, 15).map((i) => `<div class="news-item"><a href="${i.news_source_link||"#"}" target="_blank">${i.news_title}</a><div class="news-meta">${i.news_source||""}</div></div>`).join("");
                        body.innerHTML = html || '<span class="placeholder">No data.</span>';
                    }
                    async function loadWeekly(body, p) {
                        if (!p.company) { body.innerHTML = '<span class="placeholder">Select a company.</span>'; return; }
                        const r = await fetch(`/api/company/${encodeURIComponent(p.company)}/news?output_language=zh-CN`); const d = await r.json();
                        const date = p.date ? new Date(p.date + "T00:00:00") : new Date();
                        const [ws] = weekBoundaries(date);
                        const group = (d.groups || []).find((g) => g.type === "weekly" && g.report_start === ws);
                        if (!group || !group.report) { body.innerHTML = `<span class="placeholder">No weekly report for week of ${ws}.</span>`; return; }
                        const report = group.report;
                        let html = `<h3>Week of ${group.report_start}</h3>`;
                        for (const key of ["summary","sentiment","facts","viewpoint","reasoning","trends"]) {
                            const val = report[key]; if (!val || (Array.isArray(val) && !val.length)) continue;
                            const items = Array.isArray(val) ? val : [val];
                            html += `<strong>${key}:</strong><ul>${items.map((s) => `<li>${s}</li>`).join("")}</ul>`;
                        }
                        body.innerHTML = html;
                    }
                    async function loadMonthly(body, p) {
                        if (!p.company) { body.innerHTML = '<span class="placeholder">Select a company.</span>'; return; }
                        const r = await fetch(`/api/company/${encodeURIComponent(p.company)}/news?output_language=zh-CN`); const d = await r.json();
                        const month = p.date ? p.date.slice(0, 7) : currentMonth();
                        const group = (d.groups || []).find((g) => g.type === "monthly" && g.label === month);
                        if (!group || !group.report) { body.innerHTML = `<span class="placeholder">No monthly report for ${month}.</span>`; return; }
                        const report = group.report;
                        let html = `<h3>${month}</h3>`;
                        for (const key of ["summary","sentiment","facts","viewpoint","reasoning","trends"]) {
                            const val = report[key]; if (!val || (Array.isArray(val) && !val.length)) continue;
                            const items = Array.isArray(val) ? val : [val];
                            html += `<strong>${key}:</strong><ul>${items.map((s) => `<li>${s}</li>`).join("")}</ul>`;
                        }
                        body.innerHTML = html;
                    }
                    async function loadEarnings(body, p) {
                        if (!p.company) { body.innerHTML = '<span class="placeholder">Select a company.</span>'; return; }
                        const r = await fetch(`/api/company/${encodeURIComponent(p.company)}/earnings/reports?limit=1`); const d = await r.json();
                        const report = (d.reports || [])[0];
                        if (!report) { body.innerHTML = '<span class="placeholder">No earnings data.</span>'; return; }
                        const fin = report.financials || {};
                        function xv(v) { if (v==null) return null; if (typeof v==="object") return v.value??v.amount??null; return v; }
                        function fmtB(n) { if (n==null) return "—"; return Math.abs(n)>=1000 ? "$"+(n/1000).toFixed(1)+"B" : "$"+n.toLocaleString()+"M"; }
                        const rows = [["Revenue",fmtB(xv(fin.revenue))],["EPS",xv(fin.diluted_eps)!=null?"$"+xv(fin.diluted_eps):"—"],["Op. Margin",xv(fin.operating_margin_pct)!=null?xv(fin.operating_margin_pct)+"%":"—"],["Net Income",fmtB(xv(fin.net_income))],["FCF",fmtB(xv(fin.free_cash_flow))]];
                        let html = `<h3>${report.fiscal_year} ${report.fiscal_quarter}</h3>`;
                        html += rows.map(([l,v]) => `<div class="metric-row"><span class="metric-label">${l}</span><span class="metric-value">${v}</span></div>`).join("");
                        const a = (report.analysis || {}).analysis || {};
                        if (a.executive_summary) html += `<p style="margin-top:8px;font-size:12px;">${a.executive_summary}</p>`;
                        body.innerHTML = html;
                    }

                    // --- Add / Reset ---
                    document.getElementById("add-btn").addEventListener("click", () => { document.getElementById("add-dropdown").classList.toggle("show"); });
                    document.getElementById("add-dropdown").querySelectorAll("button").forEach((btn) => {
                        btn.addEventListener("click", () => {
                            const type = btn.dataset.type;
                            const cfg = PANEL_TYPES.find((t) => t.value === type);
                            panels.push({ id: "p" + (nextId++), type, company: cfg && cfg.needsCompany ? (companies[0] || null) : null, date: null, colSpan: 1, rowSpan: 1 });
                            saveLayout(); renderGrid();
                            document.getElementById("add-dropdown").classList.remove("show");
                        });
                    });
                    document.addEventListener("click", (e) => { if (!e.target.closest("#add-btn") && !e.target.closest("#add-dropdown")) document.getElementById("add-dropdown").classList.remove("show"); });
                    document.getElementById("reset-btn").addEventListener("click", () => { localStorage.removeItem(STORAGE_KEY); panels = defaultLayout(); renderGrid(); });

                    // --- Init ---
                    async function init() {
                        await fetchCompanies();
                        loadLayout();
                        if (!panels.length) panels = defaultLayout();
                        nextId = Math.max(100, ...panels.map((p) => parseInt(String(p.id).replace("p",""),10) || 0)) + 1;
                        renderGrid();
                    }
                    init();
                </script>
            </body>
        </html>
    """
