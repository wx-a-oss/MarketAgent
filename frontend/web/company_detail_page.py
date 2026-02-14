"""Company detail page rendering."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from market_agent.news_sources import list_news_sources


def render_company_detail_page(company_name: str) -> str:
    safe_company = company_name.replace('"', "")
    display_company = (
        safe_company[:1].upper() + safe_company[1:] if safe_company else safe_company
    )
    source_options = "".join(
        f'<option value="{source}">{source}</option>'
        for source in list_news_sources()
        if source != "openai"
    )
    return f"""
        <html>
            <head>
                <title>MarketAgent – {display_company}</title>
                <link
                    rel="stylesheet"
                    href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css"
                />
                <style>
                    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap");
                    {BASE_PAGE_STYLES}
                    :root {{
                        --ink: #0f172a;
                        --accent: #0ea5e9;
                        --accent-2: #f97316;
                        --card: #ffffff;
                        --card-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
                    }}
                    body {{
                        background:
                            repeating-linear-gradient(
                                0deg,
                                rgba(15, 23, 42, 0.02),
                                rgba(15, 23, 42, 0.02) 1px,
                                transparent 1px,
                                transparent 6px
                            ),
                            repeating-linear-gradient(
                                90deg,
                                rgba(15, 23, 42, 0.015),
                                rgba(15, 23, 42, 0.015) 1px,
                                transparent 1px,
                                transparent 5px
                            ),
                            #f8f4ee;
                    }}
                    .container {{ max-width: 1040px; }}
                    .card {{
                        border: 2px solid rgba(15, 23, 42, 0.08);
                        border-radius: 1.6rem 1rem 2rem 1.2rem;
                        box-shadow: var(--card-shadow);
                        background: #fbf7f1;
                    }}
                    .layout {{ display: grid; grid-template-columns: 200px 1fr; gap: 1.5rem; }}
                    .header-row {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        margin-bottom: 1rem;
                    }}
                    .header-row h1 {{
                        font-size: 26px;
                        letter-spacing: -0.02em;
                        color: var(--ink);
                    }}
                    .header-actions {{
                        display: flex;
                        align-items: center;
                        gap: 0.5rem;
                    }}
                    .refresh-wrap {{
                        position: relative;
                        display: inline-flex;
                        align-items: center;
                    }}
                    .refresh-status {{
                        position: absolute;
                        top: calc(100% + 2px);
                        left: 12px;
                        font-size: 0.72rem;
                        color: #9ca3af;
                        white-space: pre-line;
                        line-height: 1.2;
                        max-width: 320px;
                    }}
                    .day-analyze-controls {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.4rem;
                    }}
                    .day-analyze-result {{
                        font-size: 0.75rem;
                        color: #94a3b8;
                        margin-left: 0.5rem;
                        white-space: nowrap;
                    }}
                    .day-group-header {{
                        display: flex;
                        align-items: center;
                        justify-content: flex-start;
                        flex-wrap: wrap;
                        gap: 0.8rem;
                        margin-bottom: 0.6rem;
                    }}
                    .day-group-header h2 {{
                        margin: 0;
                    }}
                    .day-group-right {{
                        display: inline-flex;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 0.6rem;
                        margin-left: 0;
                    }}
                    .day-total-count {{
                        font-size: 0.74rem;
                        color: #94a3b8;
                        white-space: nowrap;
                    }}
                    .day-note {{
                        font-size: 0.75rem;
                        color: #94a3b8;
                    }}
                    .day-analyze-input {{
                        width: 64px;
                        min-width: 64px;
                        height: 30px;
                        border: 1px solid #d1d5db;
                        border-radius: 0.5rem;
                        padding: 0.2rem 0.45rem;
                        font-size: 0.8rem;
                    }}
                    .day-analyze-btn {{
                        border: 1px solid #0f766e;
                        background: #0f766e;
                        color: #ffffff;
                        border-radius: 999px;
                        padding: 0.3rem 0.7rem;
                        font-size: 0.78rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .day-analyze-btn:hover {{
                        background: #0d9488;
                        border-color: #0d9488;
                    }}
                    .week-input {{
                        padding: 0.25rem 0.45rem;
                        border-radius: 0.5rem;
                        border: 1px solid #d1d5db;
                        font-size: 0.85rem;
                        height: 32px;
                        width: 180px;
                        min-width: 180px;
                    }}
                    #news-source {{
                        width: 112px;
                        min-width: 112px;
                    }}
                    #range-date {{
                        width: 230px;
                        min-width: 230px;
                    }}
                    .flatpickr-input {{
                        line-height: 1.2;
                    }}
                    .flatpickr-calendar {{
                        width: 320px;
                        font-size: 0.95rem;
                    }}
                    .flatpickr-day {{
                        height: 36px;
                        line-height: 36px;
                    }}
                    .flatpickr-weekday {{
                        font-weight: 600;
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
                        border: 1px solid rgba(15, 23, 42, 0.1);
                        border-radius: 1.1rem 0.75rem 1.3rem 0.9rem;
                        background: rgba(255, 255, 255, 0.9);
                        box-shadow: var(--card-shadow);
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
                        background: var(--accent);
                        position: relative;
                        z-index: 1;
                        border: 2px solid #f9fafb;
                    }}
                    .timeline-dot.weekly {{ background: var(--accent-2); }}
                    .timeline-label {{ font-size: 0.9rem; color: #374151; }}
                    .report {{
                        font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
                        font-size: 14px;
                        line-height: 1.7;
                        color: var(--ink);
                    }}
                    .report h1 {{
                        font-size: 26px;
                        font-weight: 600;
                        margin-bottom: 8px;
                    }}
                    .report h2 {{
                        font-size: 18px;
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
                        border: 2px solid rgba(15, 23, 42, 0.08);
                        border-radius: 1.4rem 0.8rem 1.6rem 1rem;
                        padding: 1rem;
                        background: #fdf6e8;
                        margin-bottom: 1rem;
                        cursor: pointer;
                        position: relative;
                        padding-top: 1.6rem;
                        box-shadow: var(--card-shadow);
                    }}
                    .news-card h3 {{ margin: 0 0 0.6rem; font-size: 18px; color: var(--ink); }}
                    .news-meta {{ color: #334155; font-size: 0.9rem; }}
                    .news-meta a {{
                        color: #6b7280;
                        text-decoration: underline;
                        word-break: break-all;
                    }}
                    .news-meta a:visited {{
                        color: #6b7280;
                    }}
                    .news-meta a:hover {{
                        color: #4b5563;
                    }}
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
                    .news-action-btn.analyze-inline {{
                        color: #0f766e;
                        border-color: #99f6e4;
                        background: #f0fdfa;
                        margin-top: 0.5rem;
                    }}
                    .news-action-btn.remove-inline {{
                        color: #b91c1c;
                        border-color: #fecaca;
                        background: #fef2f2;
                        margin-top: 0.5rem;
                    }}
                    .news-source-tag {{
                        position: absolute;
                        top: -0.45rem;
                        right: 0.65rem;
                        background: #f1f5f9;
                        color: #64748b;
                        border-radius: 999px;
                        padding: 0.1rem 0.4rem;
                        font-size: 0.65rem;
                        font-weight: 600;
                        text-transform: uppercase;
                        border: 1px solid #e2e8f0;
                        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
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
                                <select class="week-input" id="news-source">
                                    <option value="finnhub" selected>finnhub</option>
                                    <option value="openai">openai</option>
                                    {source_options}
                                </select>
                                <input class="week-input" type="text" id="range-date" />
                                <div class="refresh-wrap">
                                    <button class="refresh-btn" id="refresh-btn">Refresh</button>
                                    <span class="refresh-status" id="refresh-status"></span>
                                </div>
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
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script>
                    const timelineEl = document.getElementById("timeline");
                    const contentEl = document.getElementById("news-content");
                    const refreshBtn = document.getElementById("refresh-btn");
                    const refreshStatus = document.getElementById("refresh-status");
                    const rangeInput = document.getElementById("range-date");
                    const sourceSelect = document.getElementById("news-source");
                    const companyName = "{safe_company}";
                    let selectedGroupKey = null;

                    function buildNewsCard(item) {{
                        const sourceText = item.publisher || item.content.publisher;
                        const sourceLink = item.news_source_link
                            ? `<a href="${{item.news_source_link}}" target="_blank" rel="noopener noreferrer">${{item.news_source_link}}</a>`
                            : "";
                        const meta = [sourceText, sourceLink]
                            .filter(Boolean)
                            .join(" · ");
                        const displayTime = formatPst(item.news_date_time);
                        const contentLines = [];
                        if (item.content.summary) {{
                            // Summary is already shown in the summary block.
                        }}
                        if (item.content.facts) {{
                            contentLines.push(`<div><strong>Facts:</strong> ${{item.content.facts}}</div>`);
                        }}
                        if (item.content.reasoning) {{
                            contentLines.push(`<div><strong>Reasoning:</strong> ${{item.content.reasoning}}</div>`);
                        }}
                        if (item.content.uncertainties) {{
                            contentLines.push(`<div><strong>Uncertainties:</strong> ${{item.content.uncertainties}}</div>`);
                        }}
                        if (item.content.short_term_impact) {{
                            contentLines.push(`<div><strong>Short-term impact:</strong> ${{item.content.short_term_impact}}</div>`);
                        }}
                        if (item.content.long_term_impact) {{
                            contentLines.push(`<div><strong>Long-term impact:</strong> ${{item.content.long_term_impact}}</div>`);
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
                            <div class="news-card ${{item.is_analyzed ? "analyzed" : "raw"}}" data-news-id="${{item.id}}">
                                ${{item.news_source ? `<span class="news-source-tag">${{item.news_source}}</span>` : ""}}
                                <h3>${{item.news_title}}</h3>
                                <div class="news-meta">
                                    <div>${{displayTime}}</div>
                                    <div>${{meta}}</div>
                                </div>
                                <div class="news-content">
                                    <div class="news-summary">
                                        <div><strong>Summary:</strong> ${{item.content.summary || "—"}}</div>
                                        <div><strong>Sentiment:</strong> ${{item.content.sentiment || "—"}}</div>
                                        ${{!item.is_analyzed ? '<button class="news-action-btn analyze-inline" type="button">Analyze</button>' : ''}}
                                        ${{!item.is_analyzed ? '<button class="news-action-btn remove-inline" type="button">Remove</button>' : ''}}
                                    </div>
                                    ${{item.is_analyzed ? `<div class="news-details">
                                        ${{contentLines.join("")}}
                                        <div class="news-actions">
                                            <button class="news-action-btn original" type="button">Original</button>
                                            <button class="news-action-btn delete" type="button">Remove</button>
                                        </div>
                                    </div>` : ""}}
                                </div>
                            </div>
                        `;
                    }}

                    function renderNews(items, label, group) {{
                        if (!items.length) {{
                            contentEl.innerHTML = '<p class="placeholder">No news available for this date.</p>';
                            return;
                        }}
                        const isDaily = group && group.type === "daily";
                        const rawCount = items.filter((item) => !item.is_analyzed).length;
                        const filterableCount = items.length;
                        const totalCountLabel = `${{filterableCount}} item${{filterableCount === 1 ? "" : "s"}}`;
                        const dayDate = isDaily
                            ? ((group.key || "").startsWith("day-") ? group.key.slice(4) : (group.label || ""))
                            : "";
                        const header = isDaily
                            ? `
                                <div class="day-group-header">
                                    <h2>${{label}}</h2>
                                    <div class="day-group-right">
                                        ${{filterableCount > 0
                                        ? `<div class="day-analyze-controls">
                                                <button class="day-analyze-btn" id="day-analyze-btn" type="button">Analyze</button>
                                                <input class="day-analyze-input" id="day-analyze-limit" type="number" min="1" max="${{filterableCount}}" value="${{Math.min(5, filterableCount)}}" />
                                                <span class="day-analyze-result" id="day-analyze-result"></span>
                                           </div>`
                                        : `<span class="day-note">No items for day actions</span>`}}
                                        <span class="day-total-count">${{totalCountLabel}}</span>
                                    </div>
                                </div>
                            `
                            : `<h2>${{label}}</h2>`;
                        contentEl.innerHTML = header + items.map(buildNewsCard).join("");
                        contentEl.querySelectorAll(".news-card").forEach((card) => {{
                            card.addEventListener("click", (event) => {{
                                if (card.classList.contains("raw")) {{
                                    return;
                                }}
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
                        contentEl.querySelectorAll(".news-action-btn.analyze-inline").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const actionButton = event.target;
                                const card = actionButton.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                if (!newsId) {{
                                    return;
                                }}
                                actionButton.disabled = true;
                                actionButton.textContent = "Analyzing...";
                                try {{
                                    await fetch(`/api/company/${{encodeURIComponent(companyName)}}/news/${{newsId}}/summarize`, {{
                                        method: "POST",
                                    }});
                                    loadNews();
                                }} finally {{
                                    actionButton.disabled = false;
                                    actionButton.textContent = "Analyze";
                                }}
                            }});
                        }});
                        contentEl.querySelectorAll(".news-action-btn.remove-inline").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const actionButton = event.target;
                                const card = actionButton.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                if (!newsId) {{
                                    return;
                                }}
                                actionButton.disabled = true;
                                actionButton.textContent = "Removing...";
                                try {{
                                    await fetch(`/api/company/${{encodeURIComponent(companyName)}}/news/${{newsId}}`, {{
                                        method: "DELETE",
                                    }});
                                    loadNews();
                                }} finally {{
                                    actionButton.disabled = false;
                                    actionButton.textContent = "Remove";
                                }}
                            }});
                        }});
                        const dayAnalyzeBtn = document.getElementById("day-analyze-btn");
                        const dayAnalyzeLimit = document.getElementById("day-analyze-limit");
                        const dayAnalyzeResult = document.getElementById("day-analyze-result");
                        if (dayAnalyzeBtn && dayAnalyzeLimit && dayDate) {{
                            dayAnalyzeBtn.addEventListener("click", async () => {{
                                if (rawCount <= 0) {{
                                    if (dayAnalyzeResult) {{
                                        dayAnalyzeResult.textContent = "No raw items to analyze";
                                    }}
                                    return;
                                }}
                                const value = Number(dayAnalyzeLimit.value || 5);
                                const limit = Number.isFinite(value) ? Math.max(1, Math.min(rawCount || 100, Math.trunc(value))) : 5;
                                const dayAnalyzeStart = Date.now();
                                dayAnalyzeBtn.disabled = true;
                                dayAnalyzeBtn.textContent = "Analyzing...";
                                if (dayAnalyzeResult) {{
                                    dayAnalyzeResult.textContent = "";
                                }}
                                try {{
                                    const url =
                                        `/api/company/${{encodeURIComponent(companyName)}}/news/summarize/day` +
                                        `?date=${{encodeURIComponent(dayDate)}}&limit=${{encodeURIComponent(String(limit))}}`;
                                    const response = await fetch(url, {{ method: "POST" }});
                                    const payload = await response.json();
                                    if (!response.ok || payload.error) {{
                                        if (dayAnalyzeResult) {{
                                            dayAnalyzeResult.textContent = payload.error || "Analyze day failed";
                                        }}
                                        return;
                                    }}
                                    const groups = payload.groups || [];
                                    if (groups.length) {{
                                        renderTimeline(groups);
                                    }}
                                    if (dayAnalyzeResult) {{
                                        const processed = Number(payload.processed_count || 0);
                                        const analyzed = Number(payload.analyzed_count || 0);
                                        const elapsedRaw = Number(payload.elapsed_sec);
                                        const elapsedSec = Number.isFinite(elapsedRaw)
                                            ? elapsedRaw.toFixed(1)
                                            : ((Date.now() - dayAnalyzeStart) / 1000).toFixed(1);
                                        dayAnalyzeResult.textContent = `${{analyzed}} analyzed (from ${{processed}}) in ${{elapsedSec}}s`;
                                    }}
                                }} finally {{
                                    dayAnalyzeBtn.disabled = false;
                                    dayAnalyzeBtn.textContent = "Analyze";
                                }}
                            }});
                        }}
                    }}

                    function renderWeeklyReport(report, label, startDate, endDate, items) {{
                        if (!report) {{
                            contentEl.innerHTML = `
                                <h2>${{label}}</h2>
                                <div class="news-meta">${{startDate}} → ${{endDate}}</div>
                                <div class="news-card expanded">
                                    <div class="news-content">
                                        <p class="placeholder">No weekly report available.</p>
                                        <button class="refresh-btn" id="generate-report-btn" type="button">
                                            Generate report
                                        </button>
                                    </div>
                                </div>
                            `;
                            const button = document.getElementById("generate-report-btn");
                            if (button) {{
                                button.addEventListener("click", async () => {{
                                    button.disabled = true;
                                    button.textContent = "Generating...";
                                    try {{
                                        const url = `/api/company/${{encodeURIComponent(companyName)}}/report?week_date=${{encodeURIComponent(startDate)}}`;
                                        const response = await fetch(url, {{ method: "POST" }});
                                        const payload = await response.json();
                                        const groups = payload.groups || [];
                                        if (groups.length) {{
                                            renderTimeline(groups);
                                        }}
                                    }} finally {{
                                        button.disabled = false;
                                        button.textContent = "Generate report";
                                    }}
                                }});
                            }}
                            return;
                        }}
                        const sections = [
                            ["Summary", report.summary],
                            ["Sentiment", report.sentiment],
                            ["Facts", report.facts],
                            ["Viewpoint", report.viewpoint],
                            ["Reasoning", report.reasoning],
                            ["Uncertainties", report.uncertainties],
                            ["Short-term impact", report.short_term_impact],
                            ["Long-term impact", report.long_term_impact],
                            ["Priced in", report.priced_in],
                            ["Insider signals", report.insider_signals],
                            ["Trends", report.trends],
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
                        const header = `
                            <div class="header-row">
                                <h2>${{label}}</h2>
                                <button class="refresh-btn" id="rebuild-report-btn" type="button">
                                    Rebuild report
                                </button>
                            </div>
                            <div class="news-meta">${{startDate}} → ${{endDate}}</div>
                        `;
                        contentEl.innerHTML = `
                            ${{header}}
                            <div class="news-card expanded">
                                <div class="news-content">
                                    ${{body}}
                                    ${{sourcesBlock}}
                                </div>
                            </div>
                        `;
                        const rebuildBtn = document.getElementById("rebuild-report-btn");
                        if (rebuildBtn) {{
                            rebuildBtn.addEventListener("click", async () => {{
                                rebuildBtn.disabled = true;
                                rebuildBtn.textContent = "Rebuilding...";
                                try {{
                                    const url = `/api/company/${{encodeURIComponent(companyName)}}/report?week_date=${{encodeURIComponent(startDate)}}`;
                                    const response = await fetch(url, {{ method: "POST" }});
                                    const payload = await response.json();
                                    const groups = payload.groups || [];
                                    if (groups.length) {{
                                        renderTimeline(groups);
                                    }}
                                }} finally {{
                                    rebuildBtn.disabled = false;
                                    rebuildBtn.textContent = "Rebuild report";
                                }}
                            }});
                        }}
                    }}

                    function renderGroup(group) {{
                        if (group.type === "weekly") {{
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
                        renderNews(group.items || [], group.label, group);
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
                            if (!rangeInput.value || !rangeInput.value.includes(" to ")) {{
                                alert("Please select a start and end date.");
                                return;
                            }}
                            const [startDate, endDate] = rangeInput.value.split(" to ");
                            if (!startDate || !endDate) {{
                                alert("Please select a start and end date.");
                                return;
                            }}
                            url += `?start_date=${{encodeURIComponent(startDate)}}&end_date=${{encodeURIComponent(endDate)}}`;
                            if (sourceSelect && sourceSelect.value) {{
                                const joiner = url.includes("?") ? "&" : "?";
                                url += `${{joiner}}source=${{encodeURIComponent(sourceSelect.value)}}`;
                            }}
                            const response = await fetch(url, {{
                                method: "POST",
                            }});
                            const payload = await response.json();
                            const fetchedTotal = Number(payload.fetched_total || 0);
                            const filteredOut = Number(payload.filtered_out || 0);
                            const groups = payload.groups || [];
                            if (!groups.length) {{
                                timelineEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                                contentEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            }} else {{
                                renderTimeline(groups);
                            }}
                            if (refreshStatus) {{
                                const elapsedRaw = Number(payload.elapsed_sec);
                                const elapsedSec = Number.isFinite(elapsedRaw)
                                    ? elapsedRaw.toFixed(1)
                                    : ((Date.now() - start) / 1000).toFixed(1);
                                const selectedSource = sourceSelect && sourceSelect.value
                                    ? String(sourceSelect.value).toLowerCase()
                                    : "openai";
                                if (selectedSource === "finnhub") {{
                                    refreshStatus.textContent =
                                        `fetched: ${{fetchedTotal}}\nfiltered: ${{filteredOut}}`;
                                }} else {{
                                    refreshStatus.textContent = `fetched: ${{fetchedTotal}}`;
                                }}
                                refreshBtn.textContent = `Refreshed (${{elapsedSec}}s)`;
                            }}
                        }} finally {{
                            refreshBtn.disabled = false;
                            if (refreshBtn.textContent === "Refreshing...") {{
                                refreshBtn.textContent = "Refresh";
                            }}
                        }}
                    }}


                    refreshBtn.addEventListener("click", refreshNews);
                    if (window.flatpickr) {{
                        const today = new Date();
                        const weekStart = new Date(today);
                        weekStart.setDate(today.getDate() - today.getDay() + 1);
                        window.flatpickr(rangeInput, {{
                            dateFormat: "Y-m-d",
                            locale: {{ firstDayOfWeek: 1 }},
                            mode: "range",
                            defaultDate: [weekStart, today],
                        }});
                    }}
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
