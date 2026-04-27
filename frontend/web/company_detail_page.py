"""Company detail page rendering."""

from __future__ import annotations

import json

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from frontend.web.stock_chart_shared import (
    STOCK_CHART_RANGE_KEYS,
    render_shared_stock_chart_assets,
    render_stock_range_buttons_html,
)
from market_agent.config.models import DEFAULT_COMPANY_OPENAI_MODEL, DEFAULT_OPENAI_MODEL
from market_agent.datasources.finnhub import list_news_sources


def render_company_detail_page(
    company_name: str,
    *,
    model_choices_by_provider: dict[str, list[str]] | None = None,
    indicator_models: list[str] | None = None,
    default_company_model: str | None = None,
) -> str:
    safe_company = company_name.replace('"', "")
    display_company = (
        safe_company[:1].upper() + safe_company[1:] if safe_company else safe_company
    )
    source_options = "".join(
        f'<option value="{source}">{source}</option>'
        for source in list_news_sources()
        if source != "openai"
    )
    flat_models: list[dict[str, str]] = []
    for provider, models in (model_choices_by_provider or {}).items():
        for model in models:
            flat_models.append({"provider": str(provider), "model": str(model)})
    company_models = list((model_choices_by_provider or {}).get("openai") or [])
    selected_company_model = str(default_company_model or DEFAULT_COMPANY_OPENAI_MODEL)
    if selected_company_model not in company_models:
        company_models.append(selected_company_model)
    model_choices_json = json.dumps(flat_models, ensure_ascii=False)
    company_model_choices_json = json.dumps(company_models, ensure_ascii=False)
    indicator_models_json = json.dumps(indicator_models or [], ensure_ascii=False)
    default_openai_model_json = json.dumps(DEFAULT_OPENAI_MODEL, ensure_ascii=False)
    default_company_model_json = json.dumps(selected_company_model, ensure_ascii=False)
    shared_chart_assets = render_shared_stock_chart_assets()
    stock_range_buttons_html = render_stock_range_buttons_html()
    stock_range_keys_json = json.dumps(list(STOCK_CHART_RANGE_KEYS), ensure_ascii=False)
    return f"""
        <html>
            <head>
                <title>MarketAgent – {display_company}</title>
                <link
                    rel="stylesheet"
                    href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css"
                />
                <style>
                    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap");
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
                    .view-tabs {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.35rem;
                        margin: 0.2rem 0 1rem;
                    }}
                    .view-tab {{
                        border: 1px solid #d1d5db;
                        background: #ffffff;
                        color: #334155;
                        border-radius: 999px;
                        padding: 0.3rem 0.65rem;
                        font-size: 0.78rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .view-tab.active {{
                        background: #0f172a;
                        border-color: #0f172a;
                        color: #ffffff;
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
                    .daily-report-card {{
                        border: 1px solid #dbeafe;
                        background: #f8fbff;
                        border-radius: 0.9rem;
                        padding: 0.85rem 0.95rem;
                        margin-bottom: 0.9rem;
                    }}
                    .daily-report-card .daily-report-meta {{
                        font-size: 0.78rem;
                        color: #64748b;
                        margin-bottom: 0.35rem;
                    }}
                    .daily-report-card .daily-report-output {{
                        line-height: 1.28;
                        font-size: 0.92rem;
                        white-space: pre-wrap;
                        overflow-wrap: anywhere;
                    }}
                    .daily-report-card .daily-report-output p {{
                        margin: 0 0 0.2rem;
                    }}
                    .daily-report-card .daily-report-output h1 {{
                        margin: 0.55rem 0 0.2rem;
                        line-height: 1.18;
                        font-size: 1.18rem;
                    }}
                    .daily-report-card .daily-report-output h2,
                    .daily-report-card .daily-report-output h3,
                    .daily-report-card .daily-report-output h4 {{
                        margin: 0.35rem 0 0.12rem;
                        line-height: 1.15;
                        font-size: 0.98rem;
                    }}
                    .daily-report-card .daily-report-output ul,
                    .daily-report-card .daily-report-output ol {{
                        margin: 0.05rem 0 0.2rem;
                        padding-left: 1.15rem;
                    }}
                    .daily-report-card .daily-report-output li {{
                        margin-bottom: 0.12rem;
                    }}
                    .daily-report-card .daily-report-output hr {{
                        margin: 0.45rem 0;
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
                    .day-analyze-prompt {{
                        width: 124px;
                        min-width: 124px;
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
                        width: 200px;
                        min-width: 200px;
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
                        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
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
                    .stock-history-item {{
                        margin-bottom: 0.75rem;
                        border: 1px solid rgba(15, 23, 42, 0.08);
                        border-radius: 0.9rem;
                        background: #fffaf0;
                        box-shadow: none;
                        overflow: hidden;
                    }}
                    .stock-history-item.active {{
                        border-color: rgba(37, 99, 235, 0.45);
                        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08);
                    }}
                    .stock-history-summary {{
                        list-style: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        padding: 0.8rem 0.95rem;
                        color: var(--ink);
                        font-size: 0.95rem;
                        font-weight: 600;
                    }}
                    .stock-history-summary::-webkit-details-marker {{ display: none; }}
                    .stock-history-summary::after {{
                        content: "Expand";
                        flex: 0 0 auto;
                        font-size: 0.78rem;
                        font-weight: 500;
                        color: #64748b;
                    }}
                    .stock-history-item[open] .stock-history-summary::after {{ content: "Collapse"; }}
                    .stock-history-position {{
                        color: #1d4ed8;
                        font-size: 0.85rem;
                        font-weight: 600;
                        white-space: nowrap;
                    }}
                    .stock-history-body {{
                        padding: 0 0.95rem 0.9rem;
                        border-top: 1px solid rgba(15, 23, 42, 0.08);
                    }}
                    .stock-history-body .news-meta {{
                        margin-top: 0.7rem;
                    }}
                    .stock-history-body .news-summary {{
                        margin-top: 0.55rem;
                        color: #334155;
                        line-height: 1.5;
                    }}
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
                    .news-field pre {{
                        margin: 0.35rem 0 0;
                        padding: 0.55rem 0.65rem;
                        border-radius: 0.55rem;
                        border: 1px solid #e5e7eb;
                        background: #f8fafc;
                        font-size: 0.78rem;
                        line-height: 1.35;
                        white-space: pre-wrap;
                        overflow-wrap: anywhere;
                    }}
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
                    .status-panel {{
                        border: 1px solid #dbeafe;
                        background: #f8fbff;
                        border-radius: 1rem;
                        padding: 0.95rem;
                        box-shadow: var(--card-shadow);
                    }}
                    .status-panel-header {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 0.75rem;
                        flex-wrap: wrap;
                        margin-bottom: 0.65rem;
                    }}
                    .status-header-main {{
                        flex: 1 1 320px;
                        min-width: 0;
                    }}
                    .status-controls {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                        justify-content: flex-end;
                        margin-left: auto;
                    }}
                    .status-select {{
                        height: 30px;
                        border: 1px solid #d1d5db;
                        border-radius: 0.5rem;
                        padding: 0.2rem 0.45rem;
                        font-size: 0.8rem;
                        background: #fff;
                    }}
                    .status-btn {{
                        border: 1px solid #2563eb;
                        background: #2563eb;
                        color: #fff;
                        border-radius: 999px;
                        padding: 0.35rem 0.7rem;
                        font-size: 0.78rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .status-btn:hover {{ background: #1d4ed8; border-color: #1d4ed8; }}
                    .status-meta {{
                        color: #64748b;
                        font-size: 0.8rem;
                        margin-bottom: 0.55rem;
                    }}
                    .status-output {{
                        overflow-wrap: anywhere;
                        line-height: 1.65;
                        font-size: 0.92rem;
                    }}
                    .status-output p {{
                        margin: 0.35rem 0 0.5rem;
                    }}
                    .status-output h1,
                    .status-output h2,
                    .status-output h3,
                    .status-output h4 {{
                        margin: 0.6rem 0 0.4rem;
                        line-height: 1.35;
                    }}
                    .status-output ul,
                    .status-output ol {{
                        margin: 0.35rem 0 0.55rem;
                        padding-left: 1.2rem;
                    }}
                    .status-output li {{
                        margin: 0.18rem 0;
                    }}
                    .status-output pre {{
                        margin: 0.45rem 0;
                        padding: 0.55rem 0.65rem;
                        border-radius: 0.55rem;
                        border: 1px solid #e5e7eb;
                        background: #f8fafc;
                        overflow-x: auto;
                    }}
                    .status-output code {{
                        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
                        font-size: 0.84em;
                    }}
                    .status-output pre code {{
                        font-size: 0.78rem;
                        line-height: 1.35;
                        white-space: pre;
                    }}
                    .status-output blockquote {{
                        margin: 0.45rem 0;
                        padding: 0.35rem 0.7rem;
                        border-left: 3px solid #cbd5e1;
                        color: #334155;
                        background: #f8fafc;
                    }}
                    .stories-wrap {{
                        display: grid;
                        grid-template-columns: 280px 1fr;
                        gap: 0.8rem;
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
                    }}
                    .story-ask-wrap {{
                        margin-top: 0.75rem;
                        display: grid;
                        gap: 0.45rem;
                    }}
                    .story-ask-controls {{
                        display: flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                    }}
                    .story-ask-model {{
                        min-width: 180px;
                        height: 30px;
                        border: 1px solid #d1d5db;
                        border-radius: 0.5rem;
                        padding: 0.2rem 0.45rem;
                        font-size: 0.8rem;
                        background: #fff;
                    }}
                    .story-ask-input {{
                        width: 100%;
                        min-height: 70px;
                        border: 1px solid #d1d5db;
                        border-radius: 0.55rem;
                        padding: 0.45rem 0.55rem;
                        font-size: 0.86rem;
                        background: #fff;
                    }}
                    .story-ask-btn {{
                        width: fit-content;
                        border: 1px solid #0f766e;
                        background: #0f766e;
                        color: #fff;
                        border-radius: 999px;
                        padding: 0.35rem 0.72rem;
                        font-size: 0.78rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .story-ask-log {{
                        margin-top: 0.65rem;
                        display: grid;
                        gap: 0.5rem;
                    }}
                    .story-ask-row {{
                        border: 1px solid #e5e7eb;
                        background: #fff;
                        border-radius: 0.6rem;
                        padding: 0.5rem 0.6rem;
                    }}
                    .story-ask-meta {{
                        font-size: 0.74rem;
                        color: #64748b;
                        margin-bottom: 0.2rem;
                    }}
                    .story-ask-actions {{
                        display: flex;
                        align-items: center;
                        gap: 0.4rem;
                        margin-top: 0.35rem;
                    }}
                    .story-merge-btn {{
                        width: fit-content;
                        border: 1px solid #2563eb;
                        background: #eff6ff;
                        color: #1d4ed8;
                        border-radius: 999px;
                        padding: 0.28rem 0.65rem;
                        font-size: 0.76rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .story-merge-btn:hover {{
                        background: #dbeafe;
                    }}
                    @media (max-width: 980px) {{
                        .stories-wrap {{
                            grid-template-columns: 1fr;
                        }}
                    }}
                    .stock-panel {{
                        border: 1px solid #dbeafe;
                        border-radius: 1rem;
                        background: #f8fbff;
                        padding: 0.85rem;
                        box-shadow: var(--card-shadow);
                    }}
                    .stock-controls {{
                        display: flex;
                        align-items: center;
                        gap: 0.5rem;
                        flex-wrap: wrap;
                        margin-bottom: 0.9rem;
                    }}
                    .stock-range-btn {{
                        border: 1px solid #cbd5e1;
                        border-radius: 999px;
                        padding: 0.28rem 0.62rem;
                        background: #fff;
                        color: #334155;
                        font-size: 0.76rem;
                        font-weight: 700;
                        cursor: pointer;
                    }}
                    .stock-range-btn.active {{
                        background: #0f172a;
                        border-color: #0f172a;
                        color: #fff;
                    }}
                    .stock-select {{
                        height: 30px;
                        border: 1px solid #d1d5db;
                        border-radius: 0.5rem;
                        padding: 0.2rem 0.45rem;
                        font-size: 0.8rem;
                        background: #fff;
                    }}
                    .stock-chart-wrap {{
                        border: 1px solid #e2e8f0;
                        background: #fff;
                        border-radius: 0.8rem;
                        padding: 0.85rem 0.75rem 0.65rem;
                        min-height: 460px;
                        height: 460px;
                    }}
                    #stock-chart {{
                        width: 100% !important;
                        height: 420px !important;
                    }}
                    .stock-status {{
                        font-size: 0.88rem;
                        color: #64748b;
                    }}
                    .stock-analysis-list {{
                        margin-top: 0.75rem;
                        display: grid;
                        gap: 0.55rem;
                    }}
                    .stock-analysis-item {{
                        border: 1px solid #e2e8f0;
                        border-radius: 0.7rem;
                        background: #fff;
                        padding: 0.55rem 0.65rem;
                    }}
                    .stock-analysis-meta {{
                        font-size: 0.82rem;
                        color: #64748b;
                        margin-bottom: 0.25rem;
                    }}
                    @media (max-width: 980px) {{
                        .stock-chart-wrap {{
                            min-height: 380px;
                            height: 380px;
                        }}
                        #stock-chart {{
                            height: 340px !important;
                        }}
                    }}
                    .indicator-section {{
                        border: 1px solid #e2e8f0;
                        border-radius: 0.75rem;
                        background: #fff;
                        padding: 0.65rem;
                        margin-bottom: 0.65rem;
                    }}
                    .indicator-section h3 {{
                        margin: 0 0 0.5rem;
                        font-size: 0.96rem;
                    }}
                    .indicator-table {{
                        width: 100%;
                        border-collapse: collapse;
                        table-layout: fixed;
                    }}
                    .indicator-table th,
                    .indicator-table td {{
                        text-align: left;
                        border-bottom: 1px solid #eef2f7;
                        padding: 0.36rem 0.3rem;
                        vertical-align: top;
                        font-size: 0.86rem;
                        overflow-wrap: anywhere;
                    }}
                    .indicator-table th {{
                        width: 40%;
                        color: #475569;
                        font-weight: 600;
                    }}
                    .indicator-analysis-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 0.5rem;
                        margin-top: 0.5rem;
                    }}
                    .indicator-analysis-card {{
                        border: 1px solid #e2e8f0;
                        border-radius: 0.6rem;
                        background: #f8fafc;
                        padding: 0.5rem 0.55rem;
                    }}
                    .indicator-analysis-card h4 {{
                        margin: 0 0 0.35rem;
                        font-size: 0.85rem;
                    }}
                </style>
            </head>
            <body class="report">
                {render_nav("company")}
                <div class="container">
                    <section class="card report">
                        <div class="header-row">
                            <h1>{display_company}</h1>
                            <div class="header-actions">
                                <select class="week-input" id="company-job-model"></select>
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
                        <div class="view-tabs" id="view-tabs">
                            <button class="view-tab active" type="button" data-view-mode="daily">Daily News</button>
                            <button class="view-tab" type="button" data-view-mode="weekly">Weekly Report</button>
                            <button class="view-tab" type="button" data-view-mode="monthly">Monthly Report</button>
                            <button class="view-tab" type="button" data-view-mode="stock">Price Intelligence</button>
                            <button class="view-tab" type="button" data-view-mode="indicators">Indicators</button>
                            <button class="view-tab" type="button" data-view-mode="earnings">Earnings</button>
                            <button class="view-tab" type="button" data-view-mode="stories">Stories</button>
                        </div>
                        <div class="layout" id="company-layout">
                            <div class="timeline" id="timeline"></div>
                            <div id="news-content">
                                <p class="placeholder">Select a date from the timeline.</p>
                            </div>
                        </div>
                    </section>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                {shared_chart_assets}
                <script>
                    const stockModelChoices = {model_choices_json};
                    const companyModelChoices = {company_model_choices_json};
                    const indicatorModels = {indicator_models_json};
                    const defaultCompanyModel = {default_company_model_json};
                    const timelineEl = document.getElementById("timeline");
                    const layoutEl = document.getElementById("company-layout");
                    const contentEl = document.getElementById("news-content");
                    const viewTabsEl = document.getElementById("view-tabs");
                    const refreshBtn = document.getElementById("refresh-btn");
                    const refreshStatus = document.getElementById("refresh-status");
                    const rangeInput = document.getElementById("range-date");
                    const outputLanguageSelect = document.getElementById("global-language-select");
                    const sourceSelect = document.getElementById("news-source");
                    const companyJobModelSelect = document.getElementById("company-job-model");
                    const refreshWrap = refreshBtn ? refreshBtn.closest(".refresh-wrap") : null;
                    const companyName = "{safe_company}";
                    const VIEW_MODES = new Set(["daily", "weekly", "monthly", "stock", "indicators", "earnings", "stories"]);
                    const RANGE_KEYS = new Set({stock_range_keys_json});
                    function normalizeViewMode(raw) {{
                        const token = String(raw || "").trim().toLowerCase();
                        return VIEW_MODES.has(token) ? token : "daily";
                    }}
                    function normalizeRangeKey(raw) {{
                        const token = String(raw || "").trim().toUpperCase();
                        return RANGE_KEYS.has(token) ? token : "1Y";
                    }}
                    const WEEK_START_DAY = 6; // Saturday (JS: 0=Sun, 6=Sat)
                    function weekBoundaries(d) {{
                        const offset = (d.getDay() - WEEK_START_DAY + 7) % 7;
                        const start = new Date(d);
                        start.setDate(d.getDate() - offset);
                        const end = new Date(start);
                        end.setDate(start.getDate() + 6);
                        return [start, end];
                    }}
                    function fmtDate(d) {{
                        return d.toISOString().slice(0, 10);
                    }}
                    let currentWeekStart = null;
                    let currentWeekEnd = null;
                    function readUrlState() {{
                        const params = new URLSearchParams(window.location.search || "");
                        const lang = String(params.get("lang") || "").trim();
                        const source = String(params.get("source") || "").trim().toLowerCase();
                        const dateRange = String(params.get("date_range") || "").trim();
                        return {{
                            viewMode: normalizeViewMode(params.get("view")),
                            groupKey: String(params.get("group") || "").trim() || null,
                            stockRange: normalizeRangeKey(params.get("range")),
                            lang: lang === "en" ? "en" : "zh-CN",
                            source: source || "finnhub",
                            dateRange,
                        }};
                    }}
                    function updateUrlState({{ viewMode = null, groupKey = null, stockRange = null }} = {{}}) {{
                        const url = new URL(window.location.href);
                        const params = url.searchParams;
                        const mode = normalizeViewMode(viewMode || currentViewMode || "daily");
                        params.set("view", mode);
                        if ((mode === "daily" || mode === "weekly" || mode === "monthly") && groupKey) {{
                            params.set("group", String(groupKey));
                        }} else {{
                            params.delete("group");
                        }}
                        if (mode === "stock") {{
                            params.set("range", normalizeRangeKey(stockRange || currentStockRange || "1Y"));
                        }} else {{
                            params.delete("range");
                        }}
                        params.set("lang", getOutputLanguage());
                        if (sourceSelect && sourceSelect.value) {{
                            params.set("source", String(sourceSelect.value || "finnhub").toLowerCase());
                        }}
                        if (rangeInput && rangeInput.value) {{
                            params.set("date_range", String(rangeInput.value || "").trim());
                        }}
                        const next = `${{url.pathname}}?${{params.toString()}}`;
                        window.history.replaceState({{}}, "", next);
                    }}
                    const initialUrlState = readUrlState();
                    let selectedGroupKey = initialUrlState.groupKey;
                    let currentViewMode = initialUrlState.viewMode;
                    let currentStockRange = initialUrlState.stockRange;
                    let allGroups = [];
                    const statusCache = {{}};
                    const storyCache = {{}};
                    let stockChartController = null;
                    let storyPollTimer = null;
                    let storyJobStop = null;
                    let priceIntelligenceJobStop = null;
                    let priceIntelligenceDetailJobStop = null;

                    function getOutputLanguage() {{
                        const selected = outputLanguageSelect && outputLanguageSelect.value
                            ? String(outputLanguageSelect.value)
                            : "zh-CN";
                        return selected || "zh-CN";
                    }}

                    function initOutputLanguage() {{
                        const key = "preferred_output_language";
                        const saved = localStorage.getItem(key);
                        const normalized = initialUrlState.lang || (saved === "en" ? "en" : "zh-CN");
                        if (outputLanguageSelect) {{
                            outputLanguageSelect.value = normalized;
                            outputLanguageSelect.addEventListener("change", () => {{
                                const next = getOutputLanguage();
                                localStorage.setItem(key, next);
                                for (const cacheKey of Object.keys(statusCache)) {{
                                    delete statusCache[cacheKey];
                                }}
                                for (const cacheKey of Object.keys(storyCache)) {{
                                    delete storyCache[cacheKey];
                                }}
                                if (currentViewMode === "stories") {{
                                    renderStoriesView();
                                }}
                                updateUrlState({{
                                    viewMode: currentViewMode,
                                    groupKey: selectedGroupKey,
                                    stockRange: currentStockRange,
                                }});
                            }});
                        }}
                    }}

                    function getCompanyJobModel() {{
                        if (companyJobModelSelect && companyJobModelSelect.value) {{
                            return String(companyJobModelSelect.value);
                        }}
                        return String(defaultCompanyModel || "gpt-5.4-mini");
                    }}

                    async function persistCompanyJobModel(nextModel) {{
                        const selectedModel = String(nextModel || "").trim() || String(defaultCompanyModel || "gpt-5.4-mini");
                        const response = await fetch(`/api/company/${{encodeURIComponent(companyName)}}/llm-model`, {{
                            method: "PUT",
                            headers: {{
                                "Content-Type": "application/json",
                            }},
                            body: JSON.stringify({{ model: selectedModel }}),
                        }});
                        const payload = await response.json();
                        if (!response.ok || payload.error) {{
                            throw new Error((payload && payload.error) || "Failed to save company model.");
                        }}
                        return payload;
                    }}

                    function initCompanyJobModel() {{
                        if (!companyJobModelSelect) {{
                            return;
                        }}
                        const models = Array.isArray(companyModelChoices) ? companyModelChoices : [];
                        const selectedModel = String(defaultCompanyModel || "gpt-5.4-mini");
                        companyJobModelSelect.innerHTML = models
                            .map((model) => {{
                                const value = String(model || "");
                                const selected = value === selectedModel ? "selected" : "";
                                return `<option value="${{escapeHtml(value)}}" ${{selected}}>${{escapeHtml(value)}}</option>`;
                            }})
                            .join("");
                        if (![...companyJobModelSelect.options].some((option) => option.value === selectedModel)) {{
                            const option = document.createElement("option");
                            option.value = selectedModel;
                            option.textContent = selectedModel;
                            option.selected = true;
                            companyJobModelSelect.appendChild(option);
                        }}
                        companyJobModelSelect.dataset.previousValue = selectedModel;
                        companyJobModelSelect.addEventListener("change", async () => {{
                            const previous = companyJobModelSelect.dataset.previousValue || selectedModel;
                            const nextModel = getCompanyJobModel();
                            try {{
                                await persistCompanyJobModel(nextModel);
                                companyJobModelSelect.dataset.previousValue = nextModel;
                                for (const cacheKey of Object.keys(statusCache)) {{
                                    delete statusCache[cacheKey];
                                }}
                                for (const cacheKey of Object.keys(storyCache)) {{
                                    delete storyCache[cacheKey];
                                }}
                                if (currentViewMode === "stories") {{
                                    renderStoriesView();
                                }} else if (currentViewMode === "stock") {{
                                    renderStockView();
                                }}
                            }} catch (err) {{
                                companyJobModelSelect.value = previous;
                                alert(err && err.message ? err.message : "Failed to save company model.");
                            }}
                        }});
                    }}

                    function buildCompanyStatusCacheKey(style, outputLanguage) {{
                        return `${{style}}|${{outputLanguage}}|${{getCompanyJobModel()}}`;
                    }}

                    function buildCompanyStoryCacheKey(style, outputLanguage) {{
                        return `${{style}}|${{outputLanguage}}|${{getCompanyJobModel()}}`;
                    }}

                    function escapeHtml(value) {{
                        return String(value)
                            .replace(/&/g, "&amp;")
                            .replace(/</g, "&lt;")
                            .replace(/>/g, "&gt;")
                            .replace(/"/g, "&quot;")
                            .replace(/'/g, "&#39;");
                    }}

                    function formatFieldLabel(key) {{
                        const raw = String(key || "");
                        if (!raw) return "";
                        return raw
                            .split("_")
                            .filter(Boolean)
                            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
                            .join(" ");
                    }}

                    function renderFieldValue(value) {{
                        if (value === null || value === undefined) {{
                            return "—";
                        }}
                        if (Array.isArray(value)) {{
                            if (!value.length) {{
                                return "—";
                            }}
                            const rows = value
                                .map((entry) => `<li>${{renderFieldValue(entry)}}</li>`)
                                .join("");
                            return `<ul>${{rows}}</ul>`;
                        }}
                        if (typeof value === "object") {{
                            const rows = Object.entries(value)
                                .map(
                                    ([subKey, subValue]) =>
                                        `<li><strong>${{formatFieldLabel(subKey)}}:</strong> ${{renderFieldValue(subValue)}}</li>`
                                )
                                .join("");
                            return rows ? `<ul>${{rows}}</ul>` : "—";
                        }}
                        const text = String(value).trim();
                        return text ? toReadableBullets(text) : "—";
                    }}

                    function buildAllContentFields(content) {{
                        if (!content || typeof content !== "object") {{
                            return [];
                        }}
                        const skippedKeys = new Set(["summary", "sentiment"]);
                        return Object.entries(content).map(
                            ([key, value]) => {{
                                if (skippedKeys.has(String(key || "").toLowerCase())) {{
                                    return "";
                                }}
                                return (
                                `<div class="news-field"><strong>${{formatFieldLabel(key)}}:</strong> ${{renderFieldValue(value)}}</div>`
                                );
                            }}
                        ).filter(Boolean);
                    }}

                    function formatRawResponse(raw) {{
                        if (!raw) {{
                            return "";
                        }}
                        if (typeof raw !== "string") {{
                            return escapeHtml(String(raw));
                        }}
                        try {{
                            const parsed = JSON.parse(raw);
                            return escapeHtml(JSON.stringify(parsed, null, 2));
                        }} catch (_err) {{
                            return escapeHtml(raw);
                        }}
                    }}

                    function renderMarkdown(value) {{
                        const content = String(value || "").trim();
                        if (!content) {{
                            return "<p>—</p>";
                        }}
                        if (window.marked && typeof window.marked.parse === "function") {{
                            return window.marked.parse(content);
                        }}
                        return `<pre>${{escapeHtml(content)}}</pre>`;
                    }}

                    function formatDateTime(value) {{
                        const text = String(value || "").trim();
                        if (!text) return "—";
                        const date = new Date(text);
                        if (Number.isNaN(date.getTime())) {{
                            return text;
                        }}
                        return date.toLocaleString();
                    }}

                    function toReadableBullets(raw) {{
                        const text = String(raw || "").trim();
                        if (!text) return "—";
                        const clean = text.split("\\r").join("");
                        const lines = clean.split("\\n").map((x) => x.trim()).filter(Boolean);
                        if (lines.length >= 2) {{
                            return `<ul>${{lines.map((line) => {{
                                const stripped = line.startsWith("- ") || line.startsWith("* ")
                                    ? line.slice(2).trim()
                                    : line;
                                return `<li>${{renderMarkdown(stripped)}}</li>`;
                            }}).join("")}}</ul>`;
                        }}
                        const semis = clean.split(/\\s*[;；]\\s*/).map((x) => x.trim()).filter(Boolean);
                        if (semis.length >= 2) {{
                            return `<ul>${{semis.map((part) => `<li>${{renderMarkdown(part)}}</li>`).join("")}}</ul>`;
                        }}
                        return renderMarkdown(clean);
                    }}

                    function buildNewsCard(item) {{
                        const sourceText = item.publisher || item.content.publisher;
                        const sourceLink = item.news_source_link
                            ? `<a href="${{item.news_source_link}}" target="_blank" rel="noopener noreferrer">${{item.news_source_link}}</a>`
                            : "";
                        const meta = [sourceText, sourceLink]
                            .filter(Boolean)
                            .join(" · ");
                        const displayTime = formatPst(item.news_date_time);
                        const summaryText = item.content && item.content.summary
                            ? item.content.summary
                            : "—";
                        const sentimentText = item.content && item.content.sentiment
                            ? item.content.sentiment
                            : "—";
                        const allContentFields = buildAllContentFields(item.content || {{}});
                        const rawResponse = formatRawResponse(item.llm_response_raw || "");
                        return `
                            <div class="news-card ${{item.is_analyzed ? "analyzed" : "raw"}}" data-news-id="${{item.id}}">
                                ${{item.news_source ? `<span class="news-source-tag">${{item.news_source}}</span>` : ""}}
                                <h3>${{item.news_title}}</h3>
                                <div class="news-meta">
                                    <div>${{displayTime}}</div>
                                    <div>${{meta}}</div>
                                </div>
                                <div class="news-content">
                                    ${{!item.is_analyzed ? `<div class="news-summary">
                                        <div><strong>Source:</strong> ${{sourceText || "—"}}</div>
                                        <div>${{sourceLink || ""}}</div>
                                        <div class="news-actions">
                                            <button class="news-action-btn create-story" type="button">Create Story</button>
                                            <button class="news-action-btn attach-story" type="button">Attach Story</button>
                                            <button class="news-action-btn remove-inline" type="button">Remove</button>
                                        </div>
                                    </div>` : `<div class="news-summary">
                                        <div><strong>Summary:</strong> ${{summaryText}}</div>
                                        <div><strong>Sentiment:</strong> ${{sentimentText}}</div>
                                    </div>`}}
                                    ${{item.is_analyzed ? `<div class="news-details">
                                        ${{allContentFields.join("")}}
                                        ${{rawResponse ? `<div class="news-field"><strong>OpenAI Response:</strong><pre>${{rawResponse}}</pre></div>` : ""}}
                                        <div class="news-actions">
                                            <button class="news-action-btn create-story" type="button">Create Story</button>
                                            <button class="news-action-btn attach-story" type="button">Attach Story</button>
                                            <button class="news-action-btn original" type="button">Original</button>
                                            <button class="news-action-btn delete" type="button">Remove</button>
                                        </div>
                                    </div>` : ""}}
                                </div>
                            </div>
                        `;
                    }}

                    function getFilteredGroups() {{
                        if (!Array.isArray(allGroups)) {{
                            return [];
                        }}
                        if (currentViewMode === "daily") {{
                            return allGroups.filter((g) => g.type === "daily");
                        }}
                        if (currentViewMode === "weekly") {{
                            return allGroups.filter((g) => g.type === "weekly");
                        }}
                        if (currentViewMode === "monthly") {{
                            return allGroups.filter((g) => g.type === "monthly");
                        }}
                        return [];
                    }}

                    function setViewMode(mode) {{
                        if (storyPollTimer) {{
                            clearTimeout(storyPollTimer);
                            storyPollTimer = null;
                        }}
                        currentViewMode = normalizeViewMode(mode);
                        updateUrlState({{
                            viewMode: currentViewMode,
                            groupKey: selectedGroupKey,
                            stockRange: currentStockRange,
                        }});
                        const needsNewsRangeControls = currentViewMode === "daily" || currentViewMode === "weekly";
                        if (sourceSelect) {{
                            sourceSelect.style.display = needsNewsRangeControls ? "" : "none";
                        }}
                        if (rangeInput) {{
                            rangeInput.style.display = needsNewsRangeControls ? "" : "none";
                        }}
                        if (refreshWrap) {{
                            refreshWrap.style.display = needsNewsRangeControls ? "inline-flex" : "none";
                        }}
                        if (viewTabsEl) {{
                            viewTabsEl.querySelectorAll(".view-tab").forEach((btn) => {{
                                btn.classList.toggle("active", btn.dataset.viewMode === currentViewMode);
                            }});
                        }}
                        if (currentViewMode === "status") {{
                            timelineEl.style.display = "none";
                            if (layoutEl) {{
                                layoutEl.style.gridTemplateColumns = "1fr";
                            }}
                            renderStatusView();
                            return;
                        }}
                        if (currentViewMode === "stories") {{
                            timelineEl.style.display = "none";
                            if (layoutEl) {{
                                layoutEl.style.gridTemplateColumns = "1fr";
                            }}
                            renderStoriesView();
                            return;
                        }}
                        if (currentViewMode === "stock") {{
                            timelineEl.style.display = "none";
                            if (layoutEl) {{
                                layoutEl.style.gridTemplateColumns = "1fr";
                            }}
                            renderStockView();
                            return;
                        }}
                        if (currentViewMode === "earnings") {{
                            timelineEl.style.display = "none";
                            if (layoutEl) {{
                                layoutEl.style.gridTemplateColumns = "1fr";
                            }}
                            renderEarningsView();
                            return;
                        }}
                        if (currentViewMode === "indicators") {{
                            timelineEl.style.display = "none";
                            if (layoutEl) {{
                                layoutEl.style.gridTemplateColumns = "1fr";
                            }}
                            renderIndicatorsView();
                            return;
                        }}
                        timelineEl.style.display = "";
                        if (layoutEl) {{
                            layoutEl.style.gridTemplateColumns = "200px 1fr";
                        }}
                        renderTimeline(getFilteredGroups());
                    }}

                    async function fetchCompanyStatus(promptStyle, generateIfMissing = true) {{
                        const style = promptStyle || "simple";
                        const outputLanguage = getOutputLanguage();
                        const model = getCompanyJobModel();
                        const cacheKey = buildCompanyStatusCacheKey(style, outputLanguage);
                        const response = await fetch(
                            `/api/company/${{encodeURIComponent(companyName)}}/status?prompt_style=${{encodeURIComponent(style)}}&model=${{encodeURIComponent(model)}}`
                        );
                        const payload = await response.json();
                        if (payload && payload.status) {{
                            statusCache[cacheKey] = payload.status;
                            return payload.status;
                        }}
                        if (!generateIfMissing) {{
                            return null;
                        }}
                        const genResp = await fetch(
                            `/api/company/${{encodeURIComponent(companyName)}}/status/generate?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(outputLanguage)}}&model=${{encodeURIComponent(model)}}`,
                            {{ method: "POST" }}
                        );
                        const genPayload = await genResp.json();
                        if (genPayload && genPayload.status) {{
                            statusCache[cacheKey] = genPayload.status;
                            return genPayload.status;
                        }}
                        return null;
                    }}

                    function renderStatusView() {{
                        const outputLanguage = getOutputLanguage();
                        const cachedSimple = statusCache[buildCompanyStatusCacheKey("simple", outputLanguage)] || null;
                        const defaultStyle = cachedSimple ? "simple" : "simple";
                        contentEl.innerHTML = `
                            <div class="status-panel">
                                <div class="status-panel-header">
                                    <div class="status-header-main">
                                        <h2 style="margin:0;">Company Status</h2>
                                        <div class="status-meta" id="status-meta">Loading status...</div>
                                    </div>
                                    <div class="status-controls">
                                        <select class="status-select" id="status-prompt-style">
                                            <option value="simple" selected>simple</option>
                                            <option value="structured">structured</option>
                                        </select>
                                        <button class="status-btn" id="status-refresh-btn" type="button">Refresh Status</button>
                                    </div>
                                </div>
                                <div class="status-output" id="status-output"></div>
                            </div>
                        `;
                        const promptSelect = document.getElementById("status-prompt-style");
                        const refreshStatusBtn = document.getElementById("status-refresh-btn");
                        const statusOutput = document.getElementById("status-output");
                        const statusMeta = document.getElementById("status-meta");
                        if (promptSelect) {{
                            promptSelect.value = defaultStyle;
                        }}

                        async function loadForStyle(style, forceGenerate = false) {{
                            if (statusOutput) {{
                                statusOutput.textContent = forceGenerate ? "Generating company status..." : "Loading company status...";
                            }}
                            if (statusMeta) {{
                                statusMeta.textContent = "";
                            }}
                            let status = null;
                            const outputLanguage = getOutputLanguage();
                            const cacheKey = buildCompanyStatusCacheKey(style, outputLanguage);
                            if (!forceGenerate && statusCache[cacheKey]) {{
                                status = statusCache[cacheKey];
                            }} else if (!forceGenerate) {{
                                status = await fetchCompanyStatus(style, true);
                            }} else {{
                                const resp = await fetch(
                                    `/api/company/${{encodeURIComponent(companyName)}}/status/generate?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(outputLanguage)}}&model=${{encodeURIComponent(getCompanyJobModel())}}`,
                                    {{ method: "POST" }}
                                );
                                const payload = await resp.json();
                                status = payload && payload.status ? payload.status : null;
                                if (status) {{
                                    statusCache[cacheKey] = status;
                                }}
                            }}
                            if (!status) {{
                                if (statusOutput) {{
                                    statusOutput.textContent = "No company status available yet.";
                                }}
                                if (statusMeta) {{
                                    statusMeta.textContent = "Generate status after you have company news / daily reports.";
                                }}
                                return;
                            }}
                            if (statusMeta) {{
                                statusMeta.textContent =
                                    `as_of=${{status.as_of_date}} · window=${{status.window_start_date}} → ${{status.window_end_date}} · provider=${{status.provider}} · model=${{status.model}} · prompt=${{status.prompt_style}} · generated=${{status.created_at}}`;
                            }}
                            if (statusOutput) {{
                                statusOutput.innerHTML = renderMarkdown(status.output_text || "—");
                            }}
                        }}

                        if (promptSelect) {{
                            promptSelect.addEventListener("change", () => {{
                                loadForStyle(promptSelect.value, false);
                            }});
                        }}
                        if (refreshStatusBtn) {{
                            refreshStatusBtn.addEventListener("click", async () => {{
                                refreshStatusBtn.disabled = true;
                                refreshStatusBtn.textContent = "Refreshing...";
                                try {{
                                    const style = promptSelect ? promptSelect.value : "simple";
                                    await loadForStyle(style, true);
                                }} finally {{
                                    refreshStatusBtn.disabled = false;
                                    refreshStatusBtn.textContent = "Refresh Status";
                                }}
                            }});
                        }}

                        loadForStyle(defaultStyle, false);
                    }}

                    function formatStoryArray(value) {{
                        if (!Array.isArray(value) || !value.length) {{
                            return "<p>—</p>";
                        }}
                        function formatStoryEntry(entry) {{
                            if (entry === null || entry === undefined) {{
                                return "—";
                            }}
                            if (typeof entry === "string" || typeof entry === "number" || typeof entry === "boolean") {{
                                return renderMarkdown(String(entry));
                            }}
                            if (Array.isArray(entry)) {{
                                return `<ul>${{entry.map((row) => `<li>${{formatStoryEntry(row)}}</li>`).join("")}}</ul>`;
                            }}
                            if (typeof entry === "object") {{
                                const title = entry.title || entry.news_title || entry.headline || entry.label || entry.key || "";
                                const date = entry.date || entry.news_date_time || entry.report_date || entry.as_of_date || "";
                                const source = entry.source || entry.news_source || entry.provider || "";
                                const link = entry.url || entry.news_source_link || entry.link || "";
                                const summary = entry.summary || entry.note || entry.change || entry.text || "";
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
                                        ? `<div>${{renderMarkdown(String(summary))}}</div>`
                                        : "";
                                    return `<div>${{top || "Item"}}${{linkHtml}}${{summaryHtml}}</div>`;
                                }}
                                return `<pre>${{escapeHtml(JSON.stringify(entry, null, 2))}}</pre>`;
                            }}
                            return escapeHtml(String(entry));
                        }}
                        return `<ul>${{value.map((entry) => `<li>${{formatStoryEntry(entry)}}</li>`).join("")}}</ul>`;
                    }}

                    async function fetchJsonWithTimeout(url, options = {{}}, timeoutMs = 90000) {{
                        const controller = new AbortController();
                        const timer = setTimeout(() => controller.abort(), timeoutMs);
                        try {{
                            const response = await fetch(url, {{ ...options, signal: controller.signal }});
                            let payload = null;
                            try {{
                                payload = await response.json();
                            }} catch (_err) {{
                                payload = null;
                            }}
                            if (!response.ok) {{
                                const msg = (payload && payload.error)
                                    ? String(payload.error)
                                    : `HTTP ${{response.status}}`;
                                throw new Error(msg);
                            }}
                            if (payload && payload.error) {{
                                throw new Error(String(payload.error));
                            }}
                            return payload || {{}};
                        }} finally {{
                            clearTimeout(timer);
                        }}
                    }}

                    function buildJobKey(...parts) {{
                        return parts.map((item) => String(item || "").trim().toLowerCase()).join("|");
                    }}

                    function formatJobText(job) {{
                        if (!job) return "";
                        const counts = job.final_counts || {{}};
                        const parts = [String(job.status || "")];
                        if (job.current_stage) parts.push(String(job.current_stage));
                        if (job.elapsed_sec) parts.push(`${{Number(job.elapsed_sec || 0).toFixed(1)}}s`);
                        if (job.input_char_count) parts.push(`prompt=${{job.input_char_count}} chars`);
                        if (job.input_item_count) parts.push(`input=${{job.input_item_count}}`);
                        if (job.output_char_count) parts.push(`output=${{job.output_char_count}} chars`);
                        if (counts.raw_stored_count) parts.push(`raw=${{counts.raw_stored_count}}`);
                        if (counts.filtered_kept_count) parts.push(`kept=${{counts.filtered_kept_count}}`);
                        if (counts.cluster_count) parts.push(`clusters=${{counts.cluster_count}}`);
                        if (counts.report_count || counts.daily_report_count) parts.push(`reports=${{counts.report_count || counts.daily_report_count}}`);
                        if (counts.updated_story_count || counts.new_story_count) parts.push(`stories +${{counts.new_story_count || 0}}/${{counts.updated_story_count || 0}} updated`);
                        if (job.result_summary) parts.push(String(job.result_summary));
                        if (job.error_text) parts.push(String(job.error_text));
                        return parts.filter(Boolean).join(" · ");
                    }}

                    async function fetchJob(jobId) {{
                        const payload = await fetchJsonWithTimeout(`/api/jobs/${{encodeURIComponent(String(jobId))}}`, {{ method: "GET" }}, 30000);
                        return payload.job || null;
                    }}

                    async function fetchJobByKey(jobKey) {{
                        try {{
                            const payload = await fetchJsonWithTimeout(`/api/jobs/by-key?job_key=${{encodeURIComponent(jobKey)}}&include_finished=true`, {{ method: "GET" }}, 30000);
                            return payload.job || null;
                        }} catch (_err) {{
                            return null;
                        }}
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

                    async function fetchStoryList(style, forceRefresh = false, bypassCache = false) {{
                        const outputLanguage = getOutputLanguage();
                        const model = getCompanyJobModel();
                        const cacheKey = buildCompanyStoryCacheKey(style, outputLanguage);
                        if (!forceRefresh && !bypassCache && storyCache[cacheKey]) {{
                            return storyCache[cacheKey];
                        }}
                        const url = forceRefresh
                            ? `/api/company/${{encodeURIComponent(companyName)}}/stories/refresh?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(outputLanguage)}}&model=${{encodeURIComponent(model)}}`
                            : `/api/company/${{encodeURIComponent(companyName)}}/stories?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(outputLanguage)}}&model=${{encodeURIComponent(model)}}`;
                        const payload = await fetchJsonWithTimeout(
                            url,
                            {{ method: forceRefresh ? "POST" : "GET" }},
                            forceRefresh ? 180000 : 30000,
                        );
                        const normalized = {{
                            stories: Array.isArray(payload.stories) ? payload.stories : [],
                            ongoing_stories: Array.isArray(payload.ongoing_stories) ? payload.ongoing_stories : [],
                            finished_stories: Array.isArray(payload.finished_stories) ? payload.finished_stories : [],
                            warmup: payload.warmup || null,
                            job: payload.job || null,
                            mode: payload.mode || "",
                        }};
                        storyCache[cacheKey] = normalized;
                        return normalized;
                    }}

                    async function fetchStoryDetail(storyKey, style) {{
                        const outputLanguage = getOutputLanguage();
                        return fetchJsonWithTimeout(
                            `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(storyKey)}}?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(outputLanguage)}}`,
                            {{ method: "GET" }},
                            30000,
                        );
                    }}

                    function renderStoryDetailBody(story, updates, qa) {{
                        if (!story) {{
                            return '<p class="placeholder">Select a story to see details.</p>';
                        }}
                        const timelineRows = Array.isArray(story.timeline_items) && story.timeline_items.length
                            ? `<ul>${{story.timeline_items.map((item) => `<li><strong>${{escapeHtml(String(item.date || item.label || ""))}}</strong>${{item.summary ? ` · ${{escapeHtml(String(item.summary))}}` : ""}}</li>`).join("")}}</ul>`
                            : "—";
                        const futureRows = Array.isArray(story.future_and_impact) && story.future_and_impact.length
                            ? `<ul>${{story.future_and_impact.map((item) => `<li>${{escapeHtml(String(item.scenario || ""))}}${{item.probability ? ` · prob=${{escapeHtml(String(item.probability))}}` : ""}}${{item.impact ? ` · impact=${{escapeHtml(String(item.impact))}}` : ""}}</li>`).join("")}}</ul>`
                            : "—";
                        const isClosed = ["finished", "resolved", "closed"].includes(String(story.story_status || "").toLowerCase());
                        const askModelOptions = Array.isArray(stockModelChoices)
                            ? stockModelChoices.map((item) => {{
                                const provider = String(item.provider || "openai");
                                const model = String(item.model || "");
                                const selected = provider === "openai" && model === {default_openai_model_json} ? "selected" : "";
                                return `<option value="${{escapeHtml(model)}}" data-provider="${{escapeHtml(provider)}}" ${{selected}}>${{escapeHtml(`${{provider}} · ${{model}}`)}}</option>`;
                              }}).join("")
                            : `<option value="${{escapeHtml(String({default_openai_model_json}))}}" data-provider="openai" selected>openai · ${{escapeHtml(String({default_openai_model_json}))}}</option>`;
                        const updatesRows = Array.isArray(updates) && updates.length
                            ? updates
                                .slice(0, 6)
                                .map((row) => `<li>${{row.as_of_date}} · model=${{row.model}} · provider=${{row.provider}}</li>`)
                                .join("")
                            : "<li>—</li>";
                        const qaRows = Array.isArray(qa) && qa.length
                            ? qa.map((row) => `
                                <div class="story-ask-row">
                                    <div class="story-ask-meta">${{row.created_at}} · ${{row.provider}} · ${{row.model}}</div>
                                    <div><strong>Q:</strong> ${{escapeHtml(row.question || "")}}</div>
                                    <div><strong>A:</strong> ${{renderMarkdown(row.answer || "")}}</div>
                                    <div class="story-ask-actions">
                                        <button class="story-merge-btn" type="button" data-qa-id="${{row.id}}">Merge into Story</button>
                                    </div>
                                </div>
                              `).join("")
                            : '<p class="placeholder">No Q&A yet.</p>';
                        return `
                            <div class="story-detail-section">
                                <h3>${{escapeHtml(story.story_title || "")}}</h3>
                                <div class="story-item-meta">status=${{story.story_status}} · priority=${{story.priority || "normal"}} · updated=${{story.updated_at || ""}}</div>
                                <div class="story-detail-box">${{escapeHtml(story.story_summary || "—")}}</div>
                                <div class="story-ask-controls" style="margin-top:0.6rem;">
                                    <button class="story-merge-btn" id="story-status-toggle-btn" type="button">${{isClosed ? "Reopen Story" : "Close Story"}}</button>
                                    <button class="story-merge-btn" id="story-priority-btn" type="button">${{String(story.priority || "normal") === "high" ? "Set Normal Priority" : "Set High Priority"}}</button>
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
                            <div class="story-detail-section">
                                <h3>Update History</h3>
                                <div class="story-detail-box"><ul>${{updatesRows}}</ul></div>
                            </div>
                            <div class="story-ask-wrap">
                                <h3 style="margin:0;">Deep Dive Question</h3>
                                <div class="story-ask-controls">
                                    <select class="story-ask-model" id="story-ask-model">${{askModelOptions}}</select>
                                </div>
                                <textarea class="story-ask-input" id="story-ask-input" placeholder="Ask a question for this story..."></textarea>
                                <button class="story-ask-btn" id="story-ask-btn" type="button">Ask</button>
                            </div>
                            <div class="story-ask-log" id="story-ask-log">${{qaRows}}</div>
                        `;
                    }}

                    function renderStoriesView() {{
                        contentEl.innerHTML = `
                            <div class="status-panel">
                                <div class="status-panel-header">
                                    <div class="status-header-main">
                                        <h2 style="margin:0;">Company Stories</h2>
                                        <div class="status-meta" id="stories-meta">Loading stories...</div>
                                    </div>
                                    <div class="status-controls">
                                        <button class="status-btn" id="stories-rebuild-btn" type="button" style="display:none;">Rebuild Warm-up</button>
                                        <button class="status-btn" id="stories-refresh-btn" type="button">Update Stories</button>
                                    </div>
                                </div>
                                <div class="stories-wrap">
                                    <div class="stories-side"><div class="story-list" id="story-list"></div></div>
                                    <div class="stories-main" id="story-detail"><p class="placeholder">Select a story to see details.</p></div>
                                </div>
                            </div>
                        `;
                        const refreshBtn = document.getElementById("stories-refresh-btn");
                        const rebuildBtn = document.getElementById("stories-rebuild-btn");
                        const metaEl = document.getElementById("stories-meta");
                        const listEl = document.getElementById("story-list");
                        const detailEl = document.getElementById("story-detail");
                        let activeStoryKey = "";
                        let latestWarmup = null;

                        function scheduleStoryPoll(style) {{
                            if (storyPollTimer) {{
                                clearTimeout(storyPollTimer);
                                storyPollTimer = null;
                            }}
                            if (currentViewMode !== "stories") {{
                                return;
                            }}
                            const state = String((latestWarmup && latestWarmup.job_state) || "");
                            if (!["running", "analyzing", "partial"].includes(state)) {{
                                return;
                            }}
                            storyPollTimer = window.setTimeout(() => {{
                                loadStories(false, true, style, true);
                            }}, 4000);
                        }}

                        function renderWarmupMeta(payload) {{
                            const warmup = payload && payload.warmup ? payload.warmup : null;
                            latestWarmup = warmup;
                            if (rebuildBtn) {{
                                const state = String((warmup && warmup.job_state) || "not_started");
                                rebuildBtn.style.display = state === "failed" ? "" : "none";
                            }}
                            const ongoingStories = Array.isArray(payload && payload.ongoing_stories) ? payload.ongoing_stories : [];
                            const finishedStories = Array.isArray(payload && payload.finished_stories) ? payload.finished_stories : [];
                            const latestStoryDate = String((payload && payload.latest_story_date) || "").trim();
                            const detailParts = [];
                            if (warmup) {{
                                const state = String(warmup.job_state || "not_started");
                                const elapsedValue = Number(warmup.elapsed_sec || 0);
                                const elapsed = Number.isFinite(elapsedValue) ? elapsedValue.toFixed(1) : "0.0";
                                if (warmup.total_slices) {{
                                    detailParts.push(`Warm-up days ${{warmup.completed_slices || 0}}/${{warmup.total_slices}}`);
                                }}
                                if (latestStoryDate) {{
                                    detailParts.push(`Latest story date ${{latestStoryDate}}`);
                                }}
                                if (warmup.raw_stored_count || warmup.filtered_kept_count) {{
                                    detailParts.push(`${{warmup.raw_stored_count || 0}} raw news stored`);
                                    detailParts.push(`${{warmup.filtered_kept_count || 0}} kept after filter`);
                                }}
                                detailParts.push(`Elapsed ${{elapsed}}s`);
                                if (warmup.last_error) {{
                                    detailParts.push(`Issue: ${{warmup.last_error}}`);
                                }}
                                if (state === "failed" && Number(warmup.raw_fetched_count || 0) <= 0) {{
                                    detailParts.push("Fix ticker or rebuild warm-up");
                                }}
                            }} else if (latestStoryDate) {{
                                detailParts.push(`Latest story date ${{latestStoryDate}}`);
                            }}
                            detailParts.push(`${{ongoingStories.length}} ongoing stories`);
                            detailParts.push(`${{finishedStories.length}} finished stories`);
                            const details = detailParts.join(" · ");
                            return details;
                        }}

                        function renderStoryGroup(title, stories) {{
                            if (!Array.isArray(stories) || !stories.length) {{
                                return "";
                            }}
                            return `
                                <div class="story-group-heading">${{escapeHtml(title)}}</div>
                                ${{stories.map((story) => `
                                    <div class="story-item ${{story.story_key === activeStoryKey ? "active" : ""}}" data-story-key="${{story.story_key}}">
                                        <div class="story-item-title">${{escapeHtml(story.story_title || "")}}</div>
                                        <div class="story-item-meta">#${{story.importance_rank}} · ${{story.story_status}}</div>
                                    </div>
                                `).join("")}}
                            `;
                        }}

                        async function renderDetail(storyKey, style) {{
                            if (!storyKey || !detailEl) return;
                            detailEl.innerHTML = '<p class="placeholder">Loading story detail...</p>';
                            try {{
                                const payload = await fetchStoryDetail(storyKey, style);
                                if (!payload || !payload.story) {{
                                    detailEl.innerHTML = '<p class="placeholder">Story detail not found.</p>';
                                    return;
                                }}
                                detailEl.innerHTML = renderStoryDetailBody(
                                    payload.story,
                                    payload.updates || [],
                                    payload.qa || [],
                                );
                            }} catch (err) {{
                                const msg = err && err.message ? err.message : "Failed to load story detail.";
                                detailEl.innerHTML = `<p class="placeholder">${{escapeHtml(String(msg))}}</p>`;
                                return;
                            }}
                            const askBtn = document.getElementById("story-ask-btn");
                            const askInput = document.getElementById("story-ask-input");
                            const askModelSelect = document.getElementById("story-ask-model");
                            function getStoryAskSelection() {{
                                if (!askModelSelect) {{
                                    return {{ provider: "openai", model: {default_openai_model_json} }};
                                }}
                                const selected = askModelSelect.selectedOptions && askModelSelect.selectedOptions[0];
                                return {{
                                    provider: selected ? String(selected.dataset.provider || "openai") : "openai",
                                    model: askModelSelect.value ? String(askModelSelect.value) : {default_openai_model_json},
                                }};
                            }}
                            if (askBtn && askInput) {{
                                askBtn.addEventListener("click", async () => {{
                                    const question = String(askInput.value || "").trim();
                                    if (!question) return;
                                    const selectedModel = getStoryAskSelection();
                                    askBtn.disabled = true;
                                    askBtn.textContent = "Asking...";
                                    try {{
                                        const response = await fetch(
                                            `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(storyKey)}}/ask?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&provider=${{encodeURIComponent(selectedModel.provider)}}&model=${{encodeURIComponent(selectedModel.model)}}`,
                                            {{
                                                method: "POST",
                                                headers: {{ "Content-Type": "application/json" }},
                                                body: JSON.stringify({{ question }}),
                                            }}
                                        );
                                        const askPayload = await response.json();
                                        if (askPayload && !askPayload.error) {{
                                            askInput.value = "";
                                            await renderDetail(storyKey, style);
                                        }}
                                    }} finally {{
                                        askBtn.disabled = false;
                                        askBtn.textContent = "Ask";
                                    }}
                                }});
                            }}
                            detailEl.querySelectorAll(".story-merge-btn").forEach((button) => {{
                                button.addEventListener("click", async () => {{
                                    const qaId = String(button.dataset.qaId || "").trim();
                                    if (!qaId) return;
                                    const selectedModel = getStoryAskSelection();
                                    button.disabled = true;
                                    button.textContent = "Merging...";
                                    try {{
                                        const response = await fetch(
                                            `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(storyKey)}}/qa/${{encodeURIComponent(qaId)}}/merge?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&provider=${{encodeURIComponent(selectedModel.provider)}}&model=${{encodeURIComponent(selectedModel.model)}}`,
                                            {{ method: "POST" }}
                                        );
                                        const mergePayload = await response.json();
                                        if (mergePayload && !mergePayload.error) {{
                                            const cacheKey = `${{style}}|${{getOutputLanguage()}}`;
                                            delete storyCache[cacheKey];
                                            await loadStories(false, true, style, true);
                                            await renderDetail(storyKey, style);
                                        }}
                                    }} finally {{
                                        button.disabled = false;
                                        button.textContent = "Merge into Story";
                                    }}
                                }});
                            }});
                            const statusToggleBtn = document.getElementById("story-status-toggle-btn");
                            if (statusToggleBtn) {{
                                statusToggleBtn.addEventListener("click", async () => {{
                                    const endpoint = isClosed ? "reopen" : "close";
                                    const response = await fetch(
                                        `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(storyKey)}}/${{endpoint}}?prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`,
                                        {{ method: "POST" }}
                                    );
                                    const payload = await response.json();
                                    if (payload && !payload.error) {{
                                        const cacheKey = buildCompanyStoryCacheKey(style, getOutputLanguage());
                                        delete storyCache[cacheKey];
                                        await loadStories(false, true, style, true);
                                        await renderDetail(storyKey, style);
                                    }}
                                }});
                            }}
                            const priorityBtn = document.getElementById("story-priority-btn");
                            if (priorityBtn) {{
                                priorityBtn.addEventListener("click", async () => {{
                                    const nextPriority = String(story.priority || "normal") === "high" ? "normal" : "high";
                                    const response = await fetch(
                                        `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(storyKey)}}/priority?priority=${{encodeURIComponent(nextPriority)}}&prompt_style=${{encodeURIComponent(style)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`,
                                        {{ method: "POST" }}
                                    );
                                    const payload = await response.json();
                                    if (payload && !payload.error) {{
                                        const cacheKey = `${{style}}|${{getOutputLanguage()}}`;
                                        delete storyCache[cacheKey];
                                        await loadStories(false, true, style, true);
                                        await renderDetail(storyKey, style);
                                    }}
                                }});
                            }}
                        }}

                        async function loadStories(forceRefresh = false, keepSelection = false, explicitStyle = null, bypassCache = false) {{
                            const style = explicitStyle || "simple";
                            if (metaEl) {{
                                metaEl.textContent = forceRefresh ? "Refreshing stories..." : "Loading stories...";
                            }}
                            let payload = null;
                            try {{
                                payload = await fetchStoryList(style, forceRefresh, bypassCache);
                            }} catch (err) {{
                                const msg = err && err.message ? err.message : "Failed to load stories.";
                                if (metaEl) {{
                                    metaEl.textContent = `Error: ${{msg}}`;
                                }}
                                if (listEl) {{
                                    listEl.innerHTML = `<p class="placeholder">${{escapeHtml(String(msg))}}</p>`;
                                }}
                                if (detailEl) {{
                                    detailEl.innerHTML = '<p class="placeholder">No story detail available.</p>';
                                }}
                                return;
                            }}
                            const ongoingStories = Array.isArray(payload && payload.ongoing_stories) ? payload.ongoing_stories : [];
                            const finishedStories = Array.isArray(payload && payload.finished_stories) ? payload.finished_stories : [];
                            const stories = [...ongoingStories, ...finishedStories];
                            if (metaEl) {{
                                const warmupText = renderWarmupMeta(payload);
                                metaEl.textContent = payload.job ? [formatJobText(payload.job), warmupText].filter(Boolean).join("\\n") : warmupText;
                            }}
                            scheduleStoryPoll(style);
                            if (payload.job) {{
                                const running = ["queued", "running"].includes(String(payload.job.status || ""));
                                if (refreshBtn) {{
                                    refreshBtn.disabled = running;
                                    refreshBtn.textContent = running ? "Update Running..." : "Update Stories";
                                }}
                                if (rebuildBtn) {{
                                    rebuildBtn.disabled = running;
                                    if (running && rebuildBtn.style.display !== "none") {{
                                        rebuildBtn.textContent = "Rebuild Running...";
                                    }} else {{
                                        rebuildBtn.textContent = "Rebuild Warm-up";
                                    }}
                                }}
                                if (running) {{
                                    if (storyJobStop) storyJobStop();
                                    storyJobStop = pollJob(payload.job.job_id, (job) => {{
                                        if (metaEl) metaEl.textContent = formatJobText(job);
                                    }}, async () => {{
                                        const cacheKey = `${{style}}|${{getOutputLanguage()}}`;
                                        delete storyCache[cacheKey];
                                        await loadStories(false, true, style, true);
                                    }});
                                }}
                            }}
                            if (!listEl) return;
                            if (!stories.length) {{
                                listEl.innerHTML = '<p class="placeholder">No stories yet. Use Update Stories to refresh them manually.</p>';
                                if (detailEl) {{
                                    detailEl.innerHTML = '<p class="placeholder">No story detail available.</p>';
                                }}
                                return;
                            }}
                            if (!keepSelection || !stories.some((story) => story.story_key === activeStoryKey)) {{
                                activeStoryKey = stories[0].story_key;
                            }}
                            listEl.innerHTML = `${{renderStoryGroup("Ongoing Stories", ongoingStories)}}${{renderStoryGroup("Finished Stories", finishedStories)}}`;
                            listEl.querySelectorAll(".story-item").forEach((node) => {{
                                node.addEventListener("click", async () => {{
                                    activeStoryKey = node.dataset.storyKey || "";
                                    listEl.querySelectorAll(".story-item").forEach((x) => x.classList.remove("active"));
                                    node.classList.add("active");
                                    await renderDetail(activeStoryKey, style);
                                }});
                            }});
                            await renderDetail(activeStoryKey, style);
                        }}

                        if (refreshBtn) {{
                            refreshBtn.addEventListener("click", async () => {{
                                refreshBtn.disabled = true;
                                refreshBtn.textContent = "Updating...";
                                try {{
                                    activeStoryKey = "";
                                    await loadStories(true);
                                }} finally {{
                                    refreshBtn.disabled = false;
                                    refreshBtn.textContent = "Update Stories";
                                }}
                            }});
                        }}

                        if (rebuildBtn) {{
                            rebuildBtn.addEventListener("click", async () => {{
                                rebuildBtn.disabled = true;
                                rebuildBtn.textContent = "Rebuilding...";
                                try {{
                                    activeStoryKey = "";
                                    const response = await fetch(
                                        `/api/company/${{encodeURIComponent(companyName)}}/stories/rebuild-warmup?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(getCompanyJobModel())}}`,
                                        {{ method: "POST" }}
                                    );
                                    const payload = await response.json();
                                    if (payload && !payload.error) {{
                                        const cacheKey = buildCompanyStoryCacheKey("simple", getOutputLanguage());
                                        delete storyCache[cacheKey];
                                        await loadStories(false, true, "simple", true);
                                    }} else if (metaEl) {{
                                        metaEl.textContent = `Error: ${{(payload && payload.error) || "Failed to rebuild warm-up."}}`;
                                    }}
                                }} finally {{
                                    rebuildBtn.disabled = false;
                                    rebuildBtn.textContent = "Rebuild Warm-up";
                                }}
                            }});
                        }}

                        loadStories(false).then(async () => {{
                            const style = "simple";
                            const outputLanguage = getOutputLanguage();
                            const selectedModel = getCompanyJobModel();
                            const refreshJob = await fetchJobByKey(buildJobKey("company_story_update", companyName, "openai", selectedModel, style, outputLanguage, 21));
                            const rebuildJob = await fetchJobByKey(buildJobKey("company_story_rebuild", companyName, "openai", selectedModel, style, outputLanguage));
                            const job = (refreshJob && ["queued", "running"].includes(String(refreshJob.status || ""))) ? refreshJob : rebuildJob;
                            if (job && metaEl) {{
                                metaEl.textContent = formatJobText(job);
                            }}
                            if (job && ["queued", "running"].includes(String(job.status || ""))) {{
                                if (storyJobStop) storyJobStop();
                                storyJobStop = pollJob(job.job_id, (currentJob) => {{
                                    if (metaEl) metaEl.textContent = formatJobText(currentJob);
                                }}, async () => {{
                                    const cacheKey = buildCompanyStoryCacheKey(style, getOutputLanguage());
                                    delete storyCache[cacheKey];
                                    await loadStories(false, true, style, true);
                                }});
                            }}
                        }});
                    }}

                    function renderEarningsView() {{
                        contentEl.innerHTML = `
                            <div class="status-panel">
                                <div class="status-panel-header">
                                    <div class="status-header-main">
                                        <h2 style="margin:0;">Earnings Timeline</h2>
                                        <div class="status-meta" id="earnings-meta">Loading earnings...</div>
                                    </div>
                                    <div class="status-controls">
                                        <button class="status-btn" id="earnings-refresh-btn" type="button">Refresh Earnings</button>
                                    </div>
                                </div>
                                <div id="earnings-list"></div>
                            </div>
                        `;
                        const metaEl = document.getElementById("earnings-meta");
                        const listEl = document.getElementById("earnings-list");
                        const refreshBtn = document.getElementById("earnings-refresh-btn");

                        function renderEarnings(events) {{
                            if (!listEl) return;
                            if (!Array.isArray(events) || !events.length) {{
                                listEl.innerHTML = '<p class="placeholder">No earnings events available.</p>';
                                return;
                            }}
                            listEl.innerHTML = events.map((item) => {{
                                const reaction = item.price_reaction && Array.isArray(item.price_reaction.points)
                                    ? `${{item.price_reaction.points.length}} price points · ${{item.price_reaction.window_change_pct ?? "—"}}%`
                                    : "No price reaction yet";
                                return `
                                    <div class="story-card">
                                        <h3>${{item.earnings_date}}${{item.fiscal_period ? ` · ${{item.fiscal_period}}` : ""}}</h3>
                                        <div class="news-meta">EPS actual=${{item.actual_eps ?? "—"}} · estimate=${{item.estimate_eps ?? "—"}} · surprise=${{item.surprise_percent ?? "—"}}</div>
                                        <div class="news-meta">Revenue actual=${{item.actual_revenue ?? "—"}} · estimate=${{item.estimate_revenue ?? "—"}}</div>
                                        <span class="story-section-label">Price Reaction</span>
                                        <div>${{reaction}}</div>
                                        <span class="story-section-label">Analysis</span>
                                        <div>${{renderMarkdown(item.analysis_text || "")}}</div>
                                    </div>
                                `;
                            }}).join("");
                        }}

                        async function loadEarnings(refresh = false) {{
                            if (metaEl) {{
                                metaEl.textContent = refresh ? "Refreshing earnings..." : "Loading earnings...";
                            }}
                            const endpoint = refresh
                                ? `/api/company/${{encodeURIComponent(companyName)}}/earnings/refresh?output_language=${{encodeURIComponent(getOutputLanguage())}}`
                                : `/api/company/${{encodeURIComponent(companyName)}}/earnings`;
                            const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                            const payload = await response.json();
                            renderEarnings(payload.events || []);
                            if (metaEl) {{
                                metaEl.textContent = `${{(payload.events || []).length}} earnings events`;
                            }}
                        }}

                        if (refreshBtn) {{
                            refreshBtn.addEventListener("click", async () => {{
                                refreshBtn.disabled = true;
                                refreshBtn.textContent = "Refreshing...";
                                try {{
                                    await loadEarnings(true);
                                }} finally {{
                                    refreshBtn.disabled = false;
                                    refreshBtn.textContent = "Refresh Earnings";
                                }}
                            }});
                        }}

                        loadEarnings(false);
                    }}

                    function renderStockView() {{
                        const defaultRange = normalizeRangeKey(currentStockRange || "1Y");
                        const defaultModel = {default_openai_model_json};
                        const modelOptions = Array.isArray(stockModelChoices)
                            ? stockModelChoices.map((item) => {{
                                const provider = String(item.provider || "");
                                const model = String(item.model || "");
                                const selected = model === defaultModel ? "selected" : "";
                                return `<option value="${{model}}" data-provider="${{provider}}" ${{selected}}>${{provider}} · ${{model}}</option>`;
                            }}).join("")
                            : `<option value="${{defaultModel}}" data-provider="openai" selected>openai · ${{defaultModel}}</option>`;
                        contentEl.innerHTML = `
                            <div class="stock-panel">
                                <div class="status-panel-header">
                                    <div class="status-header-main">
                                        <h2 style="margin:0;">Price Intelligence</h2>
                                        <div class="stock-status" id="stock-status">Loading price series...</div>
                                    </div>
                                    <div class="stock-controls">
                                        {stock_range_buttons_html}
                                        <select class="stock-select" id="stock-analysis-model">${{modelOptions}}</select>
                                        <button class="status-btn" id="stock-analyze-btn" type="button">Analyze Moves</button>
                                    </div>
                                </div>
                                <div class="stock-chart-wrap">
                                    <canvas id="stock-chart" height="120"></canvas>
                                </div>
                                <div class="status-panel" id="price-intelligence" style="margin-top:0.9rem;">
                                    <div class="status-panel-header">
                                        <div class="status-header-main">
                                            <h2 style="margin:0;">Price Intelligence</h2>
                                            <div class="status-meta" id="price-intelligence-meta">Loading price intelligence...</div>
                                        </div>
                                        <div class="status-controls">
                                            <button class="status-btn" id="price-intelligence-refresh" type="button">Generate Price Intelligence</button>
                                        </div>
                                    </div>
                                    <div class="status-meta" id="price-intelligence-history-meta" style="margin-bottom:0.5rem;"></div>
                                    <div class="status-output" id="price-intelligence-output"></div>
                                    <div class="stock-analysis-list" id="price-intelligence-history" style="margin-top:0.85rem;"></div>
                                </div>
                                    <div class="status-panel" style="margin-top:0.9rem;">
                                        <div class="status-panel-header">
                                            <div class="status-header-main">
                                                <h2 style="margin:0;">Technical Report</h2>
                                                <div class="status-meta" id="detailed-report-meta">Loading technical report...</div>
                                        </div>
                                        <div class="status-controls">
                                            <button class="status-btn" id="detailed-report-refresh" type="button">Generate Technical Report</button>
                                            </div>
                                        </div>
                                        <div class="status-meta" id="detailed-report-history-meta" style="margin-bottom:0.5rem;"></div>
                                        <div class="status-output" id="detailed-report-output"></div>
                                        <div class="stock-analysis-list" id="detailed-report-history" style="margin-top:0.85rem;"></div>
                                    </div>
                                <div class="stock-analysis-list" id="stock-analysis-list"></div>
                            </div>
                        `;
                        const statusEl = document.getElementById("stock-status");
                        const chartEl = document.getElementById("stock-chart");
                        const analysisListEl = document.getElementById("stock-analysis-list");
                        const analyzeBtn = document.getElementById("stock-analyze-btn");
                        const modelSelect = document.getElementById("stock-analysis-model");
                        const intelligenceOutput = document.getElementById("price-intelligence-output");
                        const intelligenceMeta = document.getElementById("price-intelligence-meta");
                        const intelligenceRefresh = document.getElementById("price-intelligence-refresh");
                        const intelligenceHistoryMeta = document.getElementById("price-intelligence-history-meta");
                        const intelligenceHistory = document.getElementById("price-intelligence-history");
                        const detailedOutput = document.getElementById("detailed-report-output");
                        const detailedMeta = document.getElementById("detailed-report-meta");
                        const detailedRefresh = document.getElementById("detailed-report-refresh");
                        const detailedHistoryMeta = document.getElementById("detailed-report-history-meta");
                        const detailedHistory = document.getElementById("detailed-report-history");
                        let activeRange = defaultRange;
                        let latestSeries = [];
                        let latestTicker = "";

                        function getSelectedModel() {{
                            return modelSelect && modelSelect.value ? String(modelSelect.value) : defaultModel;
                        }}

                        function getSelectedProvider() {{
                            if (!modelSelect) return "openai";
                            const selected = modelSelect.selectedOptions && modelSelect.selectedOptions[0];
                            if (!selected) return "openai";
                            return String(selected.dataset.provider || "openai");
                        }}

                        function renderAnalysisRows(rows) {{
                            if (!analysisListEl) return;
                            if (!rows || !rows.length) {{
                                analysisListEl.innerHTML = '<p class="placeholder">Run "Analyze Moves" to generate explanations for critical points.</p>';
                                return;
                            }}
                            analysisListEl.innerHTML = rows.map((item) => {{
                                const pct = typeof item.pct_change === "number" ? `${{item.pct_change.toFixed(2)}}%` : "—";
                                const close = typeof item.close_price === "number" ? item.close_price.toFixed(2) : "—";
                                const vol = item.volume !== null && item.volume !== undefined ? String(item.volume) : "—";
                                return `
                                    <div class="stock-analysis-item">
                                        <div class="stock-analysis-meta">${{item.point_label || item.point_date_time}} · close=${{close}} · change=${{pct}} · volume=${{vol}}</div>
                                        <div>${{renderMarkdown(item.output_text || "—")}}</div>
                                    </div>
                                `;
                            }}).join("");
                        }}

                        async function loadSeries() {{
                            if (!stockChartController) return;
                            try {{
                                await stockChartController.load();
                            }} catch (_error) {{
                                renderAnalysisRows([]);
                            }}
                        }}

                        async function analyzeMoves() {{
                            if (!analyzeBtn) return;
                            analyzeBtn.disabled = true;
                            analyzeBtn.textContent = "Analyzing...";
                            try {{
                                const provider = getSelectedProvider();
                                const model = getSelectedModel();
                                const response = await fetch(
                                    `/api/company/${{encodeURIComponent(companyName)}}/stock/moves/analyze?range_key=${{encodeURIComponent(activeRange)}}&provider=${{encodeURIComponent(provider)}}&model=${{encodeURIComponent(model)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`,
                                    {{ method: "POST" }}
                                );
                                const payload = await response.json();
                                if (!response.ok || payload.error) {{
                                    if (statusEl) {{
                                        statusEl.textContent = payload.error || "Analyze failed";
                                    }}
                                    return;
                                }}
                                renderAnalysisRows(payload.analyses || []);
                            }} finally {{
                                analyzeBtn.disabled = false;
                                analyzeBtn.textContent = "Analyze Moves";
                            }}
                        }}

                        function renderPiList(items) {{
                            const rows = Array.isArray(items) ? items.filter((item) => String(item || "").trim()) : [];
                            return rows.length ? `<ul>${{rows.map((item) => `<li>${{renderMarkdown(String(item))}}</li>`).join("")}}</ul>` : "<p>—</p>";
                        }}

                        function renderPriceIntelligenceHistory(items, selectedRunId) {{
                            const rows = Array.isArray(items) ? items : [];
                            if (!rows.length) {{
                                return '<p class="placeholder">No stored runs yet.</p>';
                            }}
                            return rows.map((item) => {{
                                const runId = Number(item.id || 0);
                                const active = selectedRunId && Number(selectedRunId) === runId ? "active" : "";
                                const zone = item && item.fair_price_zone && typeof item.fair_price_zone === "object"
                                    ? `${{item.fair_price_zone.low ?? "—"}} / ${{item.fair_price_zone.mid ?? "—"}} / ${{item.fair_price_zone.high ?? "—"}}`
                                    : "—";
                                const createdAt = item.created_at ? formatDateTime(item.created_at) : "—";
                                const positionLabel = item && item.price_position && typeof item.price_position === "object"
                                    ? String(item.price_position.label || "—")
                                    : "—";
                                return `
                                    <details class="stock-history-item ${{active}}" ${{active ? "open" : ""}}>
                                        <summary class="stock-history-summary" data-run-id="${{runId}}">
                                            <span>${{escapeHtml(createdAt)}}</span>
                                            <span class="stock-history-position">${{escapeHtml(positionLabel)}}</span>
                                        </summary>
                                        <div class="stock-history-body">
                                            <div class="news-meta">as_of=${{escapeHtml(String(item.as_of_date || "—"))}} · fair_zone=${{escapeHtml(zone)}}</div>
                                            <div class="news-summary">${{escapeHtml(String(item.bottom_line || "Run " + runId))}}</div>
                                        </div>
                                    </details>
                                `;
                            }}).join("");
                        }}

                        function renderQuickPriceIntelligence(run) {{
                            const fairZone = run && typeof run.fair_price_zone === "object" ? run.fair_price_zone : {{}};
                            const pricePosition = run && typeof run.price_position === "object" ? run.price_position : {{}};
                            const technical = run && typeof run.technical_view === "object" ? run.technical_view : {{}};
                            const fundamental = run && typeof run.fundamental_market_view === "object" ? run.fundamental_market_view : {{}};
                            const synthesis = run && typeof run.synthesis_view === "object" ? run.synthesis_view : {{}};
                            const currentPrice = run && run.current_price !== null && run.current_price !== undefined ? String(run.current_price) : "—";
                            const fairZoneText = [fairZone.low, fairZone.mid, fairZone.high].map((value) => value === null || value === undefined ? "—" : String(value)).join(" / ");
                            return `
                                <div class="news-card expanded">
                                    <h3>Price Intelligence</h3>
                                    <div class="news-meta">current_price=${{escapeHtml(currentPrice)}} · fair_zone=${{escapeHtml(fairZoneText)}} · price_position=${{escapeHtml(String(pricePosition.label || "—"))}}</div>
                                    <div class="news-content">
                                        <div><strong>Bottom Line:</strong> ${{renderMarkdown(run.bottom_line || "—")}}</div>
                                        <div><strong>Fair Zone Basis:</strong> ${{renderMarkdown(fairZone.basis || "—")}}</div>
                                        <div><strong>Price Position:</strong> ${{renderMarkdown(pricePosition.explanation || "—")}}</div>
                                    </div>
                                </div>
                                <div class="stock-analysis-list">
                                    <div class="news-card expanded">
                                        <h3>Technical View</h3>
                                        <div class="news-content">
                                            <div><strong>Summary:</strong> ${{renderMarkdown(technical.summary || "—")}}</div>
                                            <div><strong>Fair Price Read:</strong> ${{renderMarkdown(technical.fair_price_read || "—")}}</div>
                                            <div><strong>Signals:</strong> ${{renderPiList(technical.signals || [])}}</div>
                                            <div><strong>Risks:</strong> ${{renderPiList(technical.risks || [])}}</div>
                                        </div>
                                    </div>
                                    <div class="news-card expanded">
                                        <h3>Fundamental / Market View</h3>
                                        <div class="news-content">
                                            <div><strong>Summary:</strong> ${{renderMarkdown(fundamental.summary || "—")}}</div>
                                            <div><strong>Fair Price Read:</strong> ${{renderMarkdown(fundamental.fair_price_read || "—")}}</div>
                                            <div><strong>Signals:</strong> ${{renderPiList(fundamental.signals || [])}}</div>
                                            <div><strong>Risks:</strong> ${{renderPiList(fundamental.risks || [])}}</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="news-card expanded">
                                    <h3>Synthesis</h3>
                                    <div class="news-content">
                                        <div><strong>Summary:</strong> ${{renderMarkdown(synthesis.summary || "—")}}</div>
                                        <div><strong>Dominant Method:</strong> ${{renderMarkdown(synthesis.dominant_method || "—")}}</div>
                                        <div><strong>Triggers:</strong> ${{renderPiList(synthesis.triggers || [])}}</div>
                                        <div><strong>Invalidations:</strong> ${{renderPiList(synthesis.invalidations || [])}}</div>
                                    </div>
                                </div>
                            `;
                        }}

                        function renderDetailedReport(status) {{
                            if (!status) return "<p>—</p>";
                            return `
                                <div class="news-card expanded">
                                    <h3>Technical Report</h3>
                                    <div class="news-content">
                                        <div>${{renderMarkdown(status.output_text || status.output_markdown || "—")}}</div>
                                    </div>
                                </div>
                            `;
                        }}

                        function renderTechnicalReportHistory(items, activeId) {{
                            const rows = Array.isArray(items) ? items : [];
                            if (rows.length <= 1) return "";
                            return rows.map((item, index) => {{
                                const snapshotId = String(item.id || "");
                                const createdAt = formatDateTime(item.created_at || "");
                                const summary = String(item.price_position_summary || item.technical_summary || "Technical report");
                                const openAttr = index === 0 || String(activeId || "") === snapshotId ? " open" : "";
                                const activeClass = String(activeId || "") === snapshotId ? " active" : "";
                                return `
                                    <details class="stock-history-item${{activeClass}}"${{openAttr}}>
                                        <summary class="stock-history-summary" data-technical-id="${{snapshotId}}">
                                            <span>${{escapeHtml(createdAt)}}</span>
                                            <span class="stock-history-position">${{escapeHtml(summary)}}</span>
                                        </summary>
                                    </details>
                                `;
                            }}).join("");
                        }}

                        async function loadTechnicalReportSnapshot(snapshotId) {{
                            const response = await fetch(`/api/company/${{encodeURIComponent(companyName)}}/status/${{encodeURIComponent(snapshotId)}}?prompt_style=simple`);
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                if (detailedMeta) detailedMeta.textContent = payload.error || "Failed to load selected technical report.";
                                return;
                            }}
                            const status = payload.status || null;
                            if (detailedOutput) detailedOutput.innerHTML = renderDetailedReport(status);
                            const detailedHistoryItems = Array.isArray(payload.history_preview) ? payload.history_preview : [];
                            if (detailedHistory) detailedHistory.innerHTML = renderTechnicalReportHistory(detailedHistoryItems, status ? status.id : null);
                            if (detailedHistoryMeta) detailedHistoryMeta.textContent = detailedHistoryItems.length > 1 ? `history=${{detailedHistoryItems.length}} runs` : "";
                            if (detailedHistory) {{
                                detailedHistory.querySelectorAll("[data-technical-id]").forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        const selectedId = btn.getAttribute("data-technical-id");
                                        if (selectedId) await loadTechnicalReportSnapshot(selectedId);
                                    }});
                                }});
                            }}
                        }}

                        async function loadPriceIntelligenceRun(runId) {{
                            const response = await fetch(`/api/company/${{encodeURIComponent(companyName)}}/price-intelligence/${{encodeURIComponent(runId)}}`);
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                if (intelligenceMeta) intelligenceMeta.textContent = payload.error || "Failed to load selected run.";
                                return;
                            }}
                            const run = payload.run || null;
                            if (intelligenceOutput) intelligenceOutput.innerHTML = renderQuickPriceIntelligence(run);
                            if (intelligenceHistory) intelligenceHistory.innerHTML = renderPriceIntelligenceHistory(payload.history_preview || [], run ? run.id : null);
                            if (intelligenceHistoryMeta) intelligenceHistoryMeta.textContent = `history=${{Array.isArray(payload.history_preview) ? payload.history_preview.length : 0}} runs`;
                            if (intelligenceMeta && run) {{
                                intelligenceMeta.textContent = `as_of=${{run.as_of_date || "—"}} · created=${{formatDateTime(run.created_at || "")}} · provider=${{run.provider || "—"}} · model=${{run.model || "—"}} · windows=${{run.context_window_days || 730}}d/${{run.focus_window_days || 60}}d`;
                            }}
                            if (intelligenceHistory) {{
                                intelligenceHistory.querySelectorAll("[data-run-id]").forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        const selectedRunId = btn.getAttribute("data-run-id");
                                        if (selectedRunId) await loadPriceIntelligenceRun(selectedRunId);
                                    }});
                                }});
                            }}
                        }}

                        async function loadPriceIntelligence(forceGenerate = false) {{
                            const selectedModel = getCompanyJobModel();
                            const endpoint = forceGenerate
                                ? `/api/company/${{encodeURIComponent(companyName)}}/price-intelligence/generate?output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(selectedModel)}}`
                                : `/api/company/${{encodeURIComponent(companyName)}}/price-intelligence`;
                            const response = await fetch(endpoint, {{ method: forceGenerate ? "POST" : "GET" }});
                            const payload = await response.json();
                            const run = payload.run || null;
                            if (!run) {{
                                if (intelligenceOutput) intelligenceOutput.innerHTML = "<p>—</p>";
                                if (intelligenceHistory) intelligenceHistory.innerHTML = renderPriceIntelligenceHistory(payload.history_preview || [], null);
                                if (intelligenceHistoryMeta) intelligenceHistoryMeta.textContent = `history=${{Array.isArray(payload.history_preview) ? payload.history_preview.length : 0}} runs`;
                                if (intelligenceMeta) intelligenceMeta.textContent = payload.job ? formatJobText(payload.job) : "No price intelligence available yet.";
                                if (payload.job && intelligenceRefresh) {{
                                    const running = ["queued", "running"].includes(String(payload.job.status || ""));
                                    intelligenceRefresh.disabled = running;
                                    intelligenceRefresh.textContent = running ? "Generating..." : "Generate Price Intelligence";
                                }}
                                return;
                            }}
                            if (intelligenceOutput) intelligenceOutput.innerHTML = renderQuickPriceIntelligence(run);
                            if (intelligenceHistory) intelligenceHistory.innerHTML = renderPriceIntelligenceHistory(payload.history_preview || [], run.id || null);
                            if (intelligenceHistoryMeta) intelligenceHistoryMeta.textContent = `history=${{Array.isArray(payload.history_preview) ? payload.history_preview.length : 0}} runs`;
                            if (intelligenceHistory) {{
                                intelligenceHistory.querySelectorAll("[data-run-id]").forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        const selectedRunId = btn.getAttribute("data-run-id");
                                        if (selectedRunId) await loadPriceIntelligenceRun(selectedRunId);
                                    }});
                                }});
                            }}
                            if (intelligenceMeta) {{
                                const coverage = run && run.input_payload && run.input_payload.input_coverage
                                    ? run.input_payload.input_coverage
                                    : null;
                                const coverageText = coverage
                                    ? `daily_reports=${{coverage.daily_report_count || 0}} · fallback_news=${{coverage.raw_news_fallback_count || 0}}`
                                    : "";
                                intelligenceMeta.textContent = payload.job
                                    ? formatJobText(payload.job)
                                    : `as_of=${{run.as_of_date || "—"}} · created=${{formatDateTime(run.created_at || "")}} · provider=${{run.provider || "—"}} · model=${{run.model || "—"}} · windows=${{run.context_window_days || 730}}d/${{run.focus_window_days || 60}}d${{coverageText ? " · " + coverageText : ""}}`;
                            }}
                            if (payload.job && intelligenceRefresh) {{
                                const running = ["queued", "running"].includes(String(payload.job.status || ""));
                                intelligenceRefresh.disabled = running;
                                intelligenceRefresh.textContent = running ? "Generating..." : "Generate Price Intelligence";
                                if (running) {{
                                    if (priceIntelligenceJobStop) priceIntelligenceJobStop();
                                    priceIntelligenceJobStop = pollJob(payload.job.job_id, (job) => {{
                                        if (intelligenceMeta) intelligenceMeta.textContent = formatJobText(job);
                                        const stillRunning = job && ["queued", "running"].includes(String(job.status || ""));
                                        intelligenceRefresh.disabled = !!stillRunning;
                                        intelligenceRefresh.textContent = stillRunning ? "Generating..." : "Generate Price Intelligence";
                                    }}, async () => {{
                                        await loadPriceIntelligence(false);
                                    }});
                                }}
                            }}
                        }}

                        async function loadDetailedReport(forceGenerate = false) {{
                            const selectedModel = getCompanyJobModel();
                            const endpoint = forceGenerate
                                ? `/api/company/${{encodeURIComponent(companyName)}}/status/generate?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(selectedModel)}}`
                                : `/api/company/${{encodeURIComponent(companyName)}}/status?prompt_style=simple&model=${{encodeURIComponent(selectedModel)}}`;
                            const response = await fetch(endpoint, {{ method: forceGenerate ? "POST" : "GET" }});
                            const payload = await response.json();
                            const status = payload.status || null;
                            if (detailedOutput) detailedOutput.innerHTML = renderDetailedReport(status);
                            const detailedHistoryItems = Array.isArray(payload.history_preview) ? payload.history_preview : [];
                            if (detailedHistory) detailedHistory.innerHTML = renderTechnicalReportHistory(detailedHistoryItems, status ? status.id : null);
                            if (detailedHistoryMeta) detailedHistoryMeta.textContent = detailedHistoryItems.length > 1 ? `history=${{detailedHistoryItems.length}} runs` : "";
                            if (detailedHistory) {{
                                detailedHistory.querySelectorAll("[data-technical-id]").forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        const selectedId = btn.getAttribute("data-technical-id");
                                        if (selectedId) await loadTechnicalReportSnapshot(selectedId);
                                    }});
                                }});
                            }}
                            if (detailedMeta) {{
                                if (!status) {{
                                    detailedMeta.textContent = payload.job ? formatJobText(payload.job) : "No technical report available yet.";
                                }} else {{
                                    const coverage = status && status.input_payload && status.input_payload.input_coverage
                                        ? status.input_payload.input_coverage
                                        : null;
                                    const coverageText = coverage
                                        ? `price_points=${{coverage.price_point_count || 0}} · recent_points=${{coverage.recent_point_count || 0}}`
                                        : "";
                                    detailedMeta.textContent = payload.job
                                        ? formatJobText(payload.job)
                                        : `as_of=${{status.as_of_date || "—"}} · provider=${{status.provider || "—"}} · model=${{status.model || "—"}}${{coverageText ? " · " + coverageText : ""}}`;
                                }}
                            }}
                            if (payload.job && detailedRefresh) {{
                                const running = ["queued", "running"].includes(String(payload.job.status || ""));
                                detailedRefresh.disabled = running;
                                detailedRefresh.textContent = running ? "Generating..." : "Generate Technical Report";
                                if (running) {{
                                    if (priceIntelligenceDetailJobStop) priceIntelligenceDetailJobStop();
                                    priceIntelligenceDetailJobStop = pollJob(payload.job.job_id, (job) => {{
                                        if (detailedMeta) detailedMeta.textContent = formatJobText(job);
                                        const stillRunning = job && ["queued", "running"].includes(String(job.status || ""));
                                        detailedRefresh.disabled = !!stillRunning;
                                        detailedRefresh.textContent = stillRunning ? "Generating..." : "Generate Technical Report";
                                    }}, async () => {{
                                        await loadDetailedReport(false);
                                    }});
                                }}
                            }}
                        }}

                        if (stockChartController) {{
                            stockChartController.destroy();
                            stockChartController = null;
                        }}
                        stockChartController = window.MarketAgentStockChart.createController({{
                            companyName,
                            controlsEl: contentEl.querySelector(".stock-controls"),
                            statusEl,
                            chartEl,
                            initialRange: activeRange,
                            onLoaded(payload, points) {{
                                latestSeries = Array.isArray(points) ? points : [];
                                latestTicker = String((payload && payload.ticker) || "");
                                renderAnalysisRows([]);
                            }},
                            onError() {{
                                latestSeries = [];
                                latestTicker = "";
                                renderAnalysisRows([]);
                            }},
                            onRangeChange(rangeKey) {{
                                activeRange = normalizeRangeKey(rangeKey);
                                currentStockRange = activeRange;
                                updateUrlState({{
                                    viewMode: "stock",
                                    stockRange: currentStockRange,
                                }});
                            }},
                        }});
                        if (analyzeBtn) {{
                            analyzeBtn.addEventListener("click", analyzeMoves);
                        }}
                        if (intelligenceRefresh) {{
                            intelligenceRefresh.addEventListener("click", async () => {{
                                await loadPriceIntelligence(true);
                            }});
                        }}
                        if (detailedRefresh) {{
                            detailedRefresh.addEventListener("click", async () => {{
                                await loadDetailedReport(true);
                            }});
                        }}
                        loadSeries();
                        loadPriceIntelligence(false).then(async () => {{
                            const job = await fetchJobByKey(buildJobKey("price_intelligence", companyName, "openai", getCompanyJobModel(), getOutputLanguage()));
                            if (job && intelligenceMeta) {{
                                intelligenceMeta.textContent = formatJobText(job);
                            }}
                            if (job && intelligenceRefresh && ["queued", "running"].includes(String(job.status || ""))) {{
                                intelligenceRefresh.disabled = true;
                                intelligenceRefresh.textContent = "Generating...";
                                if (priceIntelligenceJobStop) priceIntelligenceJobStop();
                                priceIntelligenceJobStop = pollJob(job.job_id, (currentJob) => {{
                                    if (intelligenceMeta) intelligenceMeta.textContent = formatJobText(currentJob);
                                }}, async () => {{
                                    await loadPriceIntelligence(false);
                                }});
                            }}
                        }});
                        loadDetailedReport(false).then(async () => {{
                            const job = await fetchJobByKey(buildJobKey("detailed_report", companyName, "openai", getCompanyJobModel(), getOutputLanguage(), 30));
                            if (job && detailedMeta) {{
                                detailedMeta.textContent = formatJobText(job);
                            }}
                            if (job && detailedRefresh && ["queued", "running"].includes(String(job.status || ""))) {{
                                detailedRefresh.disabled = true;
                                detailedRefresh.textContent = "Generating...";
                                if (priceIntelligenceDetailJobStop) priceIntelligenceDetailJobStop();
                                priceIntelligenceDetailJobStop = pollJob(job.job_id, (currentJob) => {{
                                    if (detailedMeta) detailedMeta.textContent = formatJobText(currentJob);
                                }}, async () => {{
                                    await loadDetailedReport(false);
                                }});
                            }}
                        }});
                    }}

                    function renderIndicatorRows(rows) {{
                        if (!Array.isArray(rows) || !rows.length) {{
                            return '<p class="placeholder">No indicator rows.</p>';
                        }}
                        const formatCellValue = (value) => {{
                            if (value === null || value === undefined) {{
                                return "—";
                            }}
                            if (typeof value === "object") {{
                                return `<pre>${{escapeHtml(JSON.stringify(value, null, 2))}}</pre>`;
                            }}
                            return escapeHtml(String(value));
                        }};
                        const body = rows.map((row) => `
                            <tr>
                                <th>${{escapeHtml(String(row.label || ""))}}</th>
                                <td>${{formatCellValue(row.value)}}</td>
                            </tr>
                        `).join("");
                        return `<table class="indicator-table">${{body}}</table>`;
                    }}

                    function renderIndicatorsView() {{
                        const defaultModel = (Array.isArray(indicatorModels) && indicatorModels.length)
                            ? String(indicatorModels[0])
                            : "gpt-4o-mini";
                        const modelOptions = (Array.isArray(indicatorModels) && indicatorModels.length
                            ? indicatorModels
                            : [defaultModel]
                        ).map((model) => `
                            <option value="${{escapeHtml(String(model))}}">${{escapeHtml(String(model))}}</option>
                        `).join("");
                        contentEl.innerHTML = `
                            <div class="status-panel">
                                <div class="status-panel-header">
                                    <div class="status-header-main">
                                        <h2 style="margin:0;">Indicators</h2>
                                        <div class="status-meta" id="indicators-meta">Loading indicators...</div>
                                    </div>
                                    <div class="status-controls">
                                        <select class="status-select" id="indicators-model">${{modelOptions}}</select>
                                        <button class="status-btn" id="indicators-analyze-btn" type="button">Analyze Indicators</button>
                                    </div>
                                </div>
                                <div id="indicators-sections"></div>
                            </div>
                        `;
                        const sectionsEl = document.getElementById("indicators-sections");
                        const metaEl = document.getElementById("indicators-meta");
                        const modelEl = document.getElementById("indicators-model");
                        const analyzeBtn = document.getElementById("indicators-analyze-btn");
                        let sections = [];

                        function renderSections(analysisBySection = null) {{
                            if (!sectionsEl) return;
                            if (!Array.isArray(sections) || !sections.length) {{
                                sectionsEl.innerHTML = '<p class="placeholder">No indicator data available.</p>';
                                return;
                            }}
                            sectionsEl.innerHTML = sections.map((section) => {{
                                const sectionName = String(section.name || "");
                                const sectionAnalysis = analysisBySection && analysisBySection[sectionName]
                                    ? analysisBySection[sectionName]
                                    : null;
                                const analysisCards = sectionAnalysis
                                    ? `
                                        <div class="indicator-analysis-grid">
                                            <div class="indicator-analysis-card">
                                                <h4>Summary</h4>
                                                <div>${{renderMarkdown(sectionAnalysis.summary || "—")}}</div>
                                            </div>
                                            <div class="indicator-analysis-card">
                                                <h4>Highlights</h4>
                                                <div>${{Array.isArray(sectionAnalysis.highlights) && sectionAnalysis.highlights.length ? `<ul>${{sectionAnalysis.highlights.map((x) => `<li>${{escapeHtml(String(x))}}</li>`).join("")}}</ul>` : "—"}}</div>
                                            </div>
                                            <div class="indicator-analysis-card">
                                                <h4>Risks</h4>
                                                <div>${{Array.isArray(sectionAnalysis.risks) && sectionAnalysis.risks.length ? `<ul>${{sectionAnalysis.risks.map((x) => `<li>${{escapeHtml(String(x))}}</li>`).join("")}}</ul>` : "—"}}</div>
                                            </div>
                                            <div class="indicator-analysis-card">
                                                <h4>Questions</h4>
                                                <div>${{Array.isArray(sectionAnalysis.questions) && sectionAnalysis.questions.length ? `<ul>${{sectionAnalysis.questions.map((x) => `<li>${{escapeHtml(String(x))}}</li>`).join("")}}</ul>` : "—"}}</div>
                                            </div>
                                        </div>
                                      `
                                    : "";
                                return `
                                    <div class="indicator-section" data-section-name="${{escapeHtml(sectionName)}}">
                                        <h3>${{escapeHtml(sectionName)}}</h3>
                                        ${{renderIndicatorRows(section.rows || [])}}
                                        ${{analysisCards}}
                                    </div>
                                `;
                            }}).join("");
                        }}

                        async function loadIndicators() {{
                            if (metaEl) {{
                                metaEl.textContent = "Loading indicators...";
                            }}
                            const response = await fetch(`/api/company/${{encodeURIComponent(companyName)}}/indicators`);
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                if (metaEl) {{
                                    metaEl.textContent = payload.error || "Failed to load indicators";
                                }}
                                sections = [];
                                renderSections(null);
                                return;
                            }}
                            sections = Array.isArray(payload.sections) ? payload.sections : [];
                            if (metaEl) {{
                                metaEl.textContent = `ticker=${{payload.ticker || "—"}} · ${{sections.length}} sections`;
                            }}
                            renderSections(null);
                        }}

                        async function analyzeIndicators() {{
                            if (!analyzeBtn) return;
                            const selectedModel = modelEl && modelEl.value ? String(modelEl.value) : defaultModel;
                            analyzeBtn.disabled = true;
                            analyzeBtn.textContent = "Analyzing...";
                            try {{
                                const response = await fetch(
                                    `/api/company/${{encodeURIComponent(companyName)}}/indicators/analyze?provider=openai&model=${{encodeURIComponent(selectedModel)}}`,
                                    {{ method: "POST" }}
                                );
                                const payload = await response.json();
                                if (!response.ok || payload.error) {{
                                    if (metaEl) {{
                                        metaEl.textContent = payload.error || "Analyze failed";
                                    }}
                                    return;
                                }}
                                const sectionResults = payload.analysis && payload.analysis.sections
                                    ? payload.analysis.sections
                                    : null;
                                renderSections(sectionResults);
                                if (metaEl) {{
                                    metaEl.textContent = `ticker=${{payload.ticker || "—"}} · model=${{payload.model || selectedModel}}`;
                                }}
                            }} finally {{
                                analyzeBtn.disabled = false;
                                analyzeBtn.textContent = "Analyze Indicators";
                            }}
                        }}

                        if (analyzeBtn) {{
                            analyzeBtn.addEventListener("click", analyzeIndicators);
                        }}
                        loadIndicators();
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
                        const dailyReport = isDaily ? (group.daily_report || null) : null;
                        const dailyClusters = isDaily && Array.isArray(group.daily_clusters) ? group.daily_clusters : [];
                        const dailyReportHtml = isDaily
                            ? (dailyReport
                                ? `<div class="daily-report-card">
                                    <div class="daily-report-meta">Daily report · ${{dailyReport.created_at || ""}} · provider=${{dailyReport.provider}} · model=${{dailyReport.model}} · prompt=${{dailyReport.prompt_style}}</div>
                                    <div class="daily-report-output">${{renderMarkdown(dailyReport.output_text || "")}}</div>
                                   </div>`
                                : `<div class="daily-report-card">
                                    <div class="daily-report-meta">No daily report yet for this day.</div>
                                   </div>`)
                            : "";
                        const dailyClusterHtml = isDaily
                            ? (dailyClusters.length
                                ? `<div class="daily-report-card">
                                    <div class="daily-report-meta">Daily clusters · ${{dailyClusters.length}} clusters</div>
                                    <div class="daily-report-output"><ul>${{dailyClusters.map((cluster) => `<li><strong>${{escapeHtml(cluster.cluster_title || "")}}</strong> · ${{escapeHtml(cluster.cluster_summary || "")}}</li>`).join("")}}</ul></div>
                                   </div>`
                                : `<div class="daily-report-card"><div class="daily-report-meta">No daily clusters yet for this day.</div></div>`)
                            : "";
                        const header = isDaily
                            ? `
                                <div class="day-group-header">
                                    <h2>${{label}}</h2>
                                    <div class="day-group-right">
                                        ${{filterableCount > 0
                                        ? `<div class="day-analyze-controls">
                                                <button class="day-analyze-btn" id="day-analyze-btn" type="button">Daily Report</button>
                                                <span class="day-analyze-result" id="day-analyze-result"></span>
                                           </div>`
                                        : `<span class="day-note">No items for day actions</span>`}}
                                        <span class="day-total-count">${{totalCountLabel}}</span>
                                    </div>
                                </div>
                            `
                            : `<h2>${{label}}</h2>`;
                        contentEl.innerHTML = header + dailyReportHtml + dailyClusterHtml + items.map(buildNewsCard).join("");
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
                                const removeUrl =
                                    `/api/company/${{encodeURIComponent(companyName)}}/news/${{newsId}}` +
                                    `?output_language=${{encodeURIComponent(getOutputLanguage())}}`;
                                await fetch(removeUrl, {{
                                    method: "DELETE",
                                }});
                                loadNews();
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
                                    const removeUrl =
                                        `/api/company/${{encodeURIComponent(companyName)}}/news/${{newsId}}` +
                                        `?output_language=${{encodeURIComponent(getOutputLanguage())}}`;
                                    await fetch(removeUrl, {{
                                        method: "DELETE",
                                    }});
                                    loadNews();
                                }} finally {{
                                    actionButton.disabled = false;
                                    actionButton.textContent = "Remove";
                                }}
                            }});
                        }});
                        contentEl.querySelectorAll(".news-action-btn.create-story").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = event.target.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                const item = items.find((entry) => String(entry.id) === String(newsId));
                                if (!item || !dayDate) return;
                                const storyTitle = window.prompt("Story title", item.news_title || "");
                                if (!storyTitle) return;
                                await fetch(
                                    `/api/company/${{encodeURIComponent(companyName)}}/stories/create-from-news?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(getCompanyJobModel())}}`,
                                    {{
                                        method: "POST",
                                        headers: {{ "Content-Type": "application/json" }},
                                        body: JSON.stringify({{ target_date: dayDate, story_title: storyTitle, news_item: item }}),
                                    }}
                                );
                                delete storyCache[buildCompanyStoryCacheKey("simple", getOutputLanguage())];
                            }});
                        }});
                        contentEl.querySelectorAll(".news-action-btn.attach-story").forEach((button) => {{
                            button.addEventListener("click", async (event) => {{
                                event.stopPropagation();
                                const card = event.target.closest(".news-card");
                                const newsId = card ? card.dataset.newsId : null;
                                const item = items.find((entry) => String(entry.id) === String(newsId));
                                if (!item || !dayDate) return;
                                const cachedStories = storyCache[buildCompanyStoryCacheKey("simple", getOutputLanguage())];
                                const storyOptions = cachedStories && Array.isArray(cachedStories.stories) ? cachedStories.stories : [];
                                if (!storyOptions.length) {{
                                    await fetchStoryList("simple", false, true);
                                }}
                                const latestStories = storyCache[buildCompanyStoryCacheKey("simple", getOutputLanguage())];
                                const options = latestStories && Array.isArray(latestStories.stories) ? latestStories.stories : [];
                                const keyHint = window.prompt(
                                    "Attach to story key",
                                    options.map((story) => `${{story.story_key}}: ${{story.story_title}}`).join("\\n")
                                );
                                if (!keyHint) return;
                                const targetKey = String(keyHint.split(":")[0] || "").trim();
                                if (!targetKey) return;
                                await fetch(
                                    `/api/company/${{encodeURIComponent(companyName)}}/stories/${{encodeURIComponent(targetKey)}}/attach-news?prompt_style=simple&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(getCompanyJobModel())}}`,
                                    {{
                                        method: "POST",
                                        headers: {{ "Content-Type": "application/json" }},
                                        body: JSON.stringify({{ target_date: dayDate, news_item: item }}),
                                    }}
                                );
                                delete storyCache[buildCompanyStoryCacheKey("simple", getOutputLanguage())];
                            }});
                        }});
                        const dayAnalyzeBtn = document.getElementById("day-analyze-btn");
                        const dayAnalyzeResult = document.getElementById("day-analyze-result");
                        if (dayAnalyzeBtn && dayDate) {{
                            dayAnalyzeBtn.addEventListener("click", async () => {{
                                if (filterableCount <= 0) {{
                                    if (dayAnalyzeResult) {{
                                        dayAnalyzeResult.textContent = "No news for daily report";
                                    }}
                                    return;
                                }}
                                const dayAnalyzeStart = Date.now();
                                dayAnalyzeBtn.disabled = true;
                                dayAnalyzeBtn.textContent = "Generating...";
                                if (dayAnalyzeResult) {{
                                    dayAnalyzeResult.textContent = "";
                                }}
                                try {{
                                    const url =
                                        `/api/company/${{encodeURIComponent(companyName)}}/news/summarize/day` +
                                        `?date=${{encodeURIComponent(dayDate)}}` +
                                        `&output_language=${{encodeURIComponent(getOutputLanguage())}}` +
                                        `&model=${{encodeURIComponent(getCompanyJobModel())}}`;
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
                                        dayAnalyzeResult.textContent = `${{analyzed ? "daily report updated" : "no report"}} · ${{processed}} items · ${{elapsedSec}}s`;
                                    }}
                                }} finally {{
                                    dayAnalyzeBtn.disabled = false;
                                    dayAnalyzeBtn.textContent = "Daily Report";
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
                                        const url = `/api/company/${{encodeURIComponent(companyName)}}/report?week_date=${{encodeURIComponent(startDate)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`;
                                        const fullUrl = `${{url}}&model=${{encodeURIComponent(getCompanyJobModel())}}`;
                                        const response = await fetch(fullUrl, {{ method: "POST" }});
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
                                    const url = `/api/company/${{encodeURIComponent(companyName)}}/report?week_date=${{encodeURIComponent(startDate)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}`;
                                    const response = await fetch(`${{url}}&model=${{encodeURIComponent(getCompanyJobModel())}}`, {{ method: "POST" }});
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

                    function renderMonthlyReport(report, label, startDate, endDate, items) {{
                        if (!report) {{
                            contentEl.innerHTML = `
                                <h2>${{label}}</h2>
                                <div class="news-meta">${{startDate}} → ${{endDate}}</div>
                                <div class="news-card expanded">
                                    <div class="news-content">
                                        <p class="placeholder">No monthly report available.</p>
                                        <button class="refresh-btn" id="generate-monthly-report-btn" type="button">
                                            Generate monthly report
                                        </button>
                                    </div>
                                </div>
                            `;
                            const button = document.getElementById("generate-monthly-report-btn");
                            if (button) {{
                                button.addEventListener("click", async () => {{
                                    button.disabled = true;
                                    button.textContent = "Generating...";
                                    try {{
                                        const month = String(startDate || "").slice(0, 7);
                                        const url = `/api/company/${{encodeURIComponent(companyName)}}/report/month?month=${{encodeURIComponent(month)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(getCompanyJobModel())}}`;
                                        const response = await fetch(url, {{ method: "POST" }});
                                        const payload = await response.json();
                                        const groups = payload.groups || [];
                                        if (groups.length) {{
                                            allGroups = groups;
                                            renderTimeline(getFilteredGroups());
                                        }}
                                    }} finally {{
                                        button.disabled = false;
                                        button.textContent = "Generate monthly report";
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
                            .map(([title, values]) => {{
                                if (!values || !values.length) {{
                                    return `<div><strong>${{title}}:</strong> —</div>`;
                                }}
                                const rows = values
                                    .map((entry) => stripBullet(entry))
                                    .map((entry) => `<li>${{entry}}</li>`)
                                    .join("");
                                return `<div><strong>${{title}}:</strong><ul>${{rows}}</ul></div>`;
                            }})
                            .join("");
                        const sourceRows = (items || [])
                            .filter((entry) => entry && entry.news_date_time)
                            .map((entry) => `<li>${{String(entry.news_date_time).slice(0, 10)}} — ${{entry.news_title || "Weekly report"}}</li>`)
                            .join("");
                        const sourcesBlock = sourceRows
                            ? `<div><strong>Weekly Inputs:</strong><ul>${{sourceRows}}</ul></div>`
                            : "";
                        contentEl.innerHTML = `
                            <div class="header-row">
                                <h2>${{label}}</h2>
                                <button class="refresh-btn" id="rebuild-monthly-report-btn" type="button">Rebuild monthly report</button>
                            </div>
                            <div class="news-meta">${{startDate}} → ${{endDate}}</div>
                            <div class="news-card expanded">
                                <div class="news-content">
                                    ${{body}}
                                    ${{sourcesBlock}}
                                </div>
                            </div>
                        `;
                        const rebuildBtn = document.getElementById("rebuild-monthly-report-btn");
                        if (rebuildBtn) {{
                            rebuildBtn.addEventListener("click", async () => {{
                                rebuildBtn.disabled = true;
                                rebuildBtn.textContent = "Rebuilding...";
                                try {{
                                    const month = String(startDate || "").slice(0, 7);
                                    const url = `/api/company/${{encodeURIComponent(companyName)}}/report/month?month=${{encodeURIComponent(month)}}&output_language=${{encodeURIComponent(getOutputLanguage())}}&model=${{encodeURIComponent(getCompanyJobModel())}}`;
                                    const response = await fetch(url, {{ method: "POST" }});
                                    const payload = await response.json();
                                    const groups = payload.groups || [];
                                    if (groups.length) {{
                                        allGroups = groups;
                                        renderTimeline(getFilteredGroups());
                                    }}
                                }} finally {{
                                    rebuildBtn.disabled = false;
                                    rebuildBtn.textContent = "Rebuild monthly report";
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
                            updateUrlState({{
                                viewMode: currentViewMode,
                                groupKey: selectedGroupKey,
                            }});
                            return;
                        }}
                        if (group.type === "monthly") {{
                            renderMonthlyReport(
                                group.report,
                                group.label,
                                group.report_start,
                                group.report_end,
                                group.items
                            );
                            selectedGroupKey = group.key;
                            updateUrlState({{
                                viewMode: currentViewMode,
                                groupKey: selectedGroupKey,
                            }});
                            return;
                        }}
                        renderNews(group.items || [], group.label, group);
                        selectedGroupKey = group.key;
                        updateUrlState({{
                            viewMode: currentViewMode,
                            groupKey: selectedGroupKey,
                        }});
                    }}

                    function renderTimeline(groups) {{
                        timelineEl.innerHTML = "";
                        if (!groups || !groups.length) {{
                            timelineEl.innerHTML = '<p class="placeholder">No items for this view.</p>';
                            contentEl.innerHTML = '<p class="placeholder">No items for this view.</p>';
                            return;
                        }}
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
                        const response = await fetch(
                            `/api/company/${{encodeURIComponent(companyName)}}/news?output_language=${{encodeURIComponent(getOutputLanguage())}}`
                        );
                        const payload = await response.json();
                        const groups = payload.groups || [];
                        allGroups = groups;
                        if (!groups.length) {{
                            timelineEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            contentEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            return;
                        }}
                        setViewMode(currentViewMode || "daily");
                    }}

                    async function refreshNews() {{
                        refreshBtn.disabled = true;
                        const start = Date.now();
                        refreshBtn.textContent = "Refreshing...";
                        try {{
                            let url = `/api/company/${{encodeURIComponent(companyName)}}/refresh`;
                            if (!currentWeekStart || !currentWeekEnd) {{
                                alert("Please select a week.");
                                return;
                            }}
                            url += `?start_date=${{encodeURIComponent(fmtDate(currentWeekStart))}}&end_date=${{encodeURIComponent(fmtDate(currentWeekEnd))}}`;
                            if (sourceSelect && sourceSelect.value) {{
                                const joiner = url.includes("?") ? "&" : "?";
                                url += `${{joiner}}source=${{encodeURIComponent(sourceSelect.value)}}`;
                            }}
                            const joiner = url.includes("?") ? "&" : "?";
                            url += `${{joiner}}output_language=${{encodeURIComponent(getOutputLanguage())}}`;
                            url += `&model=${{encodeURIComponent(getCompanyJobModel())}}`;
                            const response = await fetch(url, {{
                                method: "POST",
                            }});
                            const payload = await response.json();
                            const fetchedTotal = Number(payload.fetched_total || 0);
                            const filteredOut = Number(payload.filtered_out || 0);
                            const groups = payload.groups || [];
                            allGroups = groups;
                            if (!groups.length) {{
                                timelineEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                                contentEl.innerHTML = '<p class="placeholder">No news yet.</p>';
                            }} else {{
                                setViewMode(currentViewMode || "daily");
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


                    if (viewTabsEl) {{
                        viewTabsEl.querySelectorAll(".view-tab").forEach((button) => {{
                            button.addEventListener("click", () => {{
                                setViewMode(button.dataset.viewMode || "daily");
                            }});
                        }});
                    }}
                    initOutputLanguage();
                    initCompanyJobModel();
                    if (sourceSelect) {{
                        sourceSelect.value = initialUrlState.source || "finnhub";
                        sourceSelect.addEventListener("change", () => updateUrlState({{
                            viewMode: currentViewMode,
                            groupKey: selectedGroupKey,
                            stockRange: currentStockRange,
                        }}));
                    }}
                    refreshBtn.addEventListener("click", refreshNews);
                    function syncWeekLabel() {{
                        if (!currentWeekStart || !currentWeekEnd) return;
                        rangeInput.value = `Week of ${{fmtDate(currentWeekStart)}}`;
                        rangeInput.title = `${{fmtDate(currentWeekStart)}} ~ ${{fmtDate(currentWeekEnd)}}`;
                    }}
                    function setWeekFromDate(d) {{
                        const [ws, we] = weekBoundaries(d);
                        currentWeekStart = ws;
                        currentWeekEnd = we;
                        syncWeekLabel();
                    }}
                    if (window.flatpickr) {{
                        const today = new Date();
                        setWeekFromDate(today);
                        const fp = window.flatpickr(rangeInput, {{
                            dateFormat: "Y-m-d",
                            locale: {{ firstDayOfWeek: 6 }},
                            maxDate: "today",
                            onChange: function(selectedDates) {{
                                if (!selectedDates || !selectedDates.length) return;
                                setWeekFromDate(selectedDates[0]);
                                updateUrlState({{
                                    viewMode: currentViewMode,
                                    groupKey: selectedGroupKey,
                                    stockRange: currentStockRange,
                                }});
                            }},
                        }});
                        if (initialUrlState.dateRange) {{
                            const parsed = initialUrlState.dateRange.replace(/^Week of /, "").replace(/ to .*/, "").trim();
                            if (parsed) {{
                                const restored = new Date(parsed + "T00:00:00");
                                if (!isNaN(restored.getTime())) {{
                                    setWeekFromDate(restored);
                                    fp.setDate(restored, false);
                                }}
                            }}
                        }}
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
                        const trimmed = entry.trimStart();
                        if (
                            trimmed.startsWith("- ") ||
                            trimmed.startsWith("• ") ||
                            trimmed.startsWith("* ")
                        ) {{
                            return trimmed.slice(2);
                        }}
                        return trimmed;
                    }}
                </script>
            </body>
        </html>
    """
