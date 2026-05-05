"""Daily news report page — view daily reports by company."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_daily_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Daily</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" />
                <style>
                    {BASE_PAGE_STYLES}
                    .page-controls {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
                    .company-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
                    .company-pill {{ padding: 5px 14px; border: 1px solid #d1d5db; border-radius: 16px; background: #fff; cursor: pointer; font-size: 13px; color: #333; }}
                    .company-pill:hover {{ background: #f5f5f5; }}
                    .company-pill.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
                    .date-input {{ padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; width: 120px; text-align: center; cursor: pointer; }}
                    .report-section {{ margin-top: 16px; }}
                    .report-card {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 20px 24px; margin-bottom: 12px; }}
                    .report-card h3 {{ margin: 0 0 10px; font-size: 15px; color: #333; }}
                    .report-body {{ font-size: 14px; line-height: 1.7; }}
                    .cluster {{ margin-bottom: 12px; }}
                    .cluster-title {{ font-weight: 600; font-size: 14px; margin-bottom: 4px; }}
                    .cluster-summary {{ font-size: 13px; color: #444; line-height: 1.6; }}
                    .news-item {{ padding: 8px 0; border-bottom: 1px solid #eee; font-size: 13px; }}
                    .news-item:last-child {{ border-bottom: none; }}
                    .news-meta {{ font-size: 12px; color: #888; margin-top: 2px; }}
                    .placeholder {{ color: #999; font-style: italic; }}
                    .refresh-btn {{ padding: 5px 14px; border: none; border-radius: 6px; background: #16a34a; color: #fff; cursor: pointer; font-size: 13px; }}
                    .refresh-btn:hover {{ background: #15803d; }}
                </style>
            </head>
            <body class="report">
                {render_nav("daily")}
                <div class="container">
                    <section class="card">
                        <div class="page-controls">
                            <div class="company-pills" id="company-pills"></div>
                            <input type="text" id="date-picker" class="date-input" />
                            <button class="refresh-btn" id="refresh-btn" type="button">Refresh</button>
                        </div>
                    </section>
                    <div id="content" class="report-section">
                        <p class="placeholder">Select a company to view daily report.</p>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    let companies = [];
                    let activeCompany = null;
                    let selectedDate = null;
                    let allGroups = [];

                    function localDateText(d) {{
                        if (!d) d = new Date();
                        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
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
                        allGroups = (data.groups || []).filter((g) => g.type === "daily");
                        renderForDate();
                    }}

                    function renderForDate() {{
                        const contentEl = document.getElementById("content");
                        const target = selectedDate || localDateText();
                        const group = allGroups.find((g) => g.label === target || g.key === `day-${{target}}`);
                        if (!group) {{
                            contentEl.innerHTML = `<div class="report-card"><p class="placeholder">No daily data for ${{activeCompany}} on ${{target}}.</p></div>`;
                            return;
                        }}
                        let html = "";
                        const report = group.daily_report;
                        if (report && report.output_text) {{
                            html += `<div class="report-card"><h3>Daily Report</h3><div class="report-body">${{renderMarkdown(report.output_text)}}</div></div>`;
                        }}
                        const clusters = group.daily_clusters || [];
                        if (clusters.length) {{
                            let clusterHtml = clusters.map((c) => `<div class="cluster"><div class="cluster-title">${{c.cluster_title || ""}}</div><div class="cluster-summary">${{renderMarkdown(c.cluster_summary || "")}}</div></div>`).join("");
                            html += `<div class="report-card"><h3>News Clusters</h3>${{clusterHtml}}</div>`;
                        }}
                        const items = group.items || [];
                        if (items.length) {{
                            const newsHtml = items.map((item) => {{
                                const link = item.news_source_link ? `<a href="${{item.news_source_link}}" target="_blank" style="color:#2563eb;">${{item.news_title}}</a>` : item.news_title;
                                return `<div class="news-item">${{link}}<div class="news-meta">${{item.news_source || ""}} · ${{item.news_date_time || ""}}</div></div>`;
                            }}).join("");
                            html += `<div class="report-card"><h3>Raw News (${{items.length}})</h3>${{newsHtml}}</div>`;
                        }}
                        if (!html) {{
                            html = `<div class="report-card"><p class="placeholder">No report or news for ${{target}}.</p></div>`;
                        }}
                        contentEl.innerHTML = html;
                    }}

                    document.getElementById("refresh-btn").addEventListener("click", async () => {{
                        if (!activeCompany || !selectedDate) return;
                        const btn = document.getElementById("refresh-btn");
                        btn.disabled = true; btn.textContent = "Refreshing...";
                        try {{
                            await fetch(`/api/company/${{encodeURIComponent(activeCompany)}}/refresh?start_date=${{selectedDate}}&end_date=${{selectedDate}}&output_language=zh-CN`, {{method: "POST"}});
                            await loadData();
                        }} finally {{ btn.disabled = false; btn.textContent = "Refresh"; }}
                    }});

                    if (window.flatpickr) {{
                        selectedDate = localDateText();
                        const fp = window.flatpickr(document.getElementById("date-picker"), {{
                            dateFormat: "Y-m-d",
                            defaultDate: selectedDate,
                            maxDate: localDateText(),
                            onChange: function(dates) {{
                                if (!dates.length) return;
                                selectedDate = localDateText(dates[0]);
                                renderForDate();
                            }},
                        }});
                    }}

                    loadCompanies();
                </script>
            </body>
        </html>
    """
