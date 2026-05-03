"""Earnings comparison page — multi-company side-by-side view."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_earnings_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Earnings</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .earnings-hero {{ display: flex; justify-content: space-between; align-items: center; }}
                    .earnings-title {{ font-size: 1.5rem; font-weight: 600; margin: 0; }}
                    .earnings-subtitle {{ font-size: 0.85rem; color: #888; margin-top: 4px; }}
                    .earnings-controls {{ display: flex; gap: 8px; align-items: center; }}
                    .earnings-controls input {{ padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; width: 200px; }}
                    .earnings-controls button {{ padding: 6px 14px; border: none; border-radius: 6px; background: #2563eb; color: #fff; cursor: pointer; font-size: 0.85rem; }}
                    .earnings-controls button:hover {{ background: #1d4ed8; }}
                    .earnings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; margin-top: 16px; }}
                    .earnings-card {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 16px; position: relative; }}
                    .earnings-card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
                    .earnings-card-header h3 {{ margin: 0; font-size: 1rem; }}
                    .earnings-card-header .quarter-badge {{ background: #f0f0f0; padding: 2px 8px; border-radius: 10px; font-size: 11px; color: #555; }}
                    .earnings-card-actions {{ display: flex; gap: 6px; }}
                    .earnings-card-actions button {{ padding: 5px 14px; border: 1px solid #d1d5db; border-radius: 5px; background: #fff; cursor: pointer; font-size: 13px; color: #333; }}
                    .earnings-card-actions button:hover {{ background: #f5f5f5; }}
                    .earnings-card table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
                    .earnings-card th {{ text-align: left; padding: 4px 6px; border-bottom: 2px solid #ddd; font-weight: 600; font-size: 11px; color: #666; }}
                    .earnings-card td {{ padding: 4px 6px; border-bottom: 1px solid #eee; }}
                    .beat {{ color: #16a34a; }}
                    .miss {{ color: #dc2626; }}
                    .earnings-empty {{ text-align: center; color: #999; padding: 40px 0; }}
                    .remove-card-btn {{ position: absolute; top: 8px; right: 8px; background: none; border: none; cursor: pointer; color: #aaa; font-size: 14px; }}
                    .remove-card-btn:hover {{ color: #dc2626; }}
                    .detail-link {{ color: #2563eb; text-decoration: none; font-size: 12px; }}
                    .detail-link:hover {{ text-decoration: underline; }}
                    .kw {{ background: #f0f0f0; padding: 2px 8px; border-radius: 10px; font-size: 11px; display: inline-block; margin: 2px; }}
                </style>
            </head>
            <body class="report">
                {render_nav("earnings")}
                <div class="container">
                    <section class="card">
                        <div class="earnings-hero">
                            <div>
                                <h1 class="earnings-title">Earnings Comparison</h1>
                                <p class="earnings-subtitle">Compare quarterly earnings across companies</p>
                            </div>
                            <div class="earnings-controls">
                                <input type="text" id="add-company-input" placeholder="Add company name..." />
                                <button id="add-company-btn" type="button">Add</button>
                            </div>
                        </div>
                    </section>
                    <div class="earnings-grid" id="earnings-grid"></div>
                    <p class="earnings-empty" id="earnings-empty">Add companies above to compare earnings.</p>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    const gridEl = document.getElementById("earnings-grid");
                    const emptyEl = document.getElementById("earnings-empty");
                    const addInput = document.getElementById("add-company-input");
                    const addBtn = document.getElementById("add-company-btn");
                    const STORAGE_KEY = "marketagent_earnings_companies";

                    function loadSavedCompanies() {{
                        try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }}
                        catch {{ return []; }}
                    }}
                    function saveCompanies(list) {{
                        localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
                    }}

                    let companies = loadSavedCompanies();

                    function fmtNum(v) {{
                        if (v == null) return "—";
                        const n = Number(v);
                        if (isNaN(n)) return String(v);
                        if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
                        if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "K";
                        return n % 1 === 0 ? n.toString() : n.toFixed(2);
                    }}

                    function beatMissHtml(pct) {{
                        if (pct == null) return "—";
                        const cls = pct > 0 ? "beat" : pct < 0 ? "miss" : "";
                        return `<span class="${{cls}}">${{pct > 0 ? "+" : ""}}${{pct}}%</span>`;
                    }}

                    function buildCardHtml(name, report) {{
                        if (!report) {{
                            return `
                                <div class="earnings-card" data-company="${{name}}">
                                    <button class="remove-card-btn" data-company="${{name}}" title="Remove">&times;</button>
                                    <div class="earnings-card-header">
                                        <h3>${{name}}</h3>
                                    </div>
                                    <p style="color:#999;font-size:13px;">No earnings data yet.</p>
                                    <div class="earnings-card-actions">
                                        <button class="fetch-latest-btn" data-company="${{name}}">Fetch Latest</button>
                                        <a class="detail-link" href="/company/${{encodeURIComponent(name)}}?view=earnings">Full Details →</a>
                                    </div>
                                </div>`;
                        }}
                        const fin = report.financials || {{}};
                        const est = report.estimates || {{}};
                        const a = (report.analysis || {{}}).analysis || {{}};
                        const kws = (report.analysis || {{}}).keywords || [];
                        const guidance = (report.analysis || {{}}).guidance || {{}};
                        const cs = report.company_specific || [];

                        function xv(v) {{ if (v == null) return null; if (typeof v === "object" && !Array.isArray(v)) return v.value ?? v.amount ?? null; return v; }}
                        function xyoy(v) {{ if (v == null) return null; if (typeof v === "object" && !Array.isArray(v)) return v.yoy_change_pct ?? v.yoy_growth_pct ?? v.yoy ?? null; return null; }}
                        function fmtDollarM(n) {{
                            const abs = Math.abs(n);
                            if (abs >= 1000) return "$" + (n / 1000).toFixed(1) + "B";
                            return "$" + Number(n).toLocaleString() + "M";
                        }}
                        function fmtRow(label, raw, unit, estObj) {{
                            const val = xv(raw);
                            if (val == null) return "";
                            const yoy = xyoy(raw);
                            let display;
                            if (unit === "%") display = val + "%";
                            else if (unit === "$M") display = fmtDollarM(Number(val));
                            else if (unit === "$") display = "$" + Number(val).toLocaleString();
                            else if (unit === "M") display = Number(val).toLocaleString() + "M";
                            else display = Number(val).toLocaleString();
                            const yoyHtml = yoy != null ? ` <span style="color:${{yoy >= 0 ? '#16a34a' : '#dc2626'}};font-size:11px;">${{yoy >= 0 ? "+" : ""}}${{yoy}}%</span>` : "";
                            const beatHtml = estObj ? beatMissHtml(estObj.beat_miss_pct) : "";
                            return `<tr><td>${{label}}</td><td>${{display}}${{yoyHtml}}</td><td>${{beatHtml}}</td></tr>`;
                        }}

                        const generalRows = [
                            fmtRow("Revenue", fin.revenue, "$M", est.revenue),
                            fmtRow("Cost of Revenue", fin.cost_of_revenue, "$M", null),
                            fmtRow("Gross Profit", fin.gross_profit, "$M", null),
                            fmtRow("Gross Margin", fin.gross_margin_pct, "%", null),
                            fmtRow("Operating Income", fin.operating_income, "$M", null),
                            fmtRow("Op. Margin", fin.operating_margin_pct, "%", null),
                            fmtRow("Net Income", fin.net_income, "$M", null),
                            fmtRow("Diluted EPS", fin.diluted_eps, "$", est.eps),
                            fmtRow("CapEx", fin.capex, "$M", null),
                            fmtRow("Free Cash Flow", fin.free_cash_flow, "$M", null),
                            fmtRow("Op. Cash Flow", fin.operating_cash_flow, "$M", null),
                            fmtRow("R&D Expense", fin.r_and_d_expense, "$M", null),
                            fmtRow("SG&A Expense", fin.sga_expense, "$M", null),
                            fmtRow("Cash & Equiv.", fin.cash_and_equivalents, "$M", null),
                            fmtRow("Total Debt", fin.total_debt, "$M", null),
                            fmtRow("D&A", fin.depreciation_amortization, "$M", null),
                            fmtRow("Shares Out.", fin.shares_outstanding_diluted, "M", null),
                        ].filter(Boolean).join("");

                        function fmtMetricInline(obj) {{
                            if (typeof obj === "string" || typeof obj === "number") return String(obj);
                            if (!obj || typeof obj !== "object") return "";
                            const parts = [];
                            const val = obj.amount ?? obj.value ?? obj.revenue ?? null;
                            if (val != null) parts.push(fmtDollarM(Number(val)));
                            const growth = obj.growth_yoy_pct ?? obj.yoy_growth_pct ?? obj.yoy_change_pct ?? obj.growth ?? null;
                            if (growth != null) {{
                                const c = growth >= 0 ? "#16a34a" : "#dc2626";
                                parts.push(`<span style="color:${{c}}">${{growth >= 0 ? "+" : ""}}${{growth}}%</span>`);
                            }}
                            return parts.length ? parts.join(" · ") : "";
                        }}

                        let csHtml = "";
                        if (cs.length) {{
                            const csRows = cs.map((sec) => {{
                                const title = sec.title || "";
                                let inner = "";
                                if (sec.data && Array.isArray(sec.data)) {{
                                    inner = sec.data.map((item) => {{
                                        if (item && typeof item === "object" && item.name) {{
                                            const metric = fmtMetricInline(item);
                                            if (!metric) return "";
                                            return `<tr><td style="padding-left:16px;">${{item.name}}</td><td>${{metric}}</td><td></td></tr>`;
                                        }}
                                        const metric = fmtMetricInline(item);
                                        if (!metric) return "";
                                        return `<tr><td style="padding-left:16px;" colspan="3">${{metric}}</td></tr>`;
                                    }}).filter(Boolean).join("");
                                }} else if (sec.data && typeof sec.data === "object") {{
                                    inner = Object.entries(sec.data).map(([k, v]) => {{
                                        const metric = typeof v === "object" ? fmtMetricInline(v) : String(v ?? "");
                                        if (!metric) return "";
                                        return `<tr><td style="padding-left:16px;">${{k.replace(/_/g, " ")}}</td><td>${{metric}}</td><td></td></tr>`;
                                    }}).filter(Boolean).join("");
                                }}
                                if (!inner) return "";
                                return `<tr><td colspan="3" style="font-weight:600;padding:6px 8px 2px;border-top:1px solid #eee;">${{title}}</td></tr>${{inner}}`;
                            }}).filter(Boolean).join("");
                            if (csRows) csHtml = `<tr><td colspan="3" style="font-weight:700;padding:10px 8px 4px;border-top:2px solid #ddd;">Company Specific</td></tr>${{csRows}}`;
                        }}

                        const summary = a.executive_summary || "";
                        const summaryHtml = summary ? `<p style="font-size:12px;color:#444;line-height:1.5;margin:8px 0;">${{summary}}</p>` : "";

                        const guidanceHtml = guidance.next_quarter || guidance.full_year
                            ? `<div style="font-size:11px;color:#555;margin:6px 0;">${{
                                guidance.next_quarter ? `<div><strong>Next Q:</strong> Rev ${{guidance.next_quarter.revenue_range || "—"}} · EPS ${{guidance.next_quarter.eps_range || "—"}}</div>` : ""
                              }}${{
                                guidance.full_year ? `<div><strong>Full Year:</strong> Rev ${{guidance.full_year.revenue_range || "—"}} · EPS ${{guidance.full_year.eps_range || "—"}}</div>` : ""
                              }}</div>`
                            : "";

                        const kwHtml = kws.slice(0, 8).map((k) => `<span class="kw">${{k}}</span>`).join("");

                        return `
                            <div class="earnings-card" data-company="${{name}}">
                                <button class="remove-card-btn" data-company="${{name}}" title="Remove">&times;</button>
                                <div class="earnings-card-header">
                                    <h3>${{name}}</h3>
                                    <span class="quarter-badge">${{report.fiscal_year}} ${{report.fiscal_quarter}}</span>
                                </div>
                                ${{summaryHtml}}
                                <table><thead><tr><th>Metric</th><th>Value</th><th>vs Est</th></tr></thead><tbody>${{generalRows}}${{csHtml}}</tbody></table>
                                ${{guidanceHtml}}
                                ${{kwHtml ? `<div style="margin-top:8px;">${{kwHtml}}</div>` : ""}}
                                <div class="earnings-card-actions" style="margin-top:10px;">
                                    <button class="fetch-latest-btn" data-company="${{name}}" data-fy="${{report.fiscal_year}}" data-fq="${{report.fiscal_quarter}}">Refresh</button>
                                    <a class="detail-link" href="/company/${{encodeURIComponent(name)}}?view=earnings">Full Details →</a>
                                </div>
                            </div>`;
                    }}

                    async function loadCompanyReport(name) {{
                        try {{
                            const resp = await fetch(`/api/company/${{encodeURIComponent(name)}}/earnings/reports?limit=1`);
                            const data = await resp.json();
                            return (data.reports || [])[0] || null;
                        }} catch {{ return null; }}
                    }}

                    async function renderGrid() {{
                        if (!companies.length) {{
                            gridEl.innerHTML = "";
                            emptyEl.style.display = "";
                            return;
                        }}
                        emptyEl.style.display = "none";
                        gridEl.innerHTML = companies.map((name) => buildCardHtml(name, null)).join("");

                        for (const name of companies) {{
                            const report = await loadCompanyReport(name);
                            const card = gridEl.querySelector(`[data-company="${{name}}"]`);
                            if (card && report) {{
                                card.outerHTML = buildCardHtml(name, report);
                            }}
                        }}
                        wireCardButtons();
                    }}

                    function wireCardButtons() {{
                        gridEl.querySelectorAll(".remove-card-btn").forEach((btn) => {{
                            btn.addEventListener("click", () => {{
                                const name = btn.dataset.company;
                                companies = companies.filter((c) => c !== name);
                                saveCompanies(companies);
                                renderGrid();
                            }});
                        }});
                        gridEl.querySelectorAll(".fetch-latest-btn").forEach((btn) => {{
                            btn.addEventListener("click", async () => {{
                                const name = btn.dataset.company;
                                const fy = btn.dataset.fy;
                                const fq = btn.dataset.fq;
                                btn.disabled = true;
                                btn.textContent = "Fetching...";
                                try {{
                                    if (fy && fq) {{
                                        await fetch(`/api/company/${{encodeURIComponent(name)}}/earnings/reports/refresh?fiscal_year=${{encodeURIComponent(fy)}}&fiscal_quarter=${{encodeURIComponent(fq)}}`, {{ method: "POST" }});
                                    }} else {{
                                        await fetch(`/api/company/${{encodeURIComponent(name)}}/earnings/reports/fetch-latest`, {{ method: "POST" }});
                                    }}
                                    const report = await loadCompanyReport(name);
                                    const card = gridEl.querySelector(`[data-company="${{name}}"]`);
                                    if (card) {{
                                        card.outerHTML = buildCardHtml(name, report);
                                        wireCardButtons();
                                    }}
                                }} catch {{
                                    btn.disabled = false;
                                    btn.textContent = "Retry";
                                }}
                            }});
                        }});
                    }}

                    function addCompany(name) {{
                        const trimmed = name.trim();
                        if (!trimmed) return;
                        if (companies.some((c) => c.toLowerCase() === trimmed.toLowerCase())) return;
                        companies.push(trimmed);
                        saveCompanies(companies);
                        renderGrid();
                    }}

                    addBtn.addEventListener("click", () => {{
                        addCompany(addInput.value);
                        addInput.value = "";
                    }});
                    addInput.addEventListener("keydown", (e) => {{
                        if (e.key === "Enter") {{
                            addCompany(addInput.value);
                            addInput.value = "";
                        }}
                    }});

                    renderGrid();
                </script>
            </body>
        </html>
    """
