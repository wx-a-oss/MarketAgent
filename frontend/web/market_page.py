"""Market workspace page rendering."""

from __future__ import annotations

import json
from typing import Dict, List

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from market_agent.config.models import DEFAULT_MARKET_OPENAI_MODEL


def render_market_page(
    news_models: Dict[str, List[str]],
    *,
    default_date: str,
) -> str:
    model_choices: List[Dict[str, str]] = []
    for provider, models in news_models.items():
        for model in models:
            model_choices.append({"provider": provider, "model": model})
    model_choices_json = json.dumps(model_choices, ensure_ascii=False)
    default_openai_model_json = json.dumps(DEFAULT_MARKET_OPENAI_MODEL, ensure_ascii=False)
    return f"""
        <html>
            <head>
                <title>MarketAgent – Market</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" />
                <style>
                    {BASE_PAGE_STYLES}
                    .report {{
                        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
                        font-size: 14px;
                        line-height: 1.7;
                        color: #0f172a;
                    }}
                    .subtabs {{
                        display: flex;
                        gap: 0.5rem;
                        margin-bottom: 0.85rem;
                        flex-wrap: wrap;
                    }}
                    .subtab-btn {{
                        border: 1px solid #cbd5e1;
                        background: #ffffff;
                        color: #334155;
                        border-radius: 999px;
                        padding: 0.38rem 0.8rem;
                        font-size: 0.85rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .subtab-btn.active {{
                        background: #0f172a;
                        color: #ffffff;
                        border-color: #0f172a;
                    }}
                    .market-subview {{ display: none; }}
                    .market-subview.active {{ display: block; }}
                    .view-toolbar {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        flex-wrap: wrap;
                        margin-bottom: 0.55rem;
                    }}
                    .view-toolbar h2 {{ margin: 0; font-size: 1.2rem; }}
                    .view-toolbar-right {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                    }}
                    .view-status-row, .summary-status, .overview-refresh-status {{
                        color: #6b7280;
                        font-size: 0.83rem;
                        margin-bottom: 0.85rem;
                    }}
                    .date-input {{
                        padding: 0.45rem 0.55rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.45rem;
                        background: #ffffff;
                        font-size: 0.9rem;
                        width: 140px;
                    }}
                    .refresh-btn {{
                        background: #16a34a;
                    }}
                    .refresh-btn:hover {{
                        background: #15803d;
                    }}
                    .market-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 0.8rem;
                    }}
                    .market-overview-section {{
                        margin-top: 1rem;
                    }}
                    .market-overview-section-title {{
                        margin: 0 0 0.65rem;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #111827;
                    }}
                    .market-item {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.65rem;
                        padding: 0.75rem;
                        background: #fafafa;
                    }}
                    .market-item h3 {{
                        margin: 0 0 0.35rem;
                        font-size: 0.95rem;
                        color: #111827;
                    }}
                    .market-item .symbol {{
                        color: #6b7280;
                        font-size: 0.78rem;
                        margin-bottom: 0.3rem;
                    }}
                    .market-item .country {{
                        color: #94a3b8;
                        font-size: 0.72rem;
                        margin-bottom: 0.3rem;
                        text-transform: uppercase;
                        letter-spacing: 0.03em;
                    }}
                    .market-item .price {{
                        font-size: 1.1rem;
                        font-weight: 700;
                        color: #111827;
                    }}
                    .market-item .change {{
                        font-size: 0.85rem;
                        margin-top: 0.2rem;
                    }}
                    .market-item .headline {{
                        color: #334155;
                        font-size: 0.78rem;
                        margin-top: 0.36rem;
                        line-height: 1.45;
                    }}
                    .market-item .headline a {{
                        color: #475569;
                        text-decoration: underline;
                        font-weight: 500;
                    }}
                    .market-item .headline-time {{
                        color: #94a3b8;
                        font-size: 0.72rem;
                        margin-top: 0.18rem;
                    }}
                    .change.up {{ color: #16a34a; }}
                    .change.down {{ color: #dc2626; }}
                    .change.flat {{ color: #6b7280; }}
                    .overview-grid {{
                        display: grid;
                        gap: 0.9rem;
                    }}
                    .overview-hint {{
                        margin-top: 0.85rem;
                        color: #64748b;
                        font-size: 0.82rem;
                    }}
                    .prices-layout {{
                        display: grid;
                        gap: 1rem;
                    }}
                    .prices-analysis-card {{
                        border: 1px solid #dbeafe;
                        border-radius: 0.9rem;
                        background: #f8fbff;
                        padding: 1rem;
                    }}
                    .prices-analysis-body {{
                        color: #0f172a;
                        line-height: 1.7;
                    }}
                    .prices-analysis-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 0.8rem;
                        margin-top: 0.9rem;
                    }}
                    .prices-note-card {{
                        border: 1px solid #e2e8f0;
                        border-radius: 0.75rem;
                        background: #ffffff;
                        padding: 0.75rem;
                    }}
                    .prices-note-card h4 {{
                        margin: 0 0 0.3rem;
                        font-size: 0.9rem;
                    }}
                    .prices-list {{
                        margin: 0.6rem 0 0;
                        padding-left: 1rem;
                    }}
                    .summary-card {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.7rem;
                        padding: 0.8rem;
                        background: #f8fafc;
                        margin-bottom: 0.7rem;
                    }}
                    .summary-card .summary-output {{
                        margin-top: 0.55rem;
                        color: #111827;
                        line-height: 1.65;
                        font-size: 0.95rem;
                    }}
                    .summary-card .summary-output p {{ margin: 0.38rem 0; }}
                    .summary-card .summary-output ul,
                    .summary-card .summary-output ol {{
                        margin: 0.42rem 0 0.42rem 1rem;
                        padding-left: 0.7rem;
                    }}
                    .news-list {{
                        display: grid;
                        gap: 0.7rem;
                    }}
                    .news-item {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.6rem;
                        padding: 0.75rem;
                        background: #fff;
                        position: relative;
                        cursor: pointer;
                    }}
                    .news-item.expanded {{
                        border-color: #cbd5e1;
                        background: #fcfdff;
                    }}
                    .news-tag {{
                        position: absolute;
                        top: -0.42rem;
                        right: 0.6rem;
                        background: #f1f5f9;
                        color: #64748b;
                        border-radius: 999px;
                        padding: 0.08rem 0.45rem;
                        font-size: 0.64rem;
                        font-weight: 700;
                        text-transform: uppercase;
                        border: 1px solid #e2e8f0;
                    }}
                    .news-item a {{
                        color: #1f2937;
                        text-decoration: none;
                        font-weight: 600;
                    }}
                    .news-item a:hover {{
                        text-decoration: underline;
                    }}
                    .news-meta {{
                        color: #6b7280;
                        font-size: 0.8rem;
                        margin-top: 0.3rem;
                    }}
                    .news-actions {{
                        display: flex;
                        align-items: center;
                        gap: 0.45rem;
                        margin-top: 0.55rem;
                        flex-wrap: wrap;
                    }}
                    .news-model-picker {{
                        padding: 0.3rem 0.45rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.45rem;
                        background: #ffffff;
                        font-size: 0.78rem;
                        max-width: 230px;
                    }}
                    .news-analyze-btn {{
                        border: 1px solid #0f766e;
                        background: #0f766e;
                        color: #ffffff;
                        border-radius: 999px;
                        padding: 0.28rem 0.62rem;
                        font-size: 0.78rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .news-analysis {{
                        display: none;
                        margin-top: 0.65rem;
                        padding: 0.65rem;
                        border: 1px solid #e2e8f0;
                        border-radius: 0.55rem;
                        background: #f8fafc;
                        white-space: pre-wrap;
                        overflow-wrap: anywhere;
                        line-height: 1.6;
                        font-size: 0.9rem;
                    }}
                    .news-item.expanded .news-analysis {{ display: block; }}
                    .news-analysis-meta {{
                        color: #64748b;
                        font-size: 0.75rem;
                        margin-bottom: 0.35rem;
                    }}
                    .attach-story-inline {{
                        display: none;
                        align-items: center;
                        gap: 0.35rem;
                    }}
                    .attach-story-inline.active {{
                        display: inline-flex;
                    }}
                    .story-warmup {{
                        color: #64748b;
                        font-size: 0.84rem;
                        margin-bottom: 0.7rem;
                    }}
                    .stories-wrap {{
                        display: grid;
                        grid-template-columns: 280px minmax(0, 920px);
                        gap: 0.8rem;
                        align-items: start;
                    }}
                    .stories-side {{
                        border: 1px solid #dbeafe;
                        border-radius: 0.9rem;
                        background: #f8fbff;
                        padding: 0.7rem;
                        max-height: 70vh;
                        overflow-y: auto;
                    }}
                    .story-list {{ display: grid; gap: 0.5rem; }}
                    .story-item {{
                        border: 1px solid #dbeafe;
                        background: #ffffff;
                        border-radius: 0.7rem;
                        padding: 0.55rem 0.6rem;
                        cursor: pointer;
                    }}
                    .story-item.active {{
                        border-color: #60a5fa;
                        box-shadow: 0 0 0 1px #93c5fd inset;
                    }}
                    .story-item-title {{
                        font-size: 0.9rem;
                        font-weight: 700;
                        color: #0f172a;
                        margin-bottom: 0.25rem;
                    }}
                    .story-item-meta {{
                        font-size: 0.76rem;
                        color: #64748b;
                    }}
                    .story-group-heading {{
                        font-size: 0.75rem;
                        font-weight: 700;
                        letter-spacing: 0.06em;
                        text-transform: uppercase;
                        color: #64748b;
                        margin: 0.25rem 0 0.15rem;
                        padding: 0 0.15rem;
                    }}
                    .stories-main {{
                        border: 1px solid #dbeafe;
                        border-radius: 0.9rem;
                        background: #f8fbff;
                        padding: 0.8rem;
                        width: 100%;
                        max-width: 920px;
                    }}
                    .story-detail-section {{ margin-top: 0.65rem; }}
                    .story-detail-section h3 {{
                        margin: 0 0 0.28rem;
                        font-size: 0.9rem;
                    }}
                    .story-detail-box {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.65rem;
                        background: #fff;
                        padding: 0.55rem 0.65rem;
                        line-height: 1.6;
                        font-size: 0.9rem;
                        overflow-wrap: anywhere;
                    }}
                    .macro-calendar-wrap {{
                        display: grid;
                        gap: 1rem;
                    }}
                    .macro-month-grid {{
                        display: grid;
                        grid-template-columns: repeat(7, minmax(0, 1fr));
                        gap: 0.4rem;
                    }}
                    .macro-month-title {{
                        margin: 0 0 0.45rem;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #0f172a;
                    }}
                    .macro-weekday {{
                        font-size: 0.72rem;
                        color: #64748b;
                        text-transform: uppercase;
                        letter-spacing: 0.04em;
                        padding: 0.12rem 0.2rem;
                    }}
                    .macro-day-cell {{
                        min-height: 102px;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.65rem;
                        padding: 0.45rem;
                        background: #fff;
                        display: flex;
                        flex-direction: column;
                        gap: 0.28rem;
                        cursor: pointer;
                    }}
                    .macro-day-cell.empty {{
                        background: transparent;
                        border-style: dashed;
                        border-color: #f1f5f9;
                        cursor: default;
                    }}
                    .macro-day-cell.has-events {{
                        border-color: #cbd5e1;
                        background: #f8fbff;
                    }}
                    .macro-day-cell.selected {{
                        border-color: #0f766e;
                        box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.14);
                    }}
                    .macro-day-num {{
                        font-size: 0.82rem;
                        font-weight: 700;
                        color: #0f172a;
                    }}
                    .macro-day-events {{
                        display: grid;
                        gap: 0.18rem;
                    }}
                    .macro-pill {{
                        font-size: 0.68rem;
                        line-height: 1.2;
                        padding: 0.14rem 0.32rem;
                        border-radius: 999px;
                        background: #e2e8f0;
                        color: #334155;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }}
                    .macro-overflow {{
                        font-size: 0.68rem;
                        color: #64748b;
                    }}
                    .macro-detail-card {{
                        border: 1px solid #dbeafe;
                        background: #f8fbff;
                        border-radius: 0.8rem;
                        padding: 0.8rem 0.9rem;
                    }}
                    .macro-detail-date {{
                        font-size: 0.88rem;
                        color: #475569;
                        margin-bottom: 0.55rem;
                    }}
                    .macro-detail-item {{
                        border-top: 1px solid #e2e8f0;
                        padding: 0.55rem 0 0;
                        margin-top: 0.55rem;
                    }}
                    .macro-detail-item:first-child {{
                        border-top: none;
                        margin-top: 0;
                        padding-top: 0;
                    }}
                    .macro-detail-item h3 {{
                        margin: 0 0 0.22rem;
                        font-size: 0.95rem;
                        color: #0f172a;
                    }}
                    .macro-detail-meta {{
                        color: #64748b;
                        font-size: 0.78rem;
                        margin-bottom: 0.2rem;
                    }}
                    .macro-detail-values {{
                        display: grid;
                        gap: 0.14rem;
                        font-size: 0.82rem;
                        color: #334155;
                    }}
                    .macro-detail-link a {{
                        color: #475569;
                        text-decoration: underline;
                        font-size: 0.78rem;
                    }}
                    .placeholder {{
                        color: #64748b;
                    }}
                    .flatpickr-day.has-report {{
                        position: relative;
                        font-weight: 700;
                        color: #0f172a;
                    }}
                    .flatpickr-day.has-report::after {{
                        content: "";
                        position: absolute;
                        bottom: 5px;
                        left: 50%;
                        width: 6px;
                        height: 6px;
                        margin-left: -3px;
                        border-radius: 999px;
                        background: #16a34a;
                    }}
                    @media (max-width: 1200px) {{
                        .stories-wrap {{
                            grid-template-columns: 260px minmax(0, 1fr);
                        }}
                        .stories-main {{ max-width: none; }}
                    }}
                    @media (max-width: 900px) {{
                        .stories-wrap {{
                            grid-template-columns: 1fr;
                        }}
                        .stories-side {{
                            max-height: none;
                        }}
                        .macro-month-grid {{
                            grid-template-columns: repeat(1, minmax(0, 1fr));
                        }}
                        .macro-weekday {{
                            display: none;
                        }}
                    }}
                </style>
            </head>
            <body class="report">
                {render_nav("market")}
                <div class="container">
                    <div class="subtabs" id="market-view-tabs">
                        <button class="subtab-btn active" type="button" data-market-view="overview">Overview</button>
                        <button class="subtab-btn" type="button" data-market-view="daily-news">Daily News</button>
                        <button class="subtab-btn" type="button" data-market-view="calendar">Macro</button>
                        <button class="subtab-btn" type="button" data-market-view="stories">Stories</button>
                    </div>

                    <div id="market-overview-view" class="market-subview active">
                        <section class="card">
                            <div class="view-toolbar">
                                <h2>Market Overview</h2>
                                <div class="view-toolbar-right">
                                    <input id="market-date-overview" class="date-input" type="text" />
                                    <button id="refresh-market-overview" class="refresh-btn" type="button">Refresh Overview</button>
                                </div>
                            </div>
                            <div id="market-overview-status" class="overview-refresh-status"></div>
                            <div class="overview-grid" id="market-overview-grid"></div>
                            <div class="overview-hint">Use Macro for macro events and Daily News for the news flow behind the move.</div>
                            <div class="prices-analysis-card" style="margin-top: 1rem;">
                                <div class="view-toolbar">
                                    <h2>Market Analysis</h2>
                                    <div class="view-toolbar-right">
                                        <select id="market-prices-analysis-model" class="news-model-picker"></select>
                                        <button id="refresh-market-prices-analysis" class="refresh-btn" type="button">Generate Analysis</button>
                                    </div>
                                </div>
                                <div id="market-prices-analysis-status" class="summary-status"></div>
                                <div id="market-prices-analysis-output" class="prices-analysis-body"></div>
                                <div id="market-prices-analysis-notes" class="prices-analysis-grid"></div>
                            </div>
                        </section>
                    </div>

                    <div id="market-daily-news-view" class="market-subview">
                        <section class="card">
                            <div class="view-toolbar">
                                <h2>Daily Market News</h2>
                                <div class="view-toolbar-right">
                                    <input id="market-date-daily-news" class="date-input" type="text" />
                                    <button id="refresh-market-daily-news" class="refresh-btn" type="button">Refresh Daily News</button>
                                </div>
                            </div>
                            <div id="summary-status" class="view-status-row"></div>
                            <div id="market-daily-clusters"></div>
                            <div id="news-summaries"></div>
                            <div id="market-news" class="news-list"></div>
                        </section>
                    </div>

                    <section id="market-stories-view" class="card market-subview">
                        <div class="view-toolbar">
                            <h2>Market Stories</h2>
                            <div class="view-toolbar-right">
                                <button id="refresh-market-stories" class="refresh-btn" type="button">Refresh Stories</button>
                            </div>
                        </div>
                        <div id="market-stories-status" class="view-status-row"></div>
                        <div id="market-story-warmup" class="story-warmup"></div>
                        <div class="stories-wrap">
                            <div class="stories-side"><div class="story-list" id="market-story-list"></div></div>
                            <div class="stories-main" id="market-story-detail"><p class="placeholder">Select a story to see details.</p></div>
                        </div>
                    </section>

                    <div id="market-calendar-view" class="market-subview">
                        <section class="card">
                            <div class="view-toolbar">
                                <h2>Market Macro</h2>
                                <div class="view-toolbar-right">
                                    <button id="refresh-market-macro" class="refresh-btn" type="button">Refresh 3 Months</button>
                                </div>
                            </div>
                            <div id="market-macro-status" class="view-status-row"></div>
                            <div id="market-macro-events" class="macro-calendar-wrap"></div>
                        </section>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    const singleNewsModels = {model_choices_json};
                    const defaultModel = {default_openai_model_json};
                    const summaryLanguage = document.getElementById("global-language-select");
                    const marketViewTabs = document.getElementById("market-view-tabs");
                    const overviewDateInput = document.getElementById("market-date-overview");
                    const dailyNewsDateInput = document.getElementById("market-date-daily-news");
                    const dateInputs = [overviewDateInput, dailyNewsDateInput].filter(Boolean);
                    const overviewStatusEl = document.getElementById("market-overview-status");
                    const overviewGridEl = document.getElementById("market-overview-grid");
                    const pricesAnalysisStatusEl = document.getElementById("market-prices-analysis-status");
                    const pricesAnalysisOutputEl = document.getElementById("market-prices-analysis-output");
                    const pricesAnalysisNotesEl = document.getElementById("market-prices-analysis-notes");
                    const pricesAnalysisModelPicker = document.getElementById("market-prices-analysis-model");
                    const refreshOverviewBtn = document.getElementById("refresh-market-overview");
                    const refreshPricesAnalysisBtn = document.getElementById("refresh-market-prices-analysis");
                    const refreshDailyNewsBtn = document.getElementById("refresh-market-daily-news");
                    const summaryStatus = document.getElementById("summary-status");
                    const summariesEl = document.getElementById("news-summaries");
                    const marketDailyClustersEl = document.getElementById("market-daily-clusters");
                    const marketStoriesStatus = document.getElementById("market-stories-status");
                    const marketStoryWarmup = document.getElementById("market-story-warmup");
                    const marketStoryListEl = document.getElementById("market-story-list");
                    const marketStoryDetailEl = document.getElementById("market-story-detail");
                    const marketMacroEventsEl = document.getElementById("market-macro-events");
                    const marketMacroStatus = document.getElementById("market-macro-status");
                    const refreshMacroBtn = document.getElementById("refresh-market-macro");
                    let latestNews = [];
                    let latestStoryOptions = [];
                    let latestMarketSections = [];
                    let latestMarketPayload = null;
                    let activeMarketStoryKey = "";
                    let currentMarketView = "overview";
                    let selectedMacroDate = "";
                    let dailyNewsAutoInitializedKey = "";
                    let marketStoriesAutoInitializedKey = "";
                    let dailyNewsJobStop = null;
                    let marketStoriesJobStop = null;
                    let macroJobStop = null;
                    let reportDateSet = new Set();
                    const datePickers = [];

                    function readUrlState() {{
                        const params = new URLSearchParams(window.location.search || "");
                        const lang = String(params.get("lang") || "").trim();
                        const date = String(params.get("date") || "").trim();
                        const rawView = String(params.get("view") || "").trim();
                        const allowed = new Set(["overview", "daily-news", "stories", "calendar"]);
                        return {{
                            lang: lang === "en" ? "en" : "zh-CN",
                            date,
                            view: allowed.has(rawView) ? rawView : "overview",
                        }};
                    }}

                    function updateUrlState() {{
                        const url = new URL(window.location.href);
                        const params = url.searchParams;
                        params.set("date", selectedDate);
                        params.set("lang", getOutputLanguage());
                        params.set("view", currentMarketView);
                        window.history.replaceState({{}}, "", `${{url.pathname}}?${{params.toString()}}`);
                    }}

                    function buildJobKey(...parts) {{
                        return parts.map((item) => String(item || "").trim().toLowerCase()).join("|");
                    }}

                    function formatJobText(job) {{
                        if (!job) return "";
                        const counts = job.final_counts || {{}};
                        const bits = [String(job.status || "")];
                        if (job.current_stage) bits.push(String(job.current_stage));
                        if (job.elapsed_sec) bits.push(`${{Number(job.elapsed_sec || 0).toFixed(1)}}s`);
                        if (job.input_char_count) bits.push(`prompt=${{job.input_char_count}} chars`);
                        if (counts.fetched_total) bits.push(`fetched=${{counts.fetched_total}}`);
                        if (counts.cluster_count) bits.push(`clusters=${{counts.cluster_count}}`);
                        if (counts.report_count) bits.push(`reports=${{counts.report_count}}`);
                        if (counts.updated) bits.push(`updated=${{counts.updated}}`);
                        if (counts.event_count) bits.push(`events=${{counts.event_count}}`);
                        if (job.result_summary) bits.push(String(job.result_summary));
                        if (job.error_text) bits.push(String(job.error_text));
                        return bits.filter(Boolean).join(" · ");
                    }}

                    async function fetchJobByKey(jobKey) {{
                        const response = await fetch(`/api/jobs/by-key?job_key=${{encodeURIComponent(jobKey)}}&include_finished=true`);
                        const payload = await response.json();
                        return payload.job || null;
                    }}

                    async function fetchJob(jobId) {{
                        const response = await fetch(`/api/jobs/${{encodeURIComponent(String(jobId))}}`);
                        const payload = await response.json();
                        return payload.job || null;
                    }}

                    function pollJob(jobId, onUpdate, onDone) {{
                        let stopped = false;
                        async function tick() {{
                            if (stopped) return;
                            const job = await fetchJob(jobId);
                            if (onUpdate) onUpdate(job);
                            const running = job && ["queued", "running"].includes(String(job.status || ""));
                            if (running) {{
                                window.setTimeout(tick, 2000);
                                return;
                            }}
                            if (onDone) onDone(job);
                        }}
                        tick();
                        return () => {{ stopped = true; }};
                    }}

                    function localDateText(d = new Date()) {{
                        const year = d.getFullYear();
                        const month = String(d.getMonth() + 1).padStart(2, "0");
                        const day = String(d.getDate()).padStart(2, "0");
                        return `${{year}}-${{month}}-${{day}}`;
                    }}

                    const initialState = readUrlState();
                    let selectedDate = initialState.date || {json.dumps(default_date)};

                    function getOutputLanguage() {{
                        const selected = summaryLanguage && summaryLanguage.value ? String(summaryLanguage.value) : "zh-CN";
                        return selected || "zh-CN";
                    }}

                    function escapeHtml(value) {{
                        return String(value ?? "")
                            .replace(/&/g, "&amp;")
                            .replace(/</g, "&lt;")
                            .replace(/>/g, "&gt;")
                            .replace(/"/g, "&quot;")
                            .replace(/'/g, "&#39;");
                    }}

                    function renderRichText(value) {{
                        const content = String(value || "").trim();
                        if (!content) return "<p>—</p>";
                        return (window.marked && typeof window.marked.parse === "function")
                            ? window.marked.parse(content)
                            : `<pre>${{escapeHtml(content)}}</pre>`;
                    }}

                    function formatStoryArray(value) {{
                        if (!Array.isArray(value) || !value.length) return "<p>—</p>";
                        return `<ul>${{value.map((entry) => `<li>${{renderRichText(typeof entry === "object" ? JSON.stringify(entry) : String(entry))}}</li>`).join("")}}</ul>`;
                    }}

                    function initOutputLanguage() {{
                        const key = "preferred_output_language";
                        const saved = localStorage.getItem(key);
                        const normalized = initialState.lang || (saved === "en" ? "en" : "zh-CN");
                        if (summaryLanguage) {{
                            summaryLanguage.value = normalized;
                            summaryLanguage.addEventListener("change", () => {{
                                localStorage.setItem(key, getOutputLanguage());
                                updateUrlState();
                            }});
                        }}
                    }}

                    function modelOptionsHtml(selectedModel) {{
                        const current = String(selectedModel || defaultModel);
                        return singleNewsModels.map((choice) => {{
                            const model = String(choice.model || "");
                            const provider = String(choice.provider || "");
                            const selectedAttr = model === current ? "selected" : "";
                            return `<option value="${{model}}" data-provider="${{provider}}" ${{selectedAttr}}>${{provider}} · ${{model}}</option>`;
                        }}).join("");
                    }}

                    function initPricesAnalysisModelPicker() {{
                        if (!pricesAnalysisModelPicker) return;
                        const storageKey = "market_prices_analysis_model";
                        const savedModel = String(localStorage.getItem(storageKey) || "").trim();
                        pricesAnalysisModelPicker.innerHTML = modelOptionsHtml(savedModel || defaultModel);
                        pricesAnalysisModelPicker.addEventListener("change", () => {{
                            localStorage.setItem(storageKey, String(pricesAnalysisModelPicker.value || defaultModel));
                        }});
                    }}

                    function getSelectedPricesAnalysisModel() {{
                        if (!pricesAnalysisModelPicker) return defaultModel;
                        return String(pricesAnalysisModelPicker.value || defaultModel);
                    }}

                    function getSelectedPricesAnalysisProvider() {{
                        if (!pricesAnalysisModelPicker) return "openai";
                        const option = pricesAnalysisModelPicker.options[pricesAnalysisModelPicker.selectedIndex];
                        return String(option && option.dataset && option.dataset.provider ? option.dataset.provider : "openai");
                    }}

                    function isToday(dateText) {{
                        return String(dateText || "") === localDateText();
                    }}

                    function numFromText(value) {{
                        if (value === null || value === undefined) return NaN;
                        const cleaned = String(value).replace(/[%,$]/g, "").trim();
                        const parsed = Number(cleaned);
                        return Number.isFinite(parsed) ? parsed : NaN;
                    }}

                    function renderItems(container, items) {{
                        if (!container) return;
                        if (!items || !items.length) {{
                            container.innerHTML = '<p class="summary-status">No data available.</p>';
                            return;
                        }}
                        container.innerHTML = items.map((item) => {{
                            const pctText = item.price_change_pct || "—";
                            const pctValue = numFromText(pctText);
                            const changeClass = Number.isFinite(pctValue)
                                ? (pctValue > 0 ? "up" : (pctValue < 0 ? "down" : "flat"))
                                : "flat";
                            let headlineHtml = "";
                            if (item.headline) {{
                                const headlineBody = item.headline_url
                                    ? '<a href="' + item.headline_url + '" target="_blank" rel="noopener noreferrer">' + item.headline + "</a>"
                                    : item.headline;
                                headlineHtml = '<div class="headline">' + headlineBody + "</div>";
                                if (item.headline_time) {{
                                    headlineHtml += '<div class="headline-time">' + item.headline_time + "</div>";
                                }}
                            }}
                            return `
                                <div class="market-item">
                                    <h3>${{item.label || "Item"}}</h3>
                                    <div class="symbol">${{item.symbol || "—"}}</div>
                                    ${{item.country_code ? `<div class="country">${{item.country_code}}</div>` : ""}}
                                    <div class="price">${{item.close_price || "—"}}</div>
                                    <div class="change ${{changeClass}}">Change: ${{pctText}}</div>
                                    ${{headlineHtml}}
                                </div>
                            `;
                        }}).join("");
                    }}

                    function renderOverviewSections(sections, payload) {{
                        if (!overviewGridEl) return;
                        if (!sections || !sections.length) {{
                            overviewGridEl.innerHTML = '<p class="summary-status">No market snapshot available.</p>';
                            return;
                        }}
                        overviewGridEl.innerHTML = sections.map((section, idx) => `
                            <section class="market-overview-section" data-section-key="${{section.key || idx}}">
                                <h3 class="market-overview-section-title">${{escapeHtml(section.label || section.key || "Section")}}</h3>
                                <div class="market-grid" id="market-overview-section-grid-${{idx}}"></div>
                            </section>
                        `).join("");
                        sections.forEach((section, idx) => {{
                            const grid = document.getElementById(`market-overview-section-grid-${{idx}}`);
                            renderItems(grid, section.items || []);
                        }});
                        if (overviewStatusEl && payload) {{
                            const priceDateText = payload.price_date && payload.price_date !== payload.date ? ` · price_date=${{payload.price_date}}` : "";
                            overviewStatusEl.textContent = `Date ${{payload.date || selectedDate}}${{priceDateText}} · prices=${{payload.price_data_source || "—"}}`;
                        }}
                    }}

                    function renderMarketSections(container, sections) {{
                        if (!container) return;
                        if (!sections || !sections.length) {{
                            container.innerHTML = '<p class="summary-status">No price snapshot available for this date.</p>';
                            return;
                        }}
                        container.innerHTML = sections.map((section, idx) => `
                            <section class="market-overview-section" data-section-key="${{section.key || idx}}">
                                <h3 class="market-overview-section-title">${{section.label || section.key || "Section"}}</h3>
                                <div class="market-grid" id="market-section-grid-${{idx}}"></div>
                            </section>
                        `).join("");
                        sections.forEach((section, idx) => {{
                            const grid = document.getElementById(`market-section-grid-${{idx}}`);
                            renderItems(grid, section.items || []);
                        }});
                    }}

                    function renderPricesAnalysis(analysis) {{
                        if (!pricesAnalysisOutputEl || !pricesAnalysisNotesEl) return;
                        if (!analysis) {{
                            pricesAnalysisOutputEl.innerHTML = '<p class="summary-status">No stored prices analysis yet for this date.</p>';
                            pricesAnalysisNotesEl.innerHTML = "";
                            return;
                        }}
                        const structured = analysis.output_json || {{}};
                        const signals = Array.isArray(structured.signals) && structured.signals.length
                            ? `<ul class="prices-list">${{structured.signals.map((item) => `<li>${{escapeHtml(String(item))}}</li>`).join("")}}</ul>`
                            : "";
                        const risks = Array.isArray(structured.risks) && structured.risks.length
                            ? `<ul class="prices-list">${{structured.risks.map((item) => `<li>${{escapeHtml(String(item))}}</li>`).join("")}}</ul>`
                            : "";
                        pricesAnalysisOutputEl.innerHTML = `
                            <div class="summary-card">
                                <div class="news-meta">${{analysis.updated_at || analysis.created_at || ""}} · provider=${{analysis.provider}} · model=${{analysis.model}}</div>
                                <div class="summary-output">${{renderRichText(analysis.output_text || structured.main_narrative || "")}}</div>
                                ${{structured.us_market_logic ? `<div class="summary-output"><strong>US Market Logic</strong>${{renderRichText(structured.us_market_logic)}}</div>` : ""}}
                                ${{structured.rotation_take ? `<div class="summary-output"><strong>Rotation</strong>${{renderRichText(structured.rotation_take)}}</div>` : ""}}
                                ${{signals ? `<div class="summary-output"><strong>Signals</strong>${{signals}}</div>` : ""}}
                                ${{risks ? `<div class="summary-output"><strong>Risks</strong>${{risks}}</div>` : ""}}
                            </div>
                        `;
                        const notes = Array.isArray(structured.section_notes) ? structured.section_notes : [];
                        pricesAnalysisNotesEl.innerHTML = notes.map((item) => `
                            <div class="prices-note-card">
                                <h4>${{escapeHtml(item.section_label || item.section_key || "Section")}}</h4>
                                <div>${{renderRichText(item.summary || "")}}</div>
                            </div>
                        `).join("");
                    }}

                    async function loadMarketSnapshot() {{
                        const response = await fetch(`/api/market/overview?date=${{encodeURIComponent(selectedDate)}}`);
                        const payload = await response.json();
                        if (!response.ok || payload.error) {{
                            if (overviewStatusEl) overviewStatusEl.textContent = payload.error || "Failed to load market snapshot.";
                            return null;
                        }}
                        latestMarketPayload = payload;
                        latestMarketSections = Array.isArray(payload.sections) ? payload.sections : [];
                        renderOverviewSections(latestMarketSections, payload);
                        return payload;
                    }}

                    async function loadPricesAnalysis(refresh = false) {{
                        if (pricesAnalysisStatusEl) {{
                            pricesAnalysisStatusEl.textContent = refresh ? "Generating prices analysis..." : "Loading prices analysis...";
                        }}
                        const selectedModel = getSelectedPricesAnalysisModel();
                        const selectedProvider = getSelectedPricesAnalysisProvider();
                        const endpoint = refresh
                            ? `/api/market/prices/analysis/generate?date=${{encodeURIComponent(selectedDate)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&provider=${{encodeURIComponent(selectedProvider)}}&model=${{encodeURIComponent(selectedModel)}}`
                            : `/api/market/prices/analysis?date=${{encodeURIComponent(selectedDate)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&provider=${{encodeURIComponent(selectedProvider)}}`;
                        const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                        const payload = await response.json();
                        if (!response.ok || payload.error) {{
                            if (pricesAnalysisStatusEl) pricesAnalysisStatusEl.textContent = payload.error || "Failed to load prices analysis.";
                            renderPricesAnalysis(null);
                            return;
                        }}
                        if (!refresh && !payload.analysis) {{
                            await loadPricesAnalysis(true);
                            return;
                        }}
                        renderPricesAnalysis(payload.analysis || null);
                        if (pricesAnalysisStatusEl) {{
                            pricesAnalysisStatusEl.textContent = payload.analysis
                                ? `stored for ${{payload.analysis.analysis_date}}`
                                : "No stored prices analysis.";
                        }}
                    }}

                    function renderSummaryHistory(items) {{
                        if (!summariesEl) return;
                        if (!items || !items.length) {{
                            summariesEl.innerHTML = '<p class="summary-status">No market summary yet for this date.</p>';
                            return;
                        }}
                        summariesEl.innerHTML = items.map((item) => `
                            <div class="summary-card">
                                <div class="news-meta">${{item.created_at || ""}} · provider=${{item.provider}} · model=${{item.model}}</div>
                                <div class="summary-output">${{renderRichText(item.output_text || "")}}</div>
                            </div>
                        `).join("");
                    }}

                    function renderDailyClusters(items) {{
                        if (!marketDailyClustersEl) return;
                        if (!items || !items.length) {{
                            marketDailyClustersEl.innerHTML = '<p class="summary-status">No daily clusters yet for this date.</p>';
                            return;
                        }}
                        marketDailyClustersEl.innerHTML = `
                            <section class="summary-card">
                                <h3 style="margin:0 0 0.55rem;">Daily Clusters</h3>
                                <div class="market-grid">
                                    ${{items.map((item) => `
                                        <div class="overview-card">
                                            <h3>${{item.cluster_title || "Cluster"}}</h3>
                                            <div>${{renderRichText(item.cluster_summary || "")}}</div>
                                        </div>
                                    `).join("")}}
                                </div>
                            </section>
                        `;
                    }}

                    function renderNews(items) {{
                        const container = document.getElementById("market-news");
                        if (!container) return;
                        if (!items || !items.length) {{
                            container.innerHTML = '<p class="summary-status">No market news available.</p>';
                            return;
                        }}
                        const deriveTag = (item) => {{
                            const explicit = String(item.source_tag || "").trim().toLowerCase();
                            if (explicit.includes("yahoo")) return "yahoo";
                            if (explicit.includes("finnhub")) return "finnhub";
                            return "";
                        }};
                        container.innerHTML = items.map((item) => `
                            <div class="news-item" data-news-url="${{item.url || ""}}">
                                ${{deriveTag(item) ? `<span class="news-tag">${{deriveTag(item)}}</span>` : ""}}
                                <a href="${{item.url}}" target="_blank" rel="noopener noreferrer">${{item.headline}}</a>
                                <div class="news-meta">${{item.source || "Unknown source"}} · ${{item.datetime_text || ""}}</div>
                                <div class="news-actions">
                                    <select class="news-model-picker">${{modelOptionsHtml(defaultModel)}}</select>
                                    <button class="news-analyze-btn" type="button">Analyze</button>
                                    <button class="news-create-story-btn" type="button">New Story</button>
                                    <button class="news-attach-story-btn" type="button">Attach</button>
                                    <span class="attach-story-inline">
                                        <select class="attach-story-select">
                                            <option value="">Pick story</option>
                                            ${{latestStoryOptions.map((story) => `<option value="${{story.story_key}}">${{story.story_title}}</option>`).join("")}}
                                        </select>
                                        <button class="news-attach-confirm-btn" type="button">Attach</button>
                                    </span>
                                </div>
                                <div class="news-analysis">
                                    <div class="news-analysis-meta"></div>
                                    <div class="news-analysis-text"></div>
                                </div>
                            </div>
                        `).join("");
                        container.querySelectorAll(".news-item").forEach((card) => {{
                            card.addEventListener("click", (event) => {{
                                if (event.target.closest("a") || event.target.closest("button") || event.target.closest("select")) return;
                                card.classList.toggle("expanded");
                            }});
                        }});
                        container.querySelectorAll(".news-analyze-btn").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = button.closest(".news-item");
                                if (!card) return;
                                const modelPicker = card.querySelector(".news-model-picker");
                                const selectedModel = modelPicker && modelPicker.value ? String(modelPicker.value) : defaultModel;
                                const url = card.getAttribute("data-news-url") || "";
                                const item = (items || []).find((row) => String(row.url || "") === String(url));
                                if (!item) return;
                                button.disabled = true;
                                button.textContent = "Analyzing...";
                                try {{
                                    const response = await fetch(`/api/market/news/item-analyze?model=${{encodeURIComponent(selectedModel)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{
                                        method: "POST",
                                        headers: {{ "Content-Type": "application/json" }},
                                        body: JSON.stringify({{ date: selectedDate, item }}),
                                    }});
                                    const payload = await response.json();
                                    if (!response.ok || payload.error) {{
                                        alert(payload.error || "Analyze failed");
                                        return;
                                    }}
                                    const analysis = payload.analysis || null;
                                    if (analysis) {{
                                        const meta = card.querySelector(".news-analysis-meta");
                                        const text = card.querySelector(".news-analysis-text");
                                        if (meta) meta.textContent = `provider=${{analysis.provider}} · model=${{analysis.model}} · updated=${{analysis.updated_at}}`;
                                        if (text) text.innerHTML = renderRichText(analysis.output_text || "");
                                        card.classList.add("expanded");
                                    }}
                                }} finally {{
                                    button.disabled = false;
                                    button.textContent = "Analyze";
                                }}
                            }});
                        }});
                        container.querySelectorAll(".news-create-story-btn").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = button.closest(".news-item");
                                if (!card) return;
                                const url = card.getAttribute("data-news-url") || "";
                                const item = (items || []).find((row) => String(row.url || "") === String(url));
                                if (!item) return;
                                const storyTitle = window.prompt("Story title", item.headline || "");
                                if (!storyTitle) return;
                                await fetch(`/api/market/stories/create-from-news?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{
                                    method: "POST",
                                    headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ date: selectedDate, story_title: storyTitle, item }}),
                                }});
                                await loadMarketStories(false);
                            }});
                        }});
                        container.querySelectorAll(".news-attach-story-btn").forEach((button) => {{
                            button.addEventListener("click", (event) => {{
                                event.stopPropagation();
                                const card = button.closest(".news-item");
                                if (!card) return;
                                const inline = card.querySelector(".attach-story-inline");
                                if (!inline) return;
                                inline.classList.toggle("active");
                            }});
                        }});
                        container.querySelectorAll(".news-attach-confirm-btn").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = button.closest(".news-item");
                                if (!card) return;
                                const picker = card.querySelector(".attach-story-select");
                                const storyKey = picker && picker.value ? String(picker.value) : "";
                                if (!storyKey) return;
                                const url = card.getAttribute("data-news-url") || "";
                                const item = (items || []).find((row) => String(row.url || "") === String(url));
                                if (!item) return;
                                await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/attach-news?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{
                                    method: "POST",
                                    headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ date: selectedDate, item }}),
                                }});
                                await loadMarketStories(false);
                            }});
                        }});
                    }}

                    async function loadDailyNews(refresh = false) {{
                        try {{
                            const params = new URLSearchParams({{
                                date: selectedDate,
                                prompt_style: "simple",
                                output_language: getOutputLanguage(),
                            }});
                            const endpoint = refresh ? `/api/market/daily-news/refresh?${{params.toString()}}` : `/api/market/daily-news?${{params.toString()}}`;
                            const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                if (summaryStatus) summaryStatus.textContent = payload.error || "Analyze failed";
                                return;
                            }}
                            latestNews = payload.raw_news || [];
                            renderNews(latestNews);
                            renderSummaryHistory(payload.summaries || []);
                            renderDailyClusters(payload.clusters || []);
                            await loadSummaryDates();
                            if (summaryStatus) {{
                                const count = Number((payload.raw_news || []).length || 0);
                                summaryStatus.textContent = `${{count}} item${{count === 1 ? "" : "s"}}${{refresh ? " · update started" : ""}}`;
                            }}
                            if (refresh && payload.job) {{
                                if (refreshDailyNewsBtn) {{
                                    refreshDailyNewsBtn.disabled = true;
                                    refreshDailyNewsBtn.textContent = "Refresh Running...";
                                }}
                                if (dailyNewsJobStop) dailyNewsJobStop();
                                dailyNewsJobStop = pollJob(payload.job.job_id, (job) => {{
                                    if (summaryStatus) summaryStatus.textContent = formatJobText(job);
                                }}, async () => {{
                                    if (refreshDailyNewsBtn) {{
                                        refreshDailyNewsBtn.disabled = false;
                                        refreshDailyNewsBtn.textContent = "Refresh Daily News";
                                    }}
                                    await loadDailyNews(false);
                                }});
                            }}
                        }} catch (error) {{
                            if (summaryStatus) summaryStatus.textContent = "Refresh failed";
                            console.error(error);
                        }}
                    }}

                    async function ensureDailyNewsLoaded() {{
                        await loadDailyNews(false);
                        const key = `${{selectedDate}}|simple|${{getOutputLanguage()}}`;
                        const hasStoredDailyNews = Array.isArray(latestNews) && latestNews.length > 0;
                        if (hasStoredDailyNews) {{
                            dailyNewsAutoInitializedKey = key;
                            return;
                        }}
                        if (dailyNewsAutoInitializedKey === key) return;
                        dailyNewsAutoInitializedKey = key;
                        await loadDailyNews(true);
                    }}

                    function buildMarketTimeline(story) {{
                        const timelineItems = Array.isArray(story.timeline_items) ? story.timeline_items.filter((item) => item && typeof item === "object") : [];
                        if (timelineItems.length) return timelineItems;
                        const fallback = [];
                        if (story.happened_text) fallback.push({{ label: "Earlier", summary: story.happened_text }});
                        if (story.happening_text) fallback.push({{ label: "Current", summary: story.happening_text }});
                        return fallback;
                    }}

                    function buildMarketFuture(story) {{
                        const futureItems = Array.isArray(story.future_and_impact) ? story.future_and_impact.filter((item) => item && typeof item === "object") : [];
                        if (futureItems.length) return futureItems;
                        if (story.next_text) return [{{ scenario: story.next_text }}];
                        return [];
                    }}

                    function renderMarketStoryGroup(title, stories) {{
                        if (!Array.isArray(stories) || !stories.length) return "";
                        return `
                            <div class="story-group-heading">${{escapeHtml(title)}}</div>
                            ${{stories.map((story) => `
                                <div class="story-item ${{story.story_key === activeMarketStoryKey ? "active" : ""}}" data-story-key="${{story.story_key}}">
                                    <div class="story-item-title">${{escapeHtml(story.story_title || "")}}</div>
                                    <div class="story-item-meta">#${{story.importance_rank || "—"}} · ${{escapeHtml(story.story_status || "ongoing")}}</div>
                                </div>
                            `).join("")}}
                        `;
                    }}

                    function renderMarketStoryDetail(story) {{
                        if (!story) return '<p class="placeholder">Select a story to see details.</p>';
                        const summaryText = String(story.story_summary || story.happening_text || story.happened_text || story.next_text || "").trim();
                        const timelineRows = formatStoryArray(buildMarketTimeline(story));
                        const futureRows = formatStoryArray(buildMarketFuture(story));
                        const isClosed = ["finished", "resolved", "closed"].includes(String(story.story_status || "").toLowerCase());
                        return `
                            <div class="story-detail-section">
                                <h3>${{escapeHtml(story.story_title || "")}}</h3>
                                <div class="story-item-meta">status=${{escapeHtml(story.story_status || "ongoing")}} · priority=${{escapeHtml(story.priority || "normal")}} · updated=${{escapeHtml(story.updated_at || "")}}</div>
                                <div class="story-detail-box">${{renderRichText(summaryText || "—")}}</div>
                                <div class="news-actions" style="margin-top:0.6rem;">
                                    <button class="story-close-btn" type="button" data-story-key="${{story.story_key}}">${{isClosed ? "Reopen Story" : "Close Story"}}</button>
                                    <button class="story-priority-btn" type="button" data-story-key="${{story.story_key}}" data-priority="${{story.priority === 'high' ? 'normal' : 'high'}}">${{story.priority === 'high' ? 'Set Normal Priority' : 'Set High Priority'}}</button>
                                </div>
                            </div>
                            <div class="story-detail-section"><h3>Timeline</h3><div class="story-detail-box">${{timelineRows}}</div></div>
                            <div class="story-detail-section"><h3>Future and Impact</h3><div class="story-detail-box">${{futureRows}}</div></div>
                            <div class="story-detail-section"><h3>Evidence</h3><div class="story-detail-box">${{formatStoryArray(story.evidence || [])}}</div></div>
                            <div class="story-detail-section"><h3>Recent Changes</h3><div class="story-detail-box">${{formatStoryArray(story.change_log || [])}}</div></div>
                        `;
                    }}

                    async function loadMarketStories(refresh = false) {{
                        if (marketStoriesStatus) marketStoriesStatus.textContent = refresh ? "Refreshing..." : "Loading...";
                        const lang = getOutputLanguage();
                        const endpoint = refresh
                            ? `/api/market/stories/refresh?prompt_style=simple&output_language=${{encodeURIComponent(lang)}}`
                            : `/api/market/stories?prompt_style=simple&output_language=${{encodeURIComponent(lang)}}`;
                        const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                        const payload = await response.json();
                        const warmup = payload.warmup || {{}};
                        const parts = [];
                        if (warmup.job_state) parts.push(`state=${{warmup.job_state}}`);
                        if (warmup.current_stage) parts.push(`stage=${{warmup.current_stage}}`);
                        if (payload.latest_story_date) parts.push(`latest=${{payload.latest_story_date}}`);
                        if (marketStoryWarmup) marketStoryWarmup.textContent = parts.join(" · ");
                        latestStoryOptions = [...(payload.ongoing_stories || []), ...(payload.finished_stories || [])];
                        if (!activeMarketStoryKey || !latestStoryOptions.some((story) => story.story_key === activeMarketStoryKey)) {{
                            activeMarketStoryKey = latestStoryOptions.length ? String(latestStoryOptions[0].story_key || "") : "";
                        }}
                        if (marketStoryListEl) {{
                            const listHtml = [
                                renderMarketStoryGroup("Ongoing Stories", payload.ongoing_stories || []),
                                renderMarketStoryGroup("Finished Stories", payload.finished_stories || []),
                            ].filter(Boolean).join("");
                            marketStoryListEl.innerHTML = listHtml || '<p class="placeholder">No stories yet.</p>';
                            marketStoryListEl.querySelectorAll(".story-item").forEach((node) => {{
                                node.addEventListener("click", () => {{
                                    activeMarketStoryKey = String(node.dataset.storyKey || "");
                                    marketStoryListEl.querySelectorAll(".story-item").forEach((x) => x.classList.remove("active"));
                                    node.classList.add("active");
                                    const activeStory = latestStoryOptions.find((story) => story.story_key === activeMarketStoryKey) || null;
                                    if (marketStoryDetailEl) marketStoryDetailEl.innerHTML = renderMarketStoryDetail(activeStory);
                                    bindMarketStoryDetailActions();
                                }});
                            }});
                        }}
                        if (marketStoryDetailEl) {{
                            const activeStory = latestStoryOptions.find((story) => story.story_key === activeMarketStoryKey) || null;
                            marketStoryDetailEl.innerHTML = renderMarketStoryDetail(activeStory);
                        }}
                        bindMarketStoryDetailActions();
                        if (marketStoriesStatus) marketStoriesStatus.textContent = payload.job ? formatJobText(payload.job) : "";
                    }}

                    function bindMarketStoryDetailActions() {{
                        document.querySelectorAll(".story-close-btn").forEach((button) => {{
                            button.addEventListener("click", async () => {{
                                const storyKey = button.getAttribute("data-story-key") || "";
                                const nextAction = String(button.textContent || "").toLowerCase().includes("reopen") ? "reopen" : "close";
                                await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/${{nextAction}}?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{ method: "POST" }});
                                await loadMarketStories(false);
                            }});
                        }});
                        document.querySelectorAll(".story-priority-btn").forEach((button) => {{
                            button.addEventListener("click", async () => {{
                                const storyKey = button.getAttribute("data-story-key") || "";
                                const priority = button.getAttribute("data-priority") || "high";
                                await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/priority?priority=${{encodeURIComponent(priority)}}&prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{ method: "POST" }});
                                await loadMarketStories(false);
                            }});
                        }});
                    }}

                    async function ensureMarketStoriesLoaded() {{
                        await loadMarketStories(false);
                        const key = `${{selectedDate}}|simple|${{getOutputLanguage()}}`;
                        if (latestStoryOptions.length) {{
                            marketStoriesAutoInitializedKey = key;
                            return;
                        }}
                        if (marketStoriesAutoInitializedKey === key) return;
                        marketStoriesAutoInitializedKey = key;
                        await loadMarketStories(true);
                    }}

                    function formatMacroCellLabel(name) {{
                        const text = String(name || "").trim();
                        if (!text) return "Event";
                        const replacements = [
                            ["Consumer Price Index", "CPI"],
                            ["Producer Price Index", "PPI"],
                            ["Nonfarm Payrolls", "NFP"],
                            ["Federal Open Market Committee", "FOMC"],
                            ["Gross Domestic Product", "GDP"],
                            ["Unemployment Rate", "Unemployment"],
                            ["Retail Sales", "Retail Sales"],
                            ["Consumer Confidence", "Confidence"],
                            ["Trade Balance", "Trade Balance"],
                        ];
                        for (const [needle, label] of replacements) {{
                            if (text.toLowerCase().includes(needle.toLowerCase())) return label;
                        }}
                        return text.length > 22 ? `${{text.slice(0, 21)}}…` : text;
                    }}

                    function renderMacroEvents(events) {{
                        if (!marketMacroEventsEl) return;
                        if (!events || !events.length) {{
                            marketMacroEventsEl.innerHTML = '<p class="summary-status">No calendar events available.</p>';
                            return;
                        }}
                        const eventsByDate = new Map();
                        for (const item of events) {{
                            const dateKey = String(item.event_date_time || "").slice(0, 10);
                            if (!dateKey) continue;
                            if (!eventsByDate.has(dateKey)) eventsByDate.set(dateKey, []);
                            eventsByDate.get(dateKey).push(item);
                        }}
                        const dateKeys = Array.from(eventsByDate.keys()).sort();
                        if (!selectedMacroDate || !eventsByDate.has(selectedMacroDate)) {{
                            selectedMacroDate = dateKeys[0] || "";
                        }}
                        const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
                        const firstDate = new Date(`${{dateKeys[0]}}T00:00:00`);
                        const lastDate = new Date(`${{dateKeys[dateKeys.length - 1]}}T00:00:00`);
                        const monthStarts = [];
                        const cursor = new Date(firstDate.getFullYear(), firstDate.getMonth(), 1);
                        while (cursor <= lastDate) {{
                            monthStarts.push(new Date(cursor));
                            cursor.setMonth(cursor.getMonth() + 1);
                        }}
                        const monthHtml = monthStarts.map((monthStart) => {{
                            const year = monthStart.getFullYear();
                            const month = monthStart.getMonth();
                            const monthLabel = monthStart.toLocaleDateString(undefined, {{ year: "numeric", month: "long" }});
                            const startWeekday = new Date(year, month, 1).getDay();
                            const endDay = new Date(year, month + 1, 0).getDate();
                            const cells = [];
                            for (let i = 0; i < startWeekday; i += 1) {{
                                cells.push('<div class="macro-day-cell empty"></div>');
                            }}
                            for (let day = 1; day <= endDay; day += 1) {{
                                const dt = new Date(year, month, day);
                                const key = `${{dt.getFullYear()}}-${{String(dt.getMonth() + 1).padStart(2, "0")}}-${{String(day).padStart(2, "0")}}`;
                                const dayEvents = eventsByDate.get(key) || [];
                                const classes = ["macro-day-cell"];
                                if (dayEvents.length) classes.push("has-events");
                                if (key === selectedMacroDate) classes.push("selected");
                                const labels = dayEvents.slice(0, 3).map((item) => `<div class="macro-pill" title="${{String(item.event_name || "").replace(/"/g, "&quot;")}}">${{formatMacroCellLabel(item.event_name)}}</div>`).join("");
                                const overflow = dayEvents.length > 3 ? `<div class="macro-overflow">+${{dayEvents.length - 3}}</div>` : "";
                                cells.push(`
                                    <button type="button" class="${{classes.join(" ")}}" data-macro-date="${{key}}">
                                        <div class="macro-day-num">${{day}}</div>
                                        <div class="macro-day-events">${{labels}}${{overflow}}</div>
                                    </button>
                                `);
                            }}
                            return `
                                <section>
                                    <h3 class="macro-month-title">${{monthLabel}}</h3>
                                    <div class="macro-month-grid">
                                        ${{weekdays.map((label) => `<div class="macro-weekday">${{label}}</div>`).join("")}}
                                        ${{cells.join("")}}
                                    </div>
                                </section>
                            `;
                        }}).join("");
                        const selectedEvents = eventsByDate.get(selectedMacroDate) || [];
                        const detailHtml = selectedEvents.length
                            ? selectedEvents.map((item) => `
                                <div class="macro-detail-item">
                                    <h3>${{item.event_name || "Event"}}</h3>
                                    <div class="macro-detail-meta">${{item.country || "US"}} · ${{item.category || "macro"}} · ${{item.event_date_time || ""}}</div>
                                    <div class="macro-detail-values">
                                        <div><strong>Actual:</strong> ${{item.actual_value || "—"}}${{item.unit ? ` ${{item.unit}}` : ""}}</div>
                                        <div><strong>Prior:</strong> ${{item.previous_value || "—"}}</div>
                                        <div><strong>Expectation:</strong> ${{item.consensus_value || "—"}}</div>
                                    </div>
                                    ${{item.source_url ? `<div class="macro-detail-link"><a href="${{item.source_url}}" target="_blank" rel="noopener noreferrer">Source</a></div>` : ""}}
                                </div>
                            `).join("")
                            : '<p class="summary-status">Select a day with events.</p>';
                        marketMacroEventsEl.innerHTML = `
                            <div class="macro-calendar-wrap">
                                ${{monthHtml}}
                                <div class="macro-detail-card">
                                    <div class="macro-detail-date">${{selectedMacroDate || "Selected day"}}</div>
                                    ${{detailHtml}}
                                </div>
                            </div>
                        `;
                        marketMacroEventsEl.querySelectorAll("[data-macro-date]").forEach((button) => {{
                            button.addEventListener("click", () => {{
                                selectedMacroDate = button.getAttribute("data-macro-date") || "";
                                renderMacroEvents(events);
                            }});
                        }});
                    }}

                    async function loadCalendar(refresh = false) {{
                        const endpoint = refresh
                            ? `/api/market/macro/refresh?output_language=${{encodeURIComponent(getOutputLanguage())}}`
                            : "/api/market/macro";
                        const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                        const payload = await response.json();
                        renderMacroEvents(payload.events || []);
                        if (marketMacroStatus) marketMacroStatus.textContent = payload.job ? formatJobText(payload.job) : "";
                        if (payload.job && refreshMacroBtn) {{
                            const running = ["queued", "running"].includes(String(payload.job.status || ""));
                            refreshMacroBtn.disabled = running;
                            refreshMacroBtn.textContent = running ? "Refresh Running..." : "Refresh 3 Months";
                            if (running) {{
                                if (macroJobStop) macroJobStop();
                                macroJobStop = pollJob(payload.job.job_id, (job) => {{
                                    if (marketMacroStatus) marketMacroStatus.textContent = formatJobText(job);
                                }}, async () => {{
                                    refreshMacroBtn.disabled = false;
                                    refreshMacroBtn.textContent = "Refresh 3 Months";
                                    await loadCalendar(false);
                                }});
                            }}
                        }}
                    }}

                    function setMarketView(mode) {{
                        const allowed = new Set(["overview", "daily-news", "stories", "calendar"]);
                        currentMarketView = allowed.has(mode) ? mode : "overview";
                        document.querySelectorAll(".market-subview").forEach((el) => {{
                            el.classList.toggle("active", el.id === `market-${{currentMarketView}}-view`);
                        }});
                        if (marketViewTabs) {{
                            marketViewTabs.querySelectorAll(".subtab-btn").forEach((btn) => {{
                                btn.classList.toggle("active", btn.dataset.marketView === currentMarketView);
                            }});
                        }}
                        updateUrlState();
                    }}

                    function isUsMarketHoursNow() {{
                        const now = new Date();
                        const parts = new Intl.DateTimeFormat("en-US", {{
                            timeZone: "America/New_York",
                            weekday: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: false,
                        }}).formatToParts(now);
                        const weekday = parts.find((part) => part.type === "weekday")?.value || "";
                        const hour = Number(parts.find((part) => part.type === "hour")?.value || "0");
                        const minute = Number(parts.find((part) => part.type === "minute")?.value || "0");
                        const dayMap = {{ Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }};
                        const dayNum = dayMap[weekday] || 0;
                        if (dayNum < 1 || dayNum > 5) return false;
                        const minutesFromMidnight = hour * 60 + minute;
                        return minutesFromMidnight >= 570 && minutesFromMidnight <= 960;
                    }}

                    async function loadSummaryDates() {{
                        try {{
                            const response = await fetch("/api/market/news/summary-dates?lookback_days=365");
                            const payload = await response.json();
                            const rows = payload.dates || [];
                            reportDateSet = new Set(rows.map((row) => String(row.date || "")));
                            datePickers.forEach((picker) => {{
                                if (picker && typeof picker.redraw === "function") picker.redraw();
                            }});
                        }} catch (_error) {{
                            reportDateSet = new Set();
                        }}
                    }}

                    async function onDateChanged(nextDate) {{
                        selectedDate = String(nextDate || selectedDate);
                        dateInputs.forEach((input) => {{
                            if (input) input.value = selectedDate;
                        }});
                        datePickers.forEach((picker) => {{
                            if (picker && typeof picker.setDate === "function") picker.setDate(selectedDate, false);
                        }});
                        await loadMarketSnapshot();
                        if (currentMarketView === "overview") {{
                            await loadPricesAnalysis(false);
                        }} else if (currentMarketView === "daily-news") {{
                            await ensureDailyNewsLoaded();
                        }} else if (currentMarketView === "stories") {{
                            await ensureMarketStoriesLoaded();
                        }} else if (currentMarketView === "calendar") {{
                            await loadCalendar(false);
                        }}
                        updateUrlState();
                    }}

                    if (refreshOverviewBtn) {{
                        refreshOverviewBtn.addEventListener("click", async () => {{
                            await loadMarketSnapshot();
                        }});
                    }}
                    if (refreshPricesAnalysisBtn) {{
                        refreshPricesAnalysisBtn.addEventListener("click", async () => {{
                            await loadPricesAnalysis(true);
                        }});
                    }}
                    if (refreshDailyNewsBtn) {{
                        refreshDailyNewsBtn.addEventListener("click", () => loadDailyNews(true));
                    }}
                    const refreshStoriesBtn = document.getElementById("refresh-market-stories");
                    if (refreshStoriesBtn) {{
                        refreshStoriesBtn.addEventListener("click", async () => {{
                            await loadMarketStories(true);
                        }});
                    }}
                    if (refreshMacroBtn) {{
                        refreshMacroBtn.addEventListener("click", async () => {{
                            await loadCalendar(true);
                        }});
                    }}
                    if (marketViewTabs) {{
                        marketViewTabs.querySelectorAll(".subtab-btn").forEach((btn) => {{
                            btn.addEventListener("click", async () => {{
                                const next = btn.dataset.marketView || "overview";
                                setMarketView(next);
                                if (next === "overview") {{
                                    await loadPricesAnalysis(false);
                                }} else if (next === "daily-news") {{
                                    await ensureDailyNewsLoaded();
                                }} else if (next === "stories") {{
                                    await ensureMarketStoriesLoaded();
                                }} else if (next === "calendar") {{
                                    await loadCalendar(false);
                                }}
                            }});
                        }});
                    }}

                    initOutputLanguage();
                    initPricesAnalysisModelPicker();
                    if (window.flatpickr && dateInputs.length) {{
                        dateInputs.forEach((input) => {{
                            const picker = window.flatpickr(input, {{
                                dateFormat: "Y-m-d",
                                defaultDate: selectedDate,
                                maxDate: "today",
                                onDayCreate: function(_dObj, _dStr, _fp, dayElem) {{
                                    const dateText = dayElem.dateObj.toISOString().slice(0, 10);
                                    if (reportDateSet.has(dateText)) dayElem.classList.add("has-report");
                                }},
                                onChange: function(selectedDates) {{
                                    if (!selectedDates || !selectedDates.length) return;
                                    const nextDate = selectedDates[0].toISOString().slice(0, 10);
                                    onDateChanged(nextDate);
                                }},
                            }});
                            datePickers.push(picker);
                        }});
                    }}

                    Promise.all([loadSummaryDates(), loadMarketSnapshot()]).then(async () => {{
                        setMarketView(initialState.view || "overview");
                        if (currentMarketView === "overview") {{
                            await loadPricesAnalysis(false);
                        }} else if (currentMarketView === "daily-news") {{
                            await ensureDailyNewsLoaded();
                        }} else if (currentMarketView === "stories") {{
                            await ensureMarketStoriesLoaded();
                        }} else if (currentMarketView === "calendar") {{
                            await loadCalendar(false);
                        }}
                    }});

                    setInterval(() => {{
                        if (!isUsMarketHoursNow() || !isToday(selectedDate)) return;
                        loadMarketSnapshot();
                    }}, 60000);
                </script>
            </body>
        </html>
    """
