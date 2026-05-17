"""Monthly news report page — view monthly reports by company."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_monthly_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Monthly</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .page-controls {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
                    .company-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
                    .company-pill {{ padding: 5px 14px; border: 1px solid #d1d5db; border-radius: 16px; background: #fff; cursor: pointer; font-size: 13px; color: #333; }}
                    .company-pill:hover {{ background: #f5f5f5; }}
                    .company-pill.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
                    .month-input {{ padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; width: 120px; text-align: center; }}
                    .report-section {{ margin-top: 16px; }}
                    .report-card {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 20px 24px; margin-bottom: 12px; }}
                    .report-card h3 {{ margin: 0 0 10px; font-size: 15px; color: #333; }}
                    .report-body {{ font-size: 14px; line-height: 1.7; }}
                    .report-body ul {{ padding-left: 20px; }}
                    .report-body li {{ margin-bottom: 4px; }}
                    .placeholder {{ color: #999; font-style: italic; }}
                    .refresh-btn {{ padding: 5px 14px; border: none; border-radius: 6px; background: #16a34a; color: #fff; cursor: pointer; font-size: 13px; }}
                    .refresh-btn:hover {{ background: #15803d; }}
                    .sub-report {{ margin: 10px 0; padding: 10px 14px; background: #f9fafb; border-radius: 6px; border: 1px solid #eee; }}
                    .sub-report h4 {{ margin: 0 0 6px; font-size: 13px; color: #555; }}
                </style>
            </head>
            <body class="report">
                {render_nav("monthly")}
                <div class="container">
                    <section class="card">
                        <div class="page-controls">
                            <div class="company-pills" id="company-pills"></div>
                            <input type="month" id="month-picker" class="month-input" />
                            <button class="refresh-btn" id="generate-btn" type="button">Generate Report</button>
                        </div>
                    </section>
                    <div id="content" class="report-section">
                        <p class="placeholder">Select a company to view monthly report.</p>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    let companies = [];
                    let activeCompany = null;
                    let selectedMonth = null;
                    let allGroups = [];

                    function currentMonth() {{
                        const d = new Date();
                        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0");
                    }}
                    function renderMarkdown(text) {{
                        if (!text) return "";
                        try {{ return marked.parse(text); }} catch {{ return text; }}
                    }}

                    async function loadCompanies() {{
                        const resp = await fetch("/api/companies");
                        const data = await resp.json();
                        companies = (data.company_names || []);
                        renderPills();
                        if (companies.length && !activeCompany) {{
                            setActiveCompany(companies[0]);
                        }}
                    }}

                    function renderPills() {{
                        const el = document.getElementById("company-pills");
                        el.innerHTML = companies.map((name) => {{
                            const cls = name === activeCompany ? "company-pill active" : "company-pill";
                            return `<button class="${{cls}}" data-company="${{name}}">${{name}}</button>`;
                        }}).join("");
                        el.querySelectorAll(".company-pill").forEach((btn) => {{
                            btn.addEventListener("click", () => setActiveCompany(btn.dataset.company));
                        }});
                    }}

                    function setActiveCompany(name) {{
                        activeCompany = name;
                        renderPills();
                        loadData();
                    }}

                    async function loadData() {{
                        if (!activeCompany) return;
                        const contentEl = document.getElementById("content");
                        contentEl.innerHTML = '<p class="placeholder">Loading...</p>';
                        const resp = await fetch(`/api/company/${{encodeURIComponent(activeCompany)}}/news?output_language=zh-CN`);
                        const data = await resp.json();
                        allGroups = (data.groups || []).filter((g) => g.type === "monthly");
                        renderForMonth();
                    }}

                    function renderForMonth() {{
                        const contentEl = document.getElementById("content");
                        const target = selectedMonth || currentMonth();
                        const group = allGroups.find((g) => g.label === target);
                        if (!group) {{
                            contentEl.innerHTML = `<div class="report-card"><p class="placeholder">No monthly data for ${{activeCompany}} (${{target}}).</p><p class="placeholder">Click "Generate Report" to create one.</p></div>`;
                            return;
                        }}
                        let html = "";
                        const report = group.report;
                        if (report) {{
                            const sections = [
                                ["Summary", report.summary],
                                ["Key Storylines", report.key_storylines],
                                ["Structural Changes", report.structural_changes],
                                ["Catalysts Ahead", report.catalysts_ahead],
                                ["Sentiment", report.sentiment],
                                ["Viewpoint", report.viewpoint],
                                ["Reasoning", report.reasoning],
                                ["Trends", report.trends],
                            ];
                            const body = sections.map(([title, items]) => {{
                                if (!items || !items.length) return "";
                                const bullets = (Array.isArray(items) ? items : [items]).map((s) => `<li>${{s}}</li>`).join("");
                                return `<div><strong>${{title}}:</strong><ul>${{bullets}}</ul></div>`;
                            }}).filter(Boolean).join("");
                            html += `<div class="report-card"><h3>Monthly Report (${{group.report_start}} ~ ${{group.report_end}})</h3><div class="report-body">${{body || '<p class="placeholder">Report has no sections.</p>'}}</div></div>`;
                        }} else {{
                            html += `<div class="report-card"><p class="placeholder">No monthly report generated yet. Click "Generate Report".</p></div>`;
                        }}
                        const weekItems = group.items || [];
                        if (weekItems.length) {{
                            const weeksHtml = weekItems.map((w) => {{
                                const weekReport = w.report;
                                let inner = `<h4>${{w.news_title || "Week"}} (${{w.report_start}} ~ ${{w.report_end}})</h4>`;
                                if (weekReport && weekReport.summary) {{
                                    const bullets = (Array.isArray(weekReport.summary) ? weekReport.summary : [weekReport.summary]).map((s) => `<li>${{s}}</li>`).join("");
                                    inner += `<ul>${{bullets}}</ul>`;
                                }} else {{
                                    inner += '<p class="placeholder">No weekly report.</p>';
                                }}
                                return `<div class="sub-report">${{inner}}</div>`;
                            }}).join("");
                            html += `<div class="report-card"><h3>Weekly Reports in Month</h3>${{weeksHtml}}</div>`;
                        }}
                        contentEl.innerHTML = html;
                    }}

                    document.getElementById("generate-btn").addEventListener("click", async () => {{
                        if (!activeCompany || !selectedMonth) return;
                        const btn = document.getElementById("generate-btn");
                        btn.disabled = true; btn.textContent = "Generating...";
                        try {{
                            await fetch(`/api/company/${{encodeURIComponent(activeCompany)}}/report/month?month=${{encodeURIComponent(selectedMonth)}}&output_language=zh-CN`, {{method: "POST"}});
                            await loadData();
                        }} finally {{ btn.disabled = false; btn.textContent = "Generate Report"; }}
                    }});

                    const monthPicker = document.getElementById("month-picker");
                    selectedMonth = currentMonth();
                    monthPicker.value = selectedMonth;
                    monthPicker.addEventListener("change", () => {{
                        selectedMonth = monthPicker.value;
                        renderForMonth();
                    }});

                    loadCompanies();
                </script>
            </body>
        </html>
    """
