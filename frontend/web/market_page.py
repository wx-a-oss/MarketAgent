"""Market overview page rendering."""

from __future__ import annotations

import json
from typing import Dict, List

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


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
                </style>
            </head>
            <body class="report">
                {render_nav("market")}
                <div class="container">
                    <section class="card">
                        <div class="section-title">
                            <h1>Today's Market</h1>
                            <div class="controls">
                                <input id="market-date" class="date-input" type="text" />
                                <button id="refresh-market" class="refresh-btn" type="button">Refresh</button>
                                <span id="market-status" class="status"></span>
                            </div>
                        </div>
                        <p class="status">Pick a date to view that day's market news and summaries. Auto refresh runs during U.S. market hours.</p>
                    </section>

                    <div id="market-sections"></div>

                    <section class="card">
                        <div class="section-title">
                            <h2 style="margin:0;">Top Market News (Today)</h2>
                            <span id="market-news-count" class="status"></span>
                        </div>
                        <div class="summary-controls">
                            <select id="summary-prompt">
                                <option value="simple" selected>simple</option>
                                <option value="structured">structured</option>
                            </select>
                            <button id="analyze-news" class="analyze-btn" type="button">Analyze All</button>
                            <span id="summary-status" class="summary-status"></span>
                        </div>
                        <div id="news-summaries"></div>
                        <div id="market-news" class="news-list"></div>
                    </section>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    const singleNewsModels = {model_choices_json};
                    const refreshBtn = document.getElementById("refresh-market");
                    const dateInput = document.getElementById("market-date");
                    const statusEl = document.getElementById("market-status");
                    const marketSectionsEl = document.getElementById("market-sections");
                    const summaryPrompt = document.getElementById("summary-prompt");
                    const summaryLanguage = document.getElementById("global-language-select");
                    const analyzeBtn = document.getElementById("analyze-news");
                    const summaryStatus = document.getElementById("summary-status");
                    const summariesEl = document.getElementById("news-summaries");
                    const marketNewsCountEl = document.getElementById("market-news-count");
                    let latestNews = [];
                    function readUrlState() {{
                        const params = new URLSearchParams(window.location.search || "");
                        const prompt = String(params.get("prompt") || "").trim().toLowerCase();
                        const lang = String(params.get("lang") || "").trim();
                        const date = String(params.get("date") || "").trim();
                        return {{
                            prompt: prompt === "structured" ? "structured" : "simple",
                            lang: lang === "en" ? "en" : "zh-CN",
                            date,
                        }};
                    }}
                    function updateUrlState() {{
                        const url = new URL(window.location.href);
                        const params = url.searchParams;
                        params.set("date", selectedDate);
                        if (summaryPrompt) {{
                            const prompt = String(summaryPrompt.value || "simple").toLowerCase();
                            params.set("prompt", prompt === "structured" ? "structured" : "simple");
                        }}
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
                    let datePicker = null;

                    function getOutputLanguage() {{
                        const selected = summaryLanguage && summaryLanguage.value
                            ? String(summaryLanguage.value)
                            : "zh-CN";
                        return selected || "zh-CN";
                    }}

                    function renderRichText(value) {{
                        const content = String(value || "").trim();
                        if (!content) return "<p>—</p>";
                        if (/^(\s*[-*+]\s+|\s*\d+[.)]\s+)/m.test(content)) {{
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
                        if (summaryPrompt) {{
                            summaryPrompt.value = initialState.prompt || "simple";
                            summaryPrompt.addEventListener("change", () => updateUrlState());
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
                            marketSectionsEl.innerHTML = '<section class="card"><p class="status">No price snapshot available for this date.</p></section>';
                            return;
                        }}
                        marketSectionsEl.innerHTML = sections.map((section, idx) => `
                            <section class="card" data-section-key="${{section.key || idx}}">
                                <h2>${{section.label || section.key || "Section"}}</h2>
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
                        const defaultModel = "gpt-5.2";
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

                    async function analyzeMarketNews(auto = false) {{
                        if (!analyzeBtn || !summaryPrompt) return;
                        if (!latestNews.length) {{
                            if (summaryStatus) summaryStatus.textContent = "No market news available to summarize.";
                            return;
                        }}
                        analyzeBtn.disabled = true;
                        analyzeBtn.textContent = auto ? "Auto analyzing..." : "Analyzing all...";
                        if (summaryStatus) {{
                            summaryStatus.textContent = auto ? "Generating 3-model summary..." : "Running OpenAI / Perplexity / Gemini...";
                        }}
                        try {{
                            const promptStyle = summaryPrompt.value || "simple";
                            const params = new URLSearchParams({{
                                prompt_style: promptStyle,
                                date: selectedDate,
                                output_language: getOutputLanguage(),
                            }});
                            const response = await fetch(`/api/market/news/summarize?${{params.toString()}}`, {{
                                method: "POST",
                            }});
                            const payload = await response.json();
                            if (!response.ok || payload.error) {{
                                if (summaryStatus) summaryStatus.textContent = payload.error || "Analyze failed";
                                return;
                            }}
                            renderSummaryHistory(payload.summaries || []);
                            await loadSummaryDates();
                            const runResults = payload.run_results || [];
                            const okCount = runResults.filter((r) => r && r.ok).length;
                            if (summaryStatus) summaryStatus.textContent = `${{okCount}}/3 models updated`;
                        }} catch (error) {{
                            if (summaryStatus) summaryStatus.textContent = "Analyze failed";
                            console.error(error);
                        }} finally {{
                            analyzeBtn.disabled = false;
                            analyzeBtn.textContent = "Analyze All";
                        }}
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
                            latestNews = payload.news || [];
                            renderNews(latestNews);
                            if (marketNewsCountEl) {{
                                const count = Number(payload.news_count || latestNews.length || 0);
                                marketNewsCountEl.textContent = `${{count}} item${{count === 1 ? "" : "s"}}`;
                            }}
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
                            if (datePicker) {{
                                datePicker.redraw();
                            }}
                        }} catch (_error) {{
                            reportDateSet = new Set();
                        }}
                    }}

                    async function onDateChanged(nextDate) {{
                        selectedDate = String(nextDate || selectedDate);
                        updateUrlState();
                        await refreshMarket();
                        const existing = await loadSummaryHistory();
                        if (!existing.length && isToday(selectedDate)) {{
                            analyzeMarketNews(true);
                        }}
                    }}

                    if (analyzeBtn) {{
                        analyzeBtn.addEventListener("click", () => analyzeMarketNews(false));
                    }}
                    initOutputLanguage();
                    refreshBtn.addEventListener("click", refreshMarket);
                    if (window.flatpickr && dateInput) {{
                        datePicker = window.flatpickr(dateInput, {{
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
                    }}
                    Promise.all([loadSummaryDates(), refreshMarket()]).then(async () => {{
                        updateUrlState();
                        const existing = await loadSummaryHistory();
                        if (!existing.length && isToday(selectedDate)) {{
                            analyzeMarketNews(true);
                        }}
                    }});
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
