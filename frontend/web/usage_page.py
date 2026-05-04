"""LLM usage monitoring dashboard page."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_usage_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Cost</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .usage-hero {{ display: flex; justify-content: space-between; align-items: center; }}
                    .usage-title {{ font-size: 1.5rem; font-weight: 600; margin: 0; }}
                    .usage-subtitle {{ font-size: 0.85rem; color: #888; margin-top: 4px; }}
                    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }}
                    .summary-card {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 14px 16px; text-align: center; }}
                    .summary-card .value {{ font-size: 1.4rem; font-weight: 700; color: #1a1a1a; }}
                    .summary-card .label {{ font-size: 0.75rem; color: #888; margin-top: 4px; }}
                    .range-btns {{ display: flex; gap: 6px; }}
                    .range-btns button {{ padding: 5px 16px; border: 1px solid #d1d5db; border-radius: 6px; background: #f5f5f5; cursor: pointer; font-size: 0.8rem; color: #333; }}
                    .range-btns button:hover {{ background: #e5e5e5; }}
                    .range-btns button.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
                    .date-input {{ padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.8rem; width: 120px; text-align: center; cursor: pointer; }}
                    .flatpickr-day .day-cost {{ display: block; font-size: 8px; line-height: 1; margin-top: -2px; }}
                    .flatpickr-day.has-cost {{ background: #f0fdf4; }}
                    .flatpickr-day.has-cost:hover {{ background: #dcfce7; }}
                    .flatpickr-day.has-cost .day-cost {{ color: #16a34a; }}
                    .usage-controls {{ display: flex; gap: 10px; align-items: center; }}
                    .usage-section {{ margin-top: 16px; }}
                    .usage-section h3 {{ font-size: 1rem; margin: 0 0 10px; color: #333; }}
                    table.usage-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
                    table.usage-table th {{ text-align: left; padding: 8px; background: #f9f9f9; border-bottom: 2px solid #ddd; font-weight: 600; font-size: 12px; color: #555; }}
                    table.usage-table td {{ padding: 8px; border-bottom: 1px solid #eee; }}
                    .cost {{ color: #dc2626; font-weight: 600; }}
                    .tokens {{ color: #555; }}
                    .muted {{ color: #999; font-size: 13px; }}
                </style>
            </head>
            <body class="report">
                {render_nav("cost")}
                <div class="container">
                    <section class="card">
                        <div class="usage-hero">
                            <div>
                                <h1 class="usage-title">LLM Usage & Cost</h1>
                                <p class="usage-subtitle">Monitor API spend across providers, models, and modules</p>
                            </div>
                            <div class="usage-controls">
                            <input type="text" id="usage-date" class="date-input" placeholder="Pick a date" />
                            <div class="range-btns" id="range-btns">
                                <button data-days="1">Today</button>
                                <button data-days="7" class="active">7 Days</button>
                                <button data-days="30">30 Days</button>
                            </div>
                        </div>
                        </div>
                    </section>

                    <div class="summary-grid" id="summary-grid"></div>

                    <section class="card usage-section">
                        <h3>Cost by Model</h3>
                        <table class="usage-table" id="model-table">
                            <thead><tr><th>Provider</th><th>Model</th><th>Requests</th><th>Tokens</th><th>Cost</th></tr></thead>
                            <tbody></tbody>
                        </table>
                    </section>

                    <section class="card usage-section">
                        <h3>Cost by Module</h3>
                        <table class="usage-table" id="module-table">
                            <thead><tr><th>Module</th><th>Requests</th><th>Tokens</th><th>Cost</th></tr></thead>
                            <tbody></tbody>
                        </table>
                    </section>

                    <section class="card usage-section">
                        <h3>Cost by Company</h3>
                        <table class="usage-table" id="company-table">
                            <thead><tr><th>Company</th><th>Requests</th><th>Tokens</th><th>Cost</th></tr></thead>
                            <tbody></tbody>
                        </table>
                    </section>

                    <section class="card usage-section">
                        <h3>Recent Requests</h3>
                        <table class="usage-table" id="requests-table">
                            <thead><tr><th>Time</th><th>Purpose</th><th>Company</th><th>Model</th><th>Input</th><th>Output</th><th>Cached</th><th>Cost</th><th>Time(ms)</th></tr></thead>
                            <tbody></tbody>
                        </table>
                        <div style="margin-top:10px;text-align:center;">
                            <button id="load-more-btn" style="padding:6px 20px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer;font-size:13px;">Load More</button>
                        </div>
                    </section>
                </div>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" />
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script>
                    let currentDays = 7;
                    let selectedDate = null;
                    let requestOffset = 0;
                    const REQUEST_LIMIT = 50;
                    let dailyCostMap = {{}};

                    function fmtCost(v) {{
                        if (v == null || v === 0) return "$0.00";
                        if (v < 0.01) return "$" + v.toFixed(4);
                        return "$" + v.toFixed(2);
                    }}
                    function fmtCostShort(v) {{
                        if (v == null || v === 0) return "";
                        if (v < 0.01) return "$" + v.toFixed(3);
                        if (v < 1) return "$" + v.toFixed(2);
                        return "$" + v.toFixed(1);
                    }}
                    function fmtTokens(v) {{
                        if (!v) return "0";
                        if (v >= 1000000) return (v / 1000000).toFixed(1) + "M";
                        if (v >= 1000) return (v / 1000).toFixed(1) + "K";
                        return v.toLocaleString();
                    }}
                    function fmtTime(iso) {{
                        if (!iso) return "—";
                        return iso.replace("T", " ").slice(0, 19);
                    }}

                    function queryParams() {{
                        if (selectedDate) return `date=${{selectedDate}}`;
                        return `days=${{currentDays}}`;
                    }}

                    async function loadSummary() {{
                        const resp = await fetch(`/api/llm-usage/summary?${{queryParams()}}`);
                        const data = await resp.json();
                        const grid = document.getElementById("summary-grid");
                        const avgCost = data.total_requests ? data.total_cost / data.total_requests : 0;
                        grid.innerHTML = `
                            <div class="summary-card"><div class="value cost">${{fmtCost(data.total_cost)}}</div><div class="label">Total Cost</div></div>
                            <div class="summary-card"><div class="value">${{data.total_requests || 0}}</div><div class="label">Requests</div></div>
                            <div class="summary-card"><div class="value">${{fmtTokens(data.total_prompt_tokens)}}</div><div class="label">Input Tokens</div></div>
                            <div class="summary-card"><div class="value">${{fmtTokens(data.total_completion_tokens)}}</div><div class="label">Output Tokens</div></div>
                            <div class="summary-card"><div class="value" style="color:#2563eb;">${{fmtTokens(data.total_cached_tokens)}}</div><div class="label">Cached Tokens</div></div>
                            <div class="summary-card"><div class="value cost">${{fmtCost(avgCost)}}</div><div class="label">Avg/Request</div></div>
                        `;
                        const modelTbody = document.querySelector("#model-table tbody");
                        modelTbody.innerHTML = (data.by_model || []).map((r) =>
                            `<tr><td>${{r.provider}}</td><td>${{r.model}}</td><td>${{r.requests}}</td><td class="tokens">${{fmtTokens(r.tokens)}}</td><td class="cost">${{fmtCost(r.cost)}}</td></tr>`
                        ).join("") || '<tr><td colspan="5" class="muted">No data</td></tr>';
                    }}

                    async function loadByModule() {{
                        const resp = await fetch(`/api/llm-usage/by-module?${{queryParams()}}`);
                        const data = await resp.json();
                        const tbody = document.querySelector("#module-table tbody");
                        tbody.innerHTML = (data.modules || []).map((r) =>
                            `<tr><td>${{r.module || "—"}}</td><td>${{r.requests}}</td><td class="tokens">${{fmtTokens(r.tokens)}}</td><td class="cost">${{fmtCost(r.cost)}}</td></tr>`
                        ).join("") || '<tr><td colspan="4" class="muted">No data</td></tr>';
                    }}

                    async function loadByCompany() {{
                        const resp = await fetch(`/api/llm-usage/by-company?${{queryParams()}}`);
                        const data = await resp.json();
                        const tbody = document.querySelector("#company-table tbody");
                        tbody.innerHTML = (data.companies || []).map((r) =>
                            `<tr><td>${{r.company_name || "—"}}</td><td>${{r.requests}}</td><td class="tokens">${{fmtTokens(r.tokens)}}</td><td class="cost">${{fmtCost(r.cost)}}</td></tr>`
                        ).join("") || '<tr><td colspan="4" class="muted">No data</td></tr>';
                    }}

                    async function loadRequests(append) {{
                        if (!append) requestOffset = 0;
                        const resp = await fetch(`/api/llm-usage/requests?${{queryParams()}}&limit=${{REQUEST_LIMIT}}&offset=${{requestOffset}}`);
                        const data = await resp.json();
                        const tbody = document.querySelector("#requests-table tbody");
                        const rows = (data.requests || []).map((r) =>
                            `<tr><td style="white-space:nowrap;font-size:12px;">${{fmtTime(r.created_at)}}</td><td>${{r.purpose}}</td><td>${{r.company_name || "—"}}</td><td>${{r.model}}</td><td class="tokens">${{fmtTokens(r.prompt_tokens)}}</td><td class="tokens">${{fmtTokens(r.completion_tokens)}}</td><td style="color:#2563eb;">${{r.cached_tokens ? fmtTokens(r.cached_tokens) : "—"}}</td><td class="cost">${{fmtCost(r.cost_usd)}}</td><td>${{r.response_time_ms ? r.response_time_ms.toLocaleString() : "—"}}</td></tr>`
                        ).join("");
                        if (append) tbody.innerHTML += rows;
                        else tbody.innerHTML = rows || '<tr><td colspan="7" class="muted">No requests yet</td></tr>';
                        requestOffset += (data.requests || []).length;
                        document.getElementById("load-more-btn").style.display = (data.requests || []).length < REQUEST_LIMIT ? "none" : "";
                    }}

                    async function loadAll() {{
                        await Promise.all([loadSummary(), loadByModule(), loadByCompany(), loadRequests(false)]);
                    }}

                    document.getElementById("range-btns").addEventListener("click", (e) => {{
                        const btn = e.target.closest("button");
                        if (!btn) return;
                        selectedDate = null;
                        currentDays = parseInt(btn.dataset.days, 10);
                        document.querySelectorAll("#range-btns button").forEach((b) => b.classList.remove("active"));
                        btn.classList.add("active");
                        document.getElementById("usage-date").value = "";
                        loadAll();
                    }});

                    document.getElementById("load-more-btn").addEventListener("click", () => loadRequests(true));

                    function localDateText(d) {{
                        const year = d.getFullYear();
                        const month = String(d.getMonth() + 1).padStart(2, "0");
                        const day = String(d.getDate()).padStart(2, "0");
                        return `${{year}}-${{month}}-${{day}}`;
                    }}

                    async function initCalendar() {{
                        const resp = await fetch("/api/llm-usage/daily-costs?days=90");
                        const data = await resp.json();
                        (data.daily || []).forEach((d) => {{ dailyCostMap[d.day] = d.cost; }});

                        if (window.flatpickr) {{
                            window.flatpickr(document.getElementById("usage-date"), {{
                                dateFormat: "Y-m-d",
                                maxDate: localDateText(new Date()),
                                onDayCreate: function(_dObj, _dStr, _fp, dayElem) {{
                                    const dateStr = localDateText(dayElem.dateObj);
                                    const cost = dailyCostMap[dateStr];
                                    const badge = document.createElement("span");
                                    badge.className = "day-cost";
                                    if (cost && cost > 0) {{
                                        dayElem.classList.add("has-cost");
                                        badge.textContent = fmtCostShort(cost);
                                    }} else {{
                                        badge.textContent = "$0";
                                        badge.style.color = "#ccc";
                                    }}
                                    dayElem.appendChild(badge);
                                }},
                                onChange: function(dates) {{
                                    if (!dates || !dates.length) return;
                                    selectedDate = localDateText(dates[0]);
                                    document.querySelectorAll("#range-btns button").forEach((b) => b.classList.remove("active"));
                                    loadAll();
                                }},
                            }});
                        }}
                    }}

                    initCalendar();
                    loadAll();
                </script>
            </body>
        </html>
    """
