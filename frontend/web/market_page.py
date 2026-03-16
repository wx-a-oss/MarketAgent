"""Market overview page rendering."""

from __future__ import annotations

import json
from typing import Dict, List

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from market_agent.config.models import DEFAULT_OPENAI_MODEL


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
    default_openai_model_json = json.dumps(DEFAULT_OPENAI_MODEL, ensure_ascii=False)
    return f"""
        <html>
            <head>
                <title>MarketAgent – Market</title>
                <link
                    rel="stylesheet"
                    href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css"
                />
                <style>
                    {BASE_PAGE_STYLES}
                    .report {{
                        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
                        font-size: 14px;
                        line-height: 1.7;
                        color: #0f172a;
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
                    .market-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 0.8rem;
                    }}
                    .market-overview-section {{
                        margin-top: 1rem;
                    }}
                    .market-overview-section:first-child {{
                        margin-top: 0.2rem;
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
                        margin-top: -0.1rem;
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
                    .section-title {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        margin-bottom: 0.6rem;
                    }}
                    .status {{
                        color: #6b7280;
                        font-size: 0.85rem;
                    }}
                    .news-list {{
                        display: grid;
                        gap: 0.7rem;
                    }}
                    .summary-controls {{
                        display: flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                        margin: 0.5rem 0 0.8rem;
                    }}
                    .summary-controls select {{
                        padding: 0.45rem 0.55rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.45rem;
                        background: #ffffff;
                    }}
                    .analyze-btn {{
                        background: #0f766e;
                    }}
                    .analyze-btn:hover {{
                        background: #0d9488;
                    }}
                    .summary-status {{
                        font-size: 0.82rem;
                        color: #6b7280;
                    }}
                    .view-toolbar {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        flex-wrap: wrap;
                        margin-bottom: 0.55rem;
                    }}
                    .view-toolbar h2,
                    .view-toolbar h1 {{
                        margin: 0;
                    }}
                    .view-toolbar-left,
                    .view-toolbar-right {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                    }}
                    .view-status-row {{
                        color: #6b7280;
                        font-size: 0.83rem;
                        margin-bottom: 0.85rem;
                    }}
                    .view-select {{
                        padding: 0.45rem 0.55rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.45rem;
                        background: #ffffff;
                        font-size: 0.9rem;
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
                    .summary-card .summary-output h1,
                    .summary-card .summary-output h2,
                    .summary-card .summary-output h3,
                    .summary-card .summary-output h4 {{
                        margin: 0.75rem 0 0.4rem;
                        line-height: 1.35;
                    }}
                    .summary-card .summary-output h1 {{ font-size: 1.12rem; }}
                    .summary-card .summary-output h2 {{ font-size: 1.04rem; }}
                    .summary-card .summary-output h3 {{ font-size: 0.98rem; }}
                    .summary-card .summary-output p {{
                        margin: 0.38rem 0;
                    }}
                    .summary-card .summary-output ul,
                    .summary-card .summary-output ol {{
                        margin: 0.42rem 0 0.42rem 1rem;
                        padding-left: 0.7rem;
                    }}
                    .summary-card .summary-output li {{
                        margin-bottom: 0.28rem;
                    }}
                    .summary-card .summary-output code {{
                        background: #eef2ff;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.28rem;
                        padding: 0.02rem 0.28rem;
                        font-size: 0.88em;
                    }}
                    .summary-card .summary-output pre {{
                        white-space: pre-wrap;
                        overflow-wrap: anywhere;
                        background: #ffffff;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.45rem;
                        padding: 0.55rem;
                    }}
                    .macro-calendar-wrap {{
                        display: grid;
                        gap: 1rem;
                    }}
                    .macro-calendar-note {{
                        font-size: 0.82rem;
                        color: #64748b;
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
                        max-width: 96px;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
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
                    .news-analyze-btn:hover {{
                        background: #0d9488;
                        border-color: #0d9488;
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
                    .news-item.expanded .news-analysis {{
                        display: block;
                    }}
                    .news-analysis-meta {{
                        color: #64748b;
                        font-size: 0.75rem;
                        margin-bottom: 0.35rem;
                    }}
                    .controls {{
                        display: flex;
                        gap: 0.5rem;
                        align-items: center;
                    }}
                    .date-input {{
                        padding: 0.45rem 0.55rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.45rem;
                        background: #ffffff;
                        font-size: 0.9rem;
                        width: 140px;
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
                    .refresh-btn {{
                        background: #16a34a;
                    }}
                    .refresh-btn:hover {{
                        background: #15803d;
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
                    .market-subview {{
                        display: none;
                    }}
                    .market-subview.active {{
                        display: block;
                    }}
                    .overview-toolbar {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        margin-bottom: 0.85rem;
                        flex-wrap: wrap;
                    }}
                    .overview-toolbar h1 {{
                        margin: 0;
                    }}
                    .overview-toolbar-meta {{
                        display: grid;
                        gap: 0.25rem;
                    }}
                    .overview-toolbar-copy {{
                        color: #6b7280;
                        font-size: 0.84rem;
                    }}
                    .overview-toolbar-controls {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                    }}
                    .overview-refresh-status {{
                        color: #6b7280;
                        font-size: 0.82rem;
                    }}
                    .story-group {{
                        display: grid;
                        gap: 0.7rem;
                        margin-top: 0.8rem;
                    }}
                    .story-card {{
                        border: 1px solid #dbe4ee;
                        border-radius: 0.75rem;
                        padding: 0.85rem;
                        background: #f8fafc;
                    }}
                    .story-card h3 {{
                        margin: 0 0 0.45rem;
                        font-size: 1rem;
                    }}
                    .story-section-label {{
                        display: block;
                        font-size: 0.78rem;
                        color: #64748b;
                        font-weight: 700;
                        margin: 0.55rem 0 0.2rem;
                        text-transform: uppercase;
                        letter-spacing: 0.04em;
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
                    .story-list {{
                        display: grid;
                        gap: 0.5rem;
                    }}
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
                    .story-detail-section {{
                        margin-top: 0.65rem;
                    }}
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
                    .placeholder {{
                        color: #64748b;
                    }}
                    @media (max-width: 1200px) {{
                        .stories-wrap {{
                            grid-template-columns: 260px minmax(0, 1fr);
                        }}
                        .stories-main {{
                            max-width: none;
                        }}
                    }}
                    @media (max-width: 900px) {{
                        .stories-wrap {{
                            grid-template-columns: 1fr;
                        }}
                        .stories-side {{
                            max-height: none;
                        }}
                    }}
                    .macro-events {{
                        display: grid;
                        gap: 0.7rem;
                    }}
                    .macro-card {{
                        border: 1px solid #e5e7eb;
                        border-radius: 0.65rem;
                        padding: 0.8rem;
                        background: #fafafa;
                    }}
                    .macro-card h3 {{
                        margin: 0 0 0.2rem;
                        font-size: 0.98rem;
                    }}
                    .attach-story-inline {{
                        display: none;
                        align-items: center;
                        gap: 0.35rem;
                    }}
                    .attach-story-inline.active {{
                        display: inline-flex;
                    }}
                </style>
            </head>
            <body class="report">
                {render_nav("market")}
                <div class="container">
                    <div class="subtabs" id="market-view-tabs">
                        <button class="subtab-btn active" type="button" data-market-view="overview">Overview</button>
                        <button class="subtab-btn" type="button" data-market-view="daily-news">Daily News</button>
                        <button class="subtab-btn" type="button" data-market-view="stories">Stories</button>
                    </div>

                    <div id="market-overview-view" class="market-subview active">
                        <section class="card">
                            <div class="view-toolbar">
                                <h2>Market Overview</h2>
                                <div class="view-toolbar-right">
                                    <input id="market-date-overview" class="date-input" type="text" />
                                    <button id="refresh-market" class="refresh-btn" type="button">Refresh Overview</button>
                                </div>
                            </div>
                            <div class="view-status-row">Pick a date to view the market snapshot. Auto refresh runs during U.S. market hours.</div>
                            <div id="market-status" class="overview-refresh-status"></div>
                            <div id="market-sections"></div>
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
                                <input id="market-date-stories" class="date-input" type="text" />
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
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    const singleNewsModels = {model_choices_json};
                    const refreshBtn = document.getElementById("refresh-market");
                    const overviewDateInput = document.getElementById("market-date-overview");
                    const dailyNewsDateInput = document.getElementById("market-date-daily-news");
                    const storiesDateInput = document.getElementById("market-date-stories");
                    const dateInputs = [overviewDateInput, dailyNewsDateInput, storiesDateInput].filter(Boolean);
                    const statusEl = document.getElementById("market-status");
                    const marketSectionsEl = document.getElementById("market-sections");
                    const summaryLanguage = document.getElementById("global-language-select");
                    const refreshDailyNewsBtn = document.getElementById("refresh-market-daily-news");
                    const summaryStatus = document.getElementById("summary-status");
                    const summariesEl = document.getElementById("news-summaries");
                    const marketDailyClustersEl = document.getElementById("market-daily-clusters");
                    const marketViewTabs = document.getElementById("market-view-tabs");
                    const marketStoriesStatus = document.getElementById("market-stories-status");
                    const marketStoryWarmup = document.getElementById("market-story-warmup");
                    const marketStoryListEl = document.getElementById("market-story-list");
                    const marketStoryDetailEl = document.getElementById("market-story-detail");
                    let latestNews = [];
                    let latestStoryOptions = [];
                    let activeMarketStoryKey = "";
                    let currentMarketView = "overview";
                    let dailyNewsAutoInitializedKey = "";
                    let marketStoriesAutoInitializedKey = "";
                    const datePickers = [];
                    function readUrlState() {{
                        const params = new URLSearchParams(window.location.search || "");
                        const lang = String(params.get("lang") || "").trim();
                        const date = String(params.get("date") || "").trim();
                        return {{
                            lang: lang === "en" ? "en" : "zh-CN",
                            date,
                        }};
                    }}
                    function updateUrlState() {{
                        const url = new URL(window.location.href);
                        const params = url.searchParams;
                        params.set("date", selectedDate);
                        params.set("lang", getOutputLanguage());
                        window.history.replaceState({{}}, "", `${{url.pathname}}?${{params.toString()}}`);
                    }}
                    const initialState = readUrlState();
                    function localDateText(d = new Date()) {{
                        const year = d.getFullYear();
                        const month = String(d.getMonth() + 1).padStart(2, "0");
                        const day = String(d.getDate()).padStart(2, "0");
                        return `${{year}}-${{month}}-${{day}}`;
                    }}
                    let selectedDate = initialState.date || localDateText();
                    let reportDateSet = new Set();

                    function getOutputLanguage() {{
                        const selected = summaryLanguage && summaryLanguage.value
                            ? String(summaryLanguage.value)
                            : "zh-CN";
                        return selected || "zh-CN";
                    }}

                    function renderRichText(value) {{
                        const content = String(value || "").trim();
                        if (!content) return "<p>—</p>";
                        if (/^(\\s*[-*+]\\s+|\\s*\\d+[.)]\\s+)/m.test(content)) {{
                            return (window.marked && typeof window.marked.parse === "function")
                                ? window.marked.parse(content)
                                : `<pre>${{content}}</pre>`;
                        }}
                        const lines = content.split("\\n").map((x) => x.trim()).filter(Boolean);
                        if (lines.length >= 2) {{
                            return `<ul>${{lines.map((line) => `<li>${{(window.marked && typeof window.marked.parse === "function") ? window.marked.parseInline(line) : line}}</li>`).join("")}}</ul>`;
                        }}
                        const numbered = content
                            .split(/(?:^|\\s)(?:\\d+[.)]|[A-Da-d][.)])\\s+/)
                            .map((x) => x.trim())
                            .filter(Boolean);
                        if (numbered.length >= 2) {{
                            return `<ul>${{numbered.map((part) => `<li>${{(window.marked && typeof window.marked.parse === "function") ? window.marked.parseInline(part) : part}}</li>`).join("")}}</ul>`;
                        }}
                        const semis = content.split(/\\s*[;；]\\s+/).map((x) => x.trim()).filter(Boolean);
                        if (semis.length >= 2) {{
                            return `<ul>${{semis.map((part) => `<li>${{(window.marked && typeof window.marked.parse === "function") ? window.marked.parseInline(part) : part}}</li>`).join("")}}</ul>`;
                        }}
                        return (window.marked && typeof window.marked.parse === "function")
                            ? window.marked.parse(content)
                            : `<pre>${{content}}</pre>`;
                    }}

                    function escapeHtml(value) {{
                        return String(value ?? "")
                            .replace(/&/g, "&amp;")
                            .replace(/</g, "&lt;")
                            .replace(/>/g, "&gt;")
                            .replace(/\"/g, "&quot;")
                            .replace(/'/g, "&#39;");
                    }}

                    function formatStoryArray(value) {{
                        if (!Array.isArray(value) || !value.length) {{
                            return "<p>—</p>";
                        }}
                        function formatEntry(entry) {{
                            if (entry === null || entry === undefined) {{
                                return "—";
                            }}
                            if (typeof entry === "string" || typeof entry === "number" || typeof entry === "boolean") {{
                                return renderRichText(String(entry));
                            }}
                            if (Array.isArray(entry)) {{
                                return `<ul>${{entry.map((row) => `<li>${{formatEntry(row)}}</li>`).join("")}}</ul>`;
                            }}
                            if (typeof entry === "object") {{
                                const title = entry.title || entry.news_title || entry.headline || entry.label || entry.key || entry.scenario || "";
                                const date = entry.date || entry.news_date_time || entry.report_date || entry.as_of_date || "";
                                const source = entry.source || entry.news_source || entry.provider || "";
                                const link = entry.url || entry.news_source_link || entry.link || "";
                                const summary = entry.summary || entry.note || entry.change || entry.text || entry.impact || "";
                                if (title || date || source || link || summary) {{
                                    const top = [
                                        title ? `<strong>${{escapeHtml(String(title))}}</strong>` : "",
                                        date ? escapeHtml(String(date)) : "",
                                        source ? escapeHtml(String(source)) : "",
                                    ].filter(Boolean).join(" · ");
                                    const linkHtml = link
                                        ? `<div><a href="${{escapeHtml(String(link))}}" target="_blank" rel="noopener noreferrer">${{escapeHtml(String(link))}}</a></div>`
                                        : "";
                                    const summaryHtml = summary
                                        ? `<div>${{renderRichText(String(summary))}}</div>`
                                        : "";
                                    return `<div>${{top || "Item"}}${{linkHtml}}${{summaryHtml}}</div>`;
                                }}
                                return `<pre>${{escapeHtml(JSON.stringify(entry, null, 2))}}</pre>`;
                            }}
                            return escapeHtml(String(entry));
                        }}
                        return `<ul>${{value.map((entry) => `<li>${{formatEntry(entry)}}</li>`).join("")}}</ul>`;
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

                    function isToday(dateText) {{
                        const today = localDateText();
                        return String(dateText || "") === today;
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
                            container.innerHTML = '<p class="status">No data available.</p>';
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
                                    <h3>${{item.label}}</h3>
                                    <div class="symbol">${{item.symbol || "—"}}</div>
                                    ${{item.country_code ? `<div class="country">Country: ${{item.country_code}}</div>` : ""}}
                                    <div class="price">${{item.close_price || "—"}}</div>
                                    <div class="change ${{changeClass}}">Change: ${{pctText}}</div>
                                    ${{headlineHtml}}
                                </div>
                            `;
                        }}).join("");
                    }}

                    function renderMarketSections(sections) {{
                        if (!marketSectionsEl) return;
                        if (!sections || !sections.length) {{
                            marketSectionsEl.innerHTML = '<p class="status">No price snapshot available for this date.</p>';
                            return;
                        }}
                        marketSectionsEl.innerHTML = sections.map((section, idx) => `
                            <section class="market-overview-section" data-section-key="${{section.key || idx}}">
                                <h2 class="market-overview-section-title">${{section.label || section.key || "Section"}}</h2>
                                <div class="market-grid" id="market-grid-${{idx}}"></div>
                            </section>
                        `).join("");
                        sections.forEach((section, idx) => {{
                            const grid = document.getElementById(`market-grid-${{idx}}`);
                            renderItems(grid, section.items || []);
                        }});
                    }}

                    function renderNews(items) {{
                        const container = document.getElementById("market-news");
                        if (!container) return;
                        if (!items || !items.length) {{
                            container.innerHTML = '<p class="status">No market news available.</p>';
                            return;
                        }}
                        const defaultModel = {default_openai_model_json};
                        const deriveTag = (item) => {{
                            const explicit = String(item.source_tag || "").trim().toLowerCase();
                            if (explicit.includes("yahoo")) return "yahoo";
                            if (explicit.includes("finnhub")) return "finnhub";
                            const source = String(item.source || "").toLowerCase();
                            if (source.includes("yahoo")) return "yahoo";
                            if (source.includes("finnhub")) return "finnhub";
                            return "";
                        }};
                        const modelOptionsHtml = (selectedModel) => {{
                            const current = String(selectedModel || defaultModel);
                            return singleNewsModels.map((choice) => {{
                                const model = String(choice.model || "");
                                const provider = String(choice.provider || "");
                                const selectedAttr = model === current ? "selected" : "";
                                return `<option value="${{model}}" data-provider="${{provider}}" ${{selectedAttr}}>${{provider}} · ${{model}}</option>`;
                            }}).join("");
                        }};
                        container.innerHTML = items.map((item) => `
                            <div class="news-item" data-news-url="${{item.url || ''}}">
                                ${{deriveTag(item) ? `<span class="news-tag">${{deriveTag(item)}}</span>` : ""}}
                                <a href="${{item.url}}" target="_blank" rel="noopener noreferrer">${{item.headline}}</a>
                                <div class="news-meta">${{item.source || "Unknown source"}} · ${{item.datetime_text || ""}}</div>
                                <div class="news-actions">
                                    <select class="news-model-picker">
                                        ${{modelOptionsHtml(defaultModel)}}
                                    </select>
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
                                if (event.target.closest("a")) return;
                                if (event.target.closest("button")) return;
                                if (event.target.closest("select")) return;
                                card.classList.toggle("expanded");
                            }});
                        }});

                        container.querySelectorAll(".news-analyze-btn").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = button.closest(".news-item");
                                if (!card) return;
                                const modelPicker = card.querySelector(".news-model-picker");
                                const selectedModel = modelPicker && modelPicker.value
                                    ? String(modelPicker.value)
                                    : defaultModel;
                                const url = card.getAttribute("data-news-url") || "";
                                const item = (items || []).find((row) => String(row.url || "") === String(url));
                                if (!item) return;
                                button.disabled = true;
                                button.textContent = "Analyzing...";
                                try {{
                                    const response = await fetch(
                                        `/api/market/news/item-analyze?model=${{encodeURIComponent(selectedModel)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`,
                                        {{
                                            method: "POST",
                                            headers: {{ "Content-Type": "application/json" }},
                                            body: JSON.stringify({{ date: selectedDate, item }}),
                                        }}
                                    );
                                    const payload = await response.json();
                                    if (!response.ok || payload.error) {{
                                        alert(payload.error || "Analyze failed");
                                        return;
                                    }}
                                    const analysis = payload.analysis || null;
                                    if (analysis) {{
                                        const meta = card.querySelector(".news-analysis-meta");
                                        const text = card.querySelector(".news-analysis-text");
                                        if (meta) {{
                                            meta.textContent = `provider=${{analysis.provider}} · model=${{analysis.model}} · lang=${{analysis.output_language}} · updated=${{analysis.updated_at}}`;
                                        }}
                                        if (text) {{
                                            text.innerHTML = renderRichText(analysis.output_text || "");
                                        }}
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
                                await fetch(`/api/market/stories/create-from-news?prompt_style=${{encodeURIComponent(summaryPrompt ? summaryPrompt.value || "simple" : "simple")}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{
                                    method: "POST",
                                    headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ date: selectedDate, story_title: storyTitle, item }}),
                                }});
                                await loadMarketStories(false);
                            }});
                        }});

                        container.querySelectorAll(".news-attach-story-btn").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
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
                                await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/attach-news?prompt_style=${{encodeURIComponent(summaryPrompt ? summaryPrompt.value || "simple" : "simple")}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`, {{
                                    method: "POST",
                                    headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ date: selectedDate, item }}),
                                }});
                                const inline = card.querySelector(".attach-story-inline");
                                if (inline) inline.classList.remove("active");
                                await loadMarketStories(false);
                            }});
                        }});

                        container.querySelectorAll(".news-model-picker").forEach((picker) => {{
                            picker.addEventListener("change", async (event) => {{
                                event.stopPropagation();
                                const model = picker.value ? String(picker.value) : defaultModel;
                                const card = picker.closest(".news-item");
                                if (!card) return;
                                const url = card.getAttribute("data-news-url") || "";
                                try {{
                                    const response = await fetch(
                                        `/api/market/news/item-analyses?date=${{encodeURIComponent(selectedDate)}}&model=${{encodeURIComponent(model)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`
                                    );
                                    const payload = await response.json();
                                    const analyses = payload.analyses || [];
                                    const found = analyses.find((row) => String(row.news_url || "") === String(url));
                                    const meta = card.querySelector(".news-analysis-meta");
                                    const text = card.querySelector(".news-analysis-text");
                                    if (!found) {{
                                        if (meta) meta.textContent = "";
                                        if (text) text.textContent = "";
                                        return;
                                    }}
                                    if (meta) {{
                                        meta.textContent = `provider=${{found.provider}} · model=${{found.model}} · lang=${{found.output_language}} · updated=${{found.updated_at}}`;
                                    }}
                                    if (text) {{
                                        text.innerHTML = renderRichText(found.output_text || "");
                                    }}
                                    card.classList.add("expanded");
                                }} catch (_error) {{
                                    // no-op
                                }}
                            }});
                        }});

                        loadExistingItemAnalyses(items, defaultModel);
                    }}

                    async function loadExistingItemAnalyses(items, model) {{
                        try {{
                            const response = await fetch(
                                `/api/market/news/item-analyses?date=${{encodeURIComponent(selectedDate)}}&model=${{encodeURIComponent(model)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`
                            );
                            const payload = await response.json();
                            const analyses = payload.analyses || [];
                            if (!analyses.length) return;
                            const byUrl = new Map(analyses.map((row) => [String(row.news_url || ""), row]));
                            const container = document.getElementById("market-news");
                            if (!container) return;
                            container.querySelectorAll(".news-item").forEach((card) => {{
                                const url = card.getAttribute("data-news-url") || "";
                                const found = byUrl.get(String(url));
                                if (!found) return;
                                const meta = card.querySelector(".news-analysis-meta");
                                const text = card.querySelector(".news-analysis-text");
                                if (meta) {{
                                    meta.textContent = `provider=${{found.provider}} · model=${{found.model}} · lang=${{found.output_language}} · updated=${{found.updated_at}}`;
                                }}
                                if (text) {{
                                    text.innerHTML = renderRichText(found.output_text || "");
                                }}
                                card.classList.add("expanded");
                            }});
                        }} catch (_error) {{
                            // no-op
                        }}
                    }}

                    function renderSummaryHistory(items) {{
                        if (!summariesEl) return;
                        if (!items || !items.length) {{
                            summariesEl.innerHTML = '<p class="status">No market summary yet for today.</p>';
                            return;
                        }}
                        summariesEl.innerHTML = items.map((item) => `
                            <div class="summary-card">
                                <div class="news-meta">
                                    ${{item.created_at || ""}} · provider=${{item.provider}} · model=${{item.model}} · prompt=${{item.prompt_style}}
                                    ${{item.news_sources ? ` · sources=${{item.news_sources}}` : ""}}
                                </div>
                                <div class="summary-output">${{renderRichText(item.output_text || "")}}</div>
                            </div>
                        `).join("");
                    }}

                    function renderDailyClusters(items) {{
                        if (!marketDailyClustersEl) return;
                        if (!items || !items.length) {{
                            marketDailyClustersEl.innerHTML = '<p class="status">No daily clusters yet for this date.</p>';
                            return;
                        }}
                        marketDailyClustersEl.innerHTML = `
                            <section class="card" style="padding:1rem; margin-bottom:0.85rem;">
                                <h3 style="margin:0 0 0.55rem;">Daily Clusters</h3>
                                <div class="story-group">
                                    ${{items.map((item) => `
                                        <div class="story-card">
                                            <h3>${{item.cluster_title || "Cluster"}}</h3>
                                            <div>${{renderRichText(item.cluster_summary || "")}}</div>
                                        </div>
                                    `).join("")}}
                                </div>
                            </section>
                        `;
                    }}

                    async function loadSummaryHistory() {{
                        try {{
                            const response = await fetch(`/api/market/news/summaries?date=${{encodeURIComponent(selectedDate)}}`);
                            const payload = await response.json();
                            const summaries = payload.summaries || [];
                            renderSummaryHistory(summaries);
                            return summaries;
                        }} catch (_error) {{
                            renderSummaryHistory([]);
                            return [];
                        }}
                    }}

                    async function loadDailyNews(refresh = false) {{
                        if (refreshDailyNewsBtn) {{
                            refreshDailyNewsBtn.disabled = true;
                            refreshDailyNewsBtn.textContent = refresh ? "Refreshing..." : "Refresh Daily News";
                        }}
                        if (summaryStatus) {{
                            summaryStatus.textContent = refresh ? "Refreshing daily news..." : "Loading...";
                        }}
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
                                summaryStatus.textContent = `${{count}} item${{count === 1 ? "" : "s"}}${{refresh ? " · updated" : ""}}`;
                            }}
                        }} catch (error) {{
                            if (summaryStatus) summaryStatus.textContent = "Refresh failed";
                            console.error(error);
                        }} finally {{
                            if (refreshDailyNewsBtn) {{
                                refreshDailyNewsBtn.disabled = false;
                                refreshDailyNewsBtn.textContent = "Refresh Daily News";
                            }}
                        }}
                    }}

                    async function ensureDailyNewsLoaded() {{
                        const lang = getOutputLanguage();
                        const key = `${{selectedDate}}|simple|${{lang}}`;
                        await loadDailyNews(false);
                        const hasStoredDailyNews = Array.isArray(latestNews) && latestNews.length > 0;
                        const hasStoredSummaries = summariesEl && summariesEl.querySelector(".summary-card");
                        const hasStoredClusters = marketDailyClustersEl && marketDailyClustersEl.querySelector(".story-card");
                        if (hasStoredDailyNews || hasStoredSummaries || hasStoredClusters) {{
                            dailyNewsAutoInitializedKey = key;
                            return;
                        }}
                        if (dailyNewsAutoInitializedKey === key) {{
                            return;
                        }}
                        dailyNewsAutoInitializedKey = key;
                        await loadDailyNews(true);
                    }}

                    async function refreshMarket() {{
                        const started = Date.now();
                        refreshBtn.disabled = true;
                        refreshBtn.textContent = "Refreshing...";
                        try {{
                            const response = await fetch(`/api/market/overview?date=${{encodeURIComponent(selectedDate)}}`);
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                statusEl.textContent = payload.error || "Failed to refresh";
                                return;
                            }}
                            renderMarketSections(payload.sections || []);
                            const elapsedSec = ((Date.now() - started) / 1000).toFixed(1);
                            const priceSource = payload.price_data_source ? ` · prices=${{payload.price_data_source}}` : "";
                            const priceDateText = payload.price_date && payload.price_date !== (payload.date || selectedDate)
                                ? ` · price_date=${{payload.price_date}}`
                                : "";
                            statusEl.textContent = `Date ${{payload.date || selectedDate}}${{priceDateText}} · Updated ${{payload.updated_at || ""}} (${{elapsedSec}}s)${{priceSource}}`;
                        }} catch (error) {{
                            statusEl.textContent = "Failed to refresh";
                            console.error(error);
                        }} finally {{
                            refreshBtn.disabled = false;
                            refreshBtn.textContent = "Refresh";
                        }}
                    }}

                    function setMarketView(mode) {{
                        currentMarketView = ["overview", "daily-news", "stories"].includes(mode) ? mode : "overview";
                        document.querySelectorAll(".market-subview").forEach((el) => {{
                            el.classList.toggle("active", el.id === `market-${{currentMarketView}}-view`);
                        }});
                        if (marketViewTabs) {{
                            marketViewTabs.querySelectorAll(".subtab-btn").forEach((btn) => {{
                                btn.classList.toggle("active", btn.dataset.marketView === currentMarketView);
                            }});
                        }}
                    }}

                    function buildMarketTimeline(story) {{
                        const timelineItems = Array.isArray(story.timeline_items) ? story.timeline_items.filter((item) => item && typeof item === "object") : [];
                        if (timelineItems.length) {{
                            return timelineItems;
                        }}
                        const fallback = [];
                        if (story.happened_text) {{
                            fallback.push({{ label: "Earlier", summary: story.happened_text }});
                        }}
                        if (story.happening_text) {{
                            fallback.push({{ label: "Current", summary: story.happening_text }});
                        }}
                        return fallback;
                    }}

                    function buildMarketFuture(story) {{
                        const futureItems = Array.isArray(story.future_and_impact) ? story.future_and_impact.filter((item) => item && typeof item === "object") : [];
                        if (futureItems.length) {{
                            return futureItems;
                        }}
                        if (story.next_text) {{
                            return [{{ scenario: story.next_text }}];
                        }}
                        return [];
                    }}

                    function renderMarketStoryGroup(title, stories) {{
                        if (!Array.isArray(stories) || !stories.length) {{
                            return "";
                        }}
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
                        if (!story) {{
                            return '<p class="placeholder">Select a story to see details.</p>';
                        }}
                        const summaryText = String(
                            story.story_summary
                            || story.happening_text
                            || story.happened_text
                            || story.next_text
                            || ""
                        ).trim();
                        const timelineRows = formatStoryArray(buildMarketTimeline(story));
                        const futureRows = formatStoryArray(buildMarketFuture(story));
                        const isClosed = ["finished", "resolved", "closed"].includes(String(story.story_status || "").toLowerCase());
                        return `
                            <div class="story-detail-section">
                                <h3>${{escapeHtml(story.story_title || "")}}</h3>
                                <div class="story-item-meta">status=${{escapeHtml(story.story_status || "ongoing")}} · priority=${{escapeHtml(story.priority || "normal")}} · updated=${{escapeHtml(story.updated_at || "")}}</div>
                                <div class="story-detail-box">${{renderRichText(summaryText || "—")}}</div>
                                <div class="summary-controls" style="margin-top:0.6rem;">
                                    <button class="story-close-btn" type="button" data-story-key="${{story.story_key}}">${{isClosed ? "Reopen Story" : "Close Story"}}</button>
                                    <button class="story-priority-btn" type="button" data-story-key="${{story.story_key}}" data-priority="${{story.priority === 'high' ? 'normal' : 'high'}}">${{story.priority === 'high' ? 'Set Normal Priority' : 'Set High Priority'}}</button>
                                </div>
                            </div>
                            <div class="story-detail-section">
                                <h3>Timeline</h3>
                                <div class="story-detail-box">${{timelineRows}}</div>
                            </div>
                            <div class="story-detail-section">
                                <h3>Future and Impact</h3>
                                <div class="story-detail-box">${{futureRows}}</div>
                            </div>
                            <div class="story-detail-section">
                                <h3>Evidence</h3>
                                <div class="story-detail-box">${{formatStoryArray(story.evidence || [])}}</div>
                            </div>
                            <div class="story-detail-section">
                                <h3>Recent Changes</h3>
                                <div class="story-detail-box">${{formatStoryArray(story.change_log || [])}}</div>
                            </div>
                        `;
                    }}

                    async function loadMarketStories(refresh = false) {{
                        if (marketStoriesStatus) {{
                            marketStoriesStatus.textContent = refresh ? "Refreshing..." : "Loading...";
                        }}
                        const prompt = "simple";
                        const lang = getOutputLanguage();
                        const endpoint = refresh
                            ? `/api/market/stories/refresh?prompt_style=${{encodeURIComponent(prompt)}}&output_language=${{encodeURIComponent(lang)}}&date=${{encodeURIComponent(selectedDate)}}`
                            : `/api/market/stories?prompt_style=${{encodeURIComponent(prompt)}}&output_language=${{encodeURIComponent(lang)}}`;
                        const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                        const payload = await response.json();
                        const warmup = payload.warmup || {{}};
                        const parts = [];
                        if (warmup.job_state) parts.push(`state=${{warmup.job_state}}`);
                        if (warmup.current_stage) parts.push(`stage=${{warmup.current_stage}}`);
                        if (Number(warmup.raw_stored_count || 0)) parts.push(`${{warmup.raw_stored_count}} raw news`);
                        if (Number(warmup.ongoing_story_count || 0) || Number(warmup.finished_story_count || 0)) {{
                            parts.push(`${{warmup.ongoing_story_count || 0}} ongoing`);
                            parts.push(`${{warmup.finished_story_count || 0}} finished`);
                        }}
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
                                    if (marketStoryDetailEl) {{
                                        marketStoryDetailEl.innerHTML = renderMarketStoryDetail(activeStory);
                                        bindMarketStoryDetailActions();
                                    }}
                                }});
                            }});
                        }}
                        if (marketStoryDetailEl) {{
                            const activeStory = latestStoryOptions.find((story) => story.story_key === activeMarketStoryKey) || null;
                            marketStoryDetailEl.innerHTML = renderMarketStoryDetail(activeStory);
                        }}

                        function bindMarketStoryDetailActions() {{
                            document.querySelectorAll(".story-close-btn").forEach((button) => {{
                                button.addEventListener("click", async () => {{
                                    const storyKey = button.getAttribute("data-story-key") || "";
                                    const nextAction = String(button.textContent || "").toLowerCase().includes("reopen") ? "reopen" : "close";
                                    await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/${{nextAction}}?prompt_style=${{encodeURIComponent(prompt)}}&output_language=${{encodeURIComponent(lang)}}`, {{ method: "POST" }});
                                    await loadMarketStories(false);
                                }});
                            }});
                            document.querySelectorAll(".story-priority-btn").forEach((button) => {{
                                button.addEventListener("click", async () => {{
                                    const storyKey = button.getAttribute("data-story-key") || "";
                                    const priority = button.getAttribute("data-priority") || "high";
                                    await fetch(`/api/market/stories/${{encodeURIComponent(storyKey)}}/priority?priority=${{encodeURIComponent(priority)}}&prompt_style=${{encodeURIComponent(prompt)}}&output_language=${{encodeURIComponent(lang)}}`, {{ method: "POST" }});
                                    await loadMarketStories(false);
                                }});
                            }});
                        }}

                        bindMarketStoryDetailActions();
                        if (marketStoriesStatus) marketStoriesStatus.textContent = refresh ? "Updated" : "";
                    }}

                    async function ensureMarketStoriesLoaded() {{
                        const prompt = "simple";
                        const lang = getOutputLanguage();
                        const key = `${{selectedDate}}|${{prompt}}|${{lang}}`;
                        await loadMarketStories(false);
                        const hasStories = latestStoryOptions && latestStoryOptions.length > 0;
                        if (hasStories) {{
                            marketStoriesAutoInitializedKey = key;
                            return;
                        }}
                        if (marketStoriesAutoInitializedKey === key) {{
                            return;
                        }}
                        marketStoriesAutoInitializedKey = key;
                        await loadMarketStories(true);
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
                        const dayMap = {{
                            Mon: 1,
                            Tue: 2,
                            Wed: 3,
                            Thu: 4,
                            Fri: 5,
                            Sat: 6,
                            Sun: 7,
                        }};
                        const dayNum = dayMap[weekday] || 0;
                        if (dayNum < 1 || dayNum > 5) {{
                            return false;
                        }}
                        const minutesFromMidnight = hour * 60 + minute;
                        const openMinutes = 9 * 60 + 30;
                        const closeMinutes = 16 * 60;
                        return minutesFromMidnight >= openMinutes && minutesFromMidnight <= closeMinutes;
                    }}

                    async function loadSummaryDates() {{
                        try {{
                            const response = await fetch("/api/market/news/summary-dates?lookback_days=365");
                            const payload = await response.json();
                            const rows = payload.dates || [];
                            reportDateSet = new Set(rows.map((row) => String(row.date || "")));
                            datePickers.forEach((picker) => {{
                                if (picker && typeof picker.redraw === "function") {{
                                    picker.redraw();
                                }}
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
                            if (picker && typeof picker.setDate === "function") {{
                                picker.setDate(selectedDate, false);
                            }}
                        }});
                        updateUrlState();
                        await refreshMarket();
                        if (currentMarketView === "daily-news") {{
                            await ensureDailyNewsLoaded();
                        }} else if (currentMarketView === "stories") {{
                            await ensureMarketStoriesLoaded();
                        }}
                    }}

                    if (refreshDailyNewsBtn) {{
                        refreshDailyNewsBtn.addEventListener("click", () => loadDailyNews(true));
                    }}
                    if (marketViewTabs) {{
                        marketViewTabs.querySelectorAll(".subtab-btn").forEach((btn) => {{
                            btn.addEventListener("click", async () => {{
                                const next = btn.dataset.marketView || "overview";
                                setMarketView(next);
                                if (next === "daily-news") {{
                                    await ensureDailyNewsLoaded();
                                }} else if (next === "stories") {{
                                    await ensureMarketStoriesLoaded();
                                }}
                            }});
                        }});
                    }}
                    const refreshStoriesBtn = document.getElementById("refresh-market-stories");
                    if (refreshStoriesBtn) {{
                        refreshStoriesBtn.addEventListener("click", async () => {{
                            await loadMarketStories(true);
                        }});
                    }}
                    initOutputLanguage();
                    refreshBtn.addEventListener("click", refreshMarket);
                    if (window.flatpickr && dateInputs.length) {{
                        dateInputs.forEach((input) => {{
                            const picker = window.flatpickr(input, {{
                                dateFormat: "Y-m-d",
                                defaultDate: selectedDate,
                                maxDate: "today",
                                onDayCreate: function(_dObj, _dStr, _fp, dayElem) {{
                                    const dateText = dayElem.dateObj.toISOString().slice(0, 10);
                                    if (reportDateSet.has(dateText)) {{
                                        dayElem.classList.add("has-report");
                                    }}
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
                    Promise.all([loadSummaryDates(), refreshMarket()]).then(async () => {{
                        updateUrlState();
                    }});
                    setMarketView("overview");
                    setInterval(() => {{
                        if (!isUsMarketHoursNow()) {{
                            return;
                        }}
                        if (!isToday(selectedDate)) {{
                            return;
                        }}
                        refreshMarket();
                    }}, 60000);
                </script>
            </body>
        </html>
    """
