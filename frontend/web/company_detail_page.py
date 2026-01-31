"""Company detail page rendering."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from market_agent.llms.news import list_news_models, list_news_providers


def render_company_detail_page(company_name: str) -> str:
    safe_company = company_name.replace('"', "")
    display_company = (
        safe_company[:1].upper() + safe_company[1:] if safe_company else safe_company
    )
    model_options = "".join(
        f'<option value="{model}">{model}</option>'
        for model in list_news_models().get("openai", [])
    )
    provider_options = "".join(
        f'<option value="{provider}">{provider}</option>'
        for provider in list_news_providers()
    )
    return f"""
        <html>
            <head>
                <title>MarketAgent – {display_company}</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .layout {{ display: grid; grid-template-columns: 240px 1fr; gap: 1.5rem; }}
                    .header-row {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        margin-bottom: 1rem;
                    }}
                    .header-actions {{
                        display: flex;
                        align-items: center;
                        gap: 0.5rem;
                    }}
                    .week-input {{
                        padding: 0.45rem 0.6rem;
                        border-radius: 0.5rem;
                        border: 1px solid #d1d5db;
                        font-size: 0.9rem;
                    }}
                    .refresh-btn {{
                        padding: 0.45rem 0.85rem;
                        border-radius: 999px;
                        border: 1px solid #16a34a;
                        background: #16a34a;
                        color: #ffffff;
                        cursor: pointer;
                        font-weight: 600;
                    }}
                    .refresh-btn:hover {{ background: #15803d; }}
                    .timeline {{
                        position: sticky;
                        top: 1.5rem;
                        align-self: start;
                        padding: 0.75rem;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.75rem;
                        background: #f9fafb;
                        max-height: 70vh;
                        overflow-y: auto;
                        display: grid;
                        gap: 0.35rem;
                    }}
                    .timeline-item {{
                        position: relative;
                        display: flex;
                        align-items: center;
                        gap: 0.5rem;
                        padding: 0.35rem 0 0.35rem 0.25rem;
                        cursor: pointer;
                        z-index: 1;
                    }}
                    .timeline-marker {{
                        position: relative;
                        width: 16px;
                        height: 100%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-shrink: 0;
                    }}
                    .timeline-dot {{
                        width: 12px;
                        height: 12px;
                        border-radius: 50%;
                        background: #60a5fa;
                        position: relative;
                        z-index: 1;
                        border: 2px solid #f9fafb;
                    }}
                    .timeline-dot.weekly {{ background: #f59e0b; }}
                    .timeline-label {{ font-size: 0.9rem; color: #374151; }}
                    .report {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                                     "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
                        font-size: 13px;
                        line-height: 1.65;
                        color: #111;
                    }}
                    .report h1 {{
                        font-size: 18px;
                        font-weight: 600;
                        margin-bottom: 8px;
                    }}
                    .report h2 {{
                        font-size: 14px;
                        font-weight: 600;
                        margin: 12px 0 6px;
                    }}
                    .report ul {{
                        padding-left: 16px;
                        margin: 0;
                    }}
                    .report li {{
                        margin-bottom: 6px;
                    }}
                    .report strong {{
                        font-weight: 600;
                    }}
                    .news-card {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.75rem;
                        padding: 1rem;
                        background: #fff;
                        margin-bottom: 1rem;
                        cursor: pointer;
                    }}
                    .news-card h3 {{ margin: 0 0 0.5rem; }}
                    .news-meta {{ color: #6b7280; font-size: 0.85rem; }}
                    .news-content div {{ margin-bottom: 0.4rem; }}
                    .news-summary {{ margin-top: 0.6rem; }}
                    .news-summary strong {{ color: #111827; }}
                    .news-details {{ margin-top: 0.6rem; display: none; }}
                    .news-card.expanded .news-details {{ display: block; }}
                    .news-actions {{
                        display: flex;
                        gap: 0.5rem;
                        margin-top: 0.6rem;
                    }}
                    .news-action-btn {{
                        border: 1px solid #d1d5db;
                        background: #f3f4f6;
                        border-radius: 0.5rem;
                        padding: 0.35rem 0.6rem;
                        font-size: 0.85rem;
                        cursor: pointer;
                    }}
                    .news-action-btn.original {{
                        color: #2563eb;
                        border-color: #bfdbfe;
                        background: #eff6ff;
                    }}
                    .news-action-btn.delete {{
                        color: #b91c1c;
                        border-color: #fecaca;
                        background: #fef2f2;
                    }}
                    .placeholder {{ color: #6b7280; }}
                </style>
            </head>
            <body class="report">
                {render_nav("company")}
                <div class="container">
                    <section class="card report">
                        <div class="header-row">
                            <h1>{display_company}</h1>
                            <div class="header-actions">
                                <select class="week-input" id="news-provider">
                                    {provider_options}
                                </select>
                                <select class="week-input" id="news-model">
                                    {model_options}
                                </select>
                                <input class="week-input" type="date" id="week-date" />
                                <button class="refresh-btn" id="refresh-btn">Refresh</button>
                            </div>
                        </div>
                        <div class="layout">
                            <div class="timeline" id="timeline"></div>
                            <div id="news-content">
                                <p class="placeholder">Select a date from the timeline.</p>
                            </div>
                        </div>
                    </section>
                </div>
                <script>
                    const timelineEl = document.getElementById("timeline");
                    const contentEl = document.getElementById("news-content");
                    const refreshBtn = document.getElementById("refresh-btn");
                    const weekInput = document.getElementById("week-date");
                    const modelSelect = document.getElementById("news-model");
                    const providerSelect = document.getElementById("news-provider");
                    const companyName = "{safe_company}";
                    let selectedGroupKey = null;

                    function buildNewsCard(item) {{
                        const meta = [item.news_source, item.news_source_link].filter(Boolean).join(" · ");
                        const displayTime = formatPst(item.news_date_time);
                        const contentLines = [];
                        if (item.content.summary) {{
                            // Summary is already shown in the summary block.
                        }}
                        if (item.content.facts) {{
                            contentLines.push(`<div><strong>Facts:</strong> ${{item.content.facts}}</div>`);
                        }}
                        if (item.content.bias) {{
                            contentLines.push(`<div><strong>Bias:</strong> ${{item.content.bias}}</div>`);
                        }}
                        if (item.content.reasoning) {{
                            contentLines.push(`<div><strong>Reasoning:</strong> ${{item.content.reasoning}}</div>`);
                        }}
                        if (item.content.short_term_impact) {{
                            contentLines.push(`<div><strong>Short-term impact:</strong> ${{item.content.short_term_impact}}</div>`);
                        }}
                        if (item.content.long_term_impact) {{
                            contentLines.push(`<div><strong>Long-term impact:</strong> ${{item.content.long_term_impact}}</div>`);
                        }}
                        if (item.content.uncertainties) {{
                            contentLines.push(`<div><strong>Uncertainties:</strong> ${{item.content.uncertainties}}</div>`);
                        }}
                        if (item.content.priced_in) {{
                            contentLines.push(`<div><strong>Priced in:</strong> ${{item.content.priced_in}}</div>`);
                        }}
                        if (item.content.insider_signals) {{
                            contentLines.push(`<div><strong>Insider signals:</strong> ${{item.content.insider_signals}}</div>`);
                        }}
                        if (item.content.trends) {{
                            contentLines.push(`<div><strong>Trends:</strong> ${{item.content.trends}}</div>`);
                        }}
                        if (item.content.sentiment) {{
                            // Sentiment is already shown in the summary block.
                        }}
                        return `
                            <div class="news-card" data-news-id="${{item.id}}">
                                <h3>${{item.news_title}}</h3>
                                <div class="news-meta">
                                    <div>${{displayTime}}</div>
                                    <div>${{meta}}</div>
                                </div>
                                <div class="news-content">
                                    <div class="news-summary">
                                        <div><strong>Summary:</strong> ${{item.content.summary || "—"}}</div>
                                        <div><strong>Sentiment:</strong> ${{item.content.sentiment || "—"}}</div>
                                    </div>
                                    <div class="news-details">
                                        ${{contentLines.join("")}}
                                        <div class="news-actions">
                                            <button class="news-action-btn original" type="button">Original</button>
                                            <button class="news-action-btn delete" type="button">Remove</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }}

                    function renderNews(items, label) {{
                        if (!items.length) {{
                            contentEl.innerHTML = '<p class="placeholder">No news available for this date.</p>';
                            return;
                        }}
                        const header = `<h2>${{label}}</h2>`;
                        contentEl.innerHTML = header + items.map(buildNewsCard).join("");
                        contentEl.querySelectorAll(".news-card").forEach((card) => {{
                            card.addEventListener("click", (event) => {{
                                if (event.target.closest(".news-action-btn")) {{
                                    return;
                                }}
                                card.classList.toggle("expanded");
                            }});
                        }});
                        contentEl.querySelectorAll(".news-action-btn.original").forEach((button) => {{
                            button.addEventListener("click", (event) => {{
                                event.stopPropagation();
                                const card = event.target.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                const item = items.find((entry) => String(entry.id) === String(newsId));
                                if (item && item.original_content) {{
                                    alert(item.original_content);
                                }} else {{
                                    alert("No original content available.");
                                }}
                            }});
                        }});
                        contentEl.querySelectorAll(".news-action-btn.delete").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = event.target.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                if (!newsId) {{
                                    return;
                                }}
                                await fetch(`/api/company/${{encodeURIComponent(companyName)}}/news/${{newsId}}`, {{
                                    method: "DELETE",
                                }});
                                loadNews();
                            }});
                        }});
                    }}

                    function renderWeeklyReport(report, label, startDate, endDate, items) {{
                        if (!report) {{
                            contentEl.innerHTML = '<p class="placeholder">No weekly report available.</p>';
                            return;
                        }}
                        const sections = [
                            ["Summary", report.summary],
                            ["Facts", report.facts],
                            ["Viewpoint", report.viewpoint],
                            ["Bias", report.bias],
                            ["Reasoning", report.reasoning],
                            ["Short-term impact", report.short_term_impact],
                            ["Long-term impact", report.long_term_impact],
                            ["Uncertainties", report.uncertainties],
                            ["Priced in", report.priced_in],
                            ["Insider signals", report.insider_signals],
                            ["Trends", report.trends],
                            ["Sentiment", report.sentiment],
                        ];
                        const body = sections
                            .map(([title, items]) => {{
                                if (!items || !items.length) {{
                                    return `<div><strong>${{title}}:</strong> —</div>`;
                                }}
                                const rows = items
                                    .map((entry) => stripBullet(entry))
                                    .map((entry) => `<li>${{entry}}</li>`)
                                    .join("");
                                return `<div><strong>${{title}}:</strong><ul>${{rows}}</ul></div>`;
                            }})
                            .join("");
                        const sources = (items || [])
                            .map((entry) => `<li>${{formatPst(entry.news_date_time)}} — ${{entry.news_title}}</li>`)
                            .join("");
                        const sourcesBlock = sources
                            ? `<div><strong>Sources:</strong><ul>${{sources}}</ul></div>`
                            : "";
                        const header = `<h2>${{label}}</h2><div class="news-meta">${{startDate}} → ${{endDate}}</div>`;
                        contentEl.innerHTML = `
                            ${{header}}
                            <div class="news-card expanded">
                                <div class="news-content">
                                    ${{body}}
                                    ${{sourcesBlock}}
                                </div>
                            </div>
                        `;
                    }}

                    function renderGroup(group) {{
                        if (group.type === "weekly" && group.report) {{
                            renderWeeklyReport(
                                group.report,
                                group.label,
                                group.report_start,
                                group.report_end,
                                group.items
                            );
                            selectedGroupKey = group.key;
                            return;
                        }}
                        renderNews(group.items || [], group.label);
                        selectedGroupKey = group.key;
                    }}

                    function renderTimeline(groups) {{
                        timelineEl.innerHTML = "";
                        let selectedGroup = null;
                        groups.forEach((group) => {{
                            if (selectedGroupKey && group.key === selectedGroupKey) {{
                                selectedGroup = group;
                            }}
                        }});
                        groups.forEach((group, index) => {{
                            const item = document.createElement("div");
                            item.className = "timeline-item";
                            item.dataset.key = group.key;
                            item.innerHTML = `
                                <span class="timeline-marker">
                                    <span class="timeline-dot ${{group.type === "weekly" ? "weekly" : ""}}"></span>
                                </span>
                                <span class="timeline-label">${{group.label}}</span>
                            `;
                            item.title = group.label;
                            item.addEventListener("click", () => {{
                                renderGroup(group);
                            }});
                            timelineEl.appendChild(item);
                            if (index === 0 && !selectedGroup) {{
                                selectedGroup = group;
                            }}
                        }});
                        if (selectedGroup) {{
                            renderGroup(selectedGroup);
                        }}
                    }}

                    async function loadNews() {{
                        const response = await fetch(`/api/company/${{encodeURIComponent(companyName)}}/news`);
                        const payload = await response.json();
                        const groups = payload.groups || [];
                        if (!groups.length) {{
                            timelineEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            contentEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            return;
                        }}
                        renderTimeline(groups);
                    }}

                    async function refreshNews() {{
                        refreshBtn.disabled = true;
                        const start = Date.now();
                        refreshBtn.textContent = "Refreshing...";
                        try {{
                            let url = `/api/company/${{encodeURIComponent(companyName)}}/refresh`;
                            if (weekInput && weekInput.value) {{
                                url += `?week_date=${{encodeURIComponent(weekInput.value)}}`;
                            }}
                            if (providerSelect && providerSelect.value) {{
                                const joiner = url.includes("?") ? "&" : "?";
                                url += `${{joiner}}provider=${{encodeURIComponent(providerSelect.value)}}`;
                            }}
                            if (modelSelect && modelSelect.value) {{
                                const joiner = url.includes("?") ? "&" : "?";
                                url += `${{joiner}}model=${{encodeURIComponent(modelSelect.value)}}`;
                            }}
                            const response = await fetch(url, {{
                                method: "POST",
                            }});
                            const payload = await response.json();
                            const groups = payload.groups || [];
                            if (!groups.length) {{
                                timelineEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                                contentEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            }} else {{
                                renderTimeline(groups);
                            }}
                            const elapsedMs = Date.now() - start;
                            refreshBtn.textContent = `Refresh (${{(elapsedMs / 1000).toFixed(1)}}s)`;
                        }} finally {{
                            refreshBtn.disabled = false;
                            if (refreshBtn.textContent === "Refreshing...") {{
                                refreshBtn.textContent = "Refresh";
                            }}
                        }}
                    }}

                    refreshBtn.addEventListener("click", refreshNews);
                    loadNews();

                    function formatPst(isoString) {{
                        if (!isoString) {{
                            return "";
                        }}
                        const parsed = new Date(isoString);
                        if (Number.isNaN(parsed.getTime())) {{
                            return isoString;
                        }}
                        return parsed.toLocaleString("en-US", {{
                            timeZone: "America/Los_Angeles",
                            year: "numeric",
                            month: "short",
                            day: "2-digit",
                            hour: "numeric",
                            minute: "2-digit",
                            hour12: true,
                            timeZoneName: "short",
                        }});
                    }}

                    function stripBullet(entry) {{
                        if (typeof entry !== "string") {{
                            return entry;
                        }}
                        return entry.replace(/^[-•\u2022]\s*/, "");
                    }}
                </script>
            </body>
        </html>
    """
