"""Weekly news report page — view weekly reports by company."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_weekly_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Weekly</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" />
                <style>
                    {BASE_PAGE_STYLES}
                    .page-controls {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
                    .company-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
                    .company-pill {{ padding: 5px 14px; border: 1px solid #d1d5db; border-radius: 16px; background: #fff; cursor: pointer; font-size: 13px; color: #333; }}
                    .company-pill:hover {{ background: #f5f5f5; }}
                    .company-pill.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
                    .date-input {{ padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; width: 180px; text-align: center; cursor: pointer; }}
                    .report-section {{ margin-top: 16px; }}
                    .report-card {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 20px 24px; margin-bottom: 12px; }}
                    .report-card h3 {{ margin: 0 0 10px; font-size: 15px; color: #333; }}
                    .report-body {{ font-size: 14px; line-height: 1.7; }}
                    .report-body ul {{ padding-left: 20px; }}
                    .report-body li {{ margin-bottom: 4px; }}
                    .placeholder {{ color: #999; font-style: italic; }}
                    .refresh-btn {{ padding: 5px 14px; border: none; border-radius: 6px; background: #16a34a; color: #fff; cursor: pointer; font-size: 13px; }}
                    .refresh-btn:hover {{ background: #15803d; }}
                    .news-item {{ padding: 8px 0; border-bottom: 1px solid #eee; font-size: 13px; }}
                    .news-item:last-child {{ border-bottom: none; }}
                    .news-meta {{ font-size: 12px; color: #888; margin-top: 2px; }}
                </style>
            </head>
            <body class="report">
                {render_nav("weekly")}
                <div class="container">
                    <section class="card">
                        <div class="page-controls">
                            <div class="company-pills" id="company-pills"></div>
                            <input type="text" id="date-picker" class="date-input" />
                            <button class="refresh-btn" id="generate-btn" type="button">Generate Report</button>
                        </div>
                    </section>
                    <div id="content" class="report-section">
                        <p class="placeholder">Select a company to view weekly report.</p>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    let companies = [];
                    let activeCompany = null;
                    let currentWeekStart = null;
                    let currentWeekEnd = null;
                    let allGroups = [];

                    const WEEK_START_DAY = 6; // Saturday (JS: 0=Sun, 6=Sat)
                    function weekBoundaries(d) {{
                        const offset = (d.getDay() - WEEK_START_DAY + 7) % 7;
                        const start = new Date(d);
                        start.setDate(d.getDate() - offset);
                        const end = new Date(start);
                        end.setDate(start.getDate() + 6);
                        return [start, end];
                    }}
                    function localDateText(d) {{
                        if (!d) d = new Date();
                        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
                    }}
                    function renderMarkdown(text) {{
                        if (!text) return "";
                        try {{ return marked.parse(text); }} catch {{ return text; }}
                    }}
                    function setWeekFromDate(d) {{
                        const [ws, we] = weekBoundaries(d);
                        currentWeekStart = localDateText(ws);
                        currentWeekEnd = localDateText(we);
                        document.getElementById("date-picker").value = `Week of ${{currentWeekStart}}`;
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
                        allGroups = (data.groups || []).filter((g) => g.type === "weekly");
                        renderForWeek();
                    }}

                    function renderForWeek() {{
                        const contentEl = document.getElementById("content");
                        if (!currentWeekStart) {{ contentEl.innerHTML = '<p class="placeholder">Select a week.</p>'; return; }}
                        const group = allGroups.find((g) => g.report_start === currentWeekStart);
                        if (!group) {{
                            contentEl.innerHTML = `<div class="report-card"><p class="placeholder">No weekly report for ${{activeCompany}} (${{currentWeekStart}} ~ ${{currentWeekEnd}}).</p><p class="placeholder">Click "Generate Report" to create one.</p></div>`;
                            return;
                        }}
                        let html = "";
                        const report = group.report;
                        if (report) {{
                            const sections = [
                                ["Summary", report.summary],
                                ["Sentiment", report.sentiment],
                                ["Facts", report.facts],
                                ["Viewpoint", report.viewpoint],
                                ["Reasoning", report.reasoning],
                                ["Uncertainties", report.uncertainties],
                                ["Short-term Impact", report.short_term_impact],
                                ["Long-term Impact", report.long_term_impact],
                                ["Trends", report.trends],
                            ];
                            const body = sections.map(([title, items]) => {{
                                if (!items || !items.length) return "";
                                const bullets = (Array.isArray(items) ? items : [items]).map((s) => `<li>${{s}}</li>`).join("");
                                return `<div><strong>${{title}}:</strong><ul>${{bullets}}</ul></div>`;
                            }}).filter(Boolean).join("");
                            html += `<div class="report-card"><h3>Weekly Report (${{group.report_start}} ~ ${{group.report_end}})</h3><div class="report-body">${{body || '<p class="placeholder">Report has no sections.</p>'}}</div></div>`;
                        }} else {{
                            html += `<div class="report-card"><p class="placeholder">No report generated yet. Click "Generate Report".</p></div>`;
                        }}
                        const items = group.items || [];
                        if (items.length) {{
                            const newsHtml = items.map((item) => {{
                                const link = item.news_source_link ? `<a href="${{item.news_source_link}}" target="_blank" style="color:#2563eb;">${{item.news_title}}</a>` : item.news_title;
                                return `<div class="news-item">${{link}}<div class="news-meta">${{item.news_source || ""}} · ${{item.news_date_time || ""}}</div></div>`;
                            }}).join("");
                            html += `<div class="report-card"><h3>Source Articles (${{items.length}})</h3>${{newsHtml}}</div>`;
                        }}
                        contentEl.innerHTML = html;
                    }}

                    document.getElementById("generate-btn").addEventListener("click", async () => {{
                        if (!activeCompany || !currentWeekStart) return;
                        const btn = document.getElementById("generate-btn");
                        btn.disabled = true; btn.textContent = "Generating...";
                        try {{
                            await fetch(`/api/company/${{encodeURIComponent(activeCompany)}}/report?week_date=${{encodeURIComponent(currentWeekStart)}}&output_language=zh-CN`, {{method: "POST"}});
                            await loadData();
                        }} finally {{ btn.disabled = false; btn.textContent = "Generate Report"; }}
                    }});

                    if (window.flatpickr) {{
                        setWeekFromDate(new Date());
                        window.flatpickr(document.getElementById("date-picker"), {{
                            dateFormat: "Y-m-d",
                            maxDate: localDateText(),
                            locale: {{ firstDayOfWeek: 6 }},
                            onChange: function(dates) {{
                                if (!dates.length) return;
                                setWeekFromDate(dates[0]);
                                renderForWeek();
                            }},
                        }});
                    }}

                    loadCompanies();
                </script>
            </body>
        </html>
    """
