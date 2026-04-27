"""Top-level charts page for subscribed companies."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav
from frontend.web.stock_chart_shared import render_shared_stock_chart_assets


def render_charts_page() -> str:
    shared_assets = render_shared_stock_chart_assets()
    return f"""
        <html>
            <head>
                <title>MarketAgent – Charts</title>
                <style>
                    {BASE_PAGE_STYLES}
                    :root {{
                        --charts-ink: #0f172a;
                        --charts-accent: #2563eb;
                        --charts-muted: #64748b;
                        --charts-surface: #fffdf8;
                        --charts-outline: rgba(15, 23, 42, 0.08);
                    }}
                    body {{
                        background:
                            radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 24%),
                            linear-gradient(180deg, #f8f3ea 0%, #f2f5f9 100%);
                    }}
                    .container {{ max-width: 1280px; }}
                    .charts-hero {{
                        display: flex;
                        align-items: flex-end;
                        justify-content: space-between;
                        gap: 1rem;
                        flex-wrap: wrap;
                    }}
                    .charts-title {{
                        margin: 0;
                        color: var(--charts-ink);
                        font-size: 2rem;
                        letter-spacing: -0.03em;
                    }}
                    .charts-subtitle {{
                        margin: 0.35rem 0 0;
                        color: var(--charts-muted);
                        max-width: 720px;
                    }}
                    .charts-meta {{
                        color: var(--charts-muted);
                        font-size: 0.85rem;
                        font-weight: 600;
                    }}
                    .charts-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
                        gap: 1rem;
                    }}
                    .chart-card {{
                        position: relative;
                        border: 1px solid var(--charts-outline);
                        border-radius: 1rem;
                        background: var(--charts-surface);
                        padding: 1rem;
                        box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
                    }}
                    .chart-card.dragging {{
                        opacity: 0.45;
                    }}
                    .chart-card.drag-over {{
                        outline: 2px dashed var(--charts-accent);
                        outline-offset: 4px;
                    }}
                    .chart-card-header {{
                        display: flex;
                        align-items: flex-start;
                        justify-content: space-between;
                        gap: 0.8rem;
                        margin-bottom: 0.75rem;
                    }}
                    .chart-card-title {{
                        margin: 0;
                        font-size: 1.05rem;
                        color: var(--charts-ink);
                    }}
                    .chart-card-ticker {{
                        margin-top: 0.18rem;
                        font-size: 0.8rem;
                        color: var(--charts-muted);
                        font-weight: 700;
                        letter-spacing: 0.04em;
                    }}
                    .chart-card-actions {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                        justify-content: flex-end;
                    }}
                    .chart-card-link, .chart-expand-btn {{
                        text-decoration: none;
                        border-radius: 999px;
                        padding: 0.35rem 0.75rem;
                        font-size: 0.78rem;
                        font-weight: 700;
                    }}
                    .chart-card-link {{
                        background: #eff6ff;
                        color: #1d4ed8;
                        border: 1px solid #bfdbfe;
                    }}
                    .chart-expand-btn {{
                        border: 1px solid #cbd5e1;
                        background: #fff;
                        color: #334155;
                        cursor: pointer;
                    }}
                    .chart-status {{
                        min-height: 1.2rem;
                        color: var(--charts-muted);
                        font-size: 0.8rem;
                        margin-bottom: 0.6rem;
                    }}
                    .chart-controls {{
                        display: flex;
                        align-items: center;
                        gap: 0.45rem;
                        flex-wrap: wrap;
                        margin-bottom: 0.8rem;
                    }}
                    .stock-range-btn {{
                        border: 1px solid #cbd5e1;
                        background: #fff;
                        color: #334155;
                        border-radius: 999px;
                        padding: 0.28rem 0.62rem;
                        font-size: 0.76rem;
                        font-weight: 700;
                        cursor: pointer;
                    }}
                    .stock-range-btn.active {{
                        background: #0f172a;
                        border-color: #0f172a;
                        color: #fff;
                    }}
                    .chart-canvas-wrap {{
                        position: relative;
                        height: 260px;
                    }}
                    .chart-placeholder {{
                        display: grid;
                        gap: 0.8rem;
                        align-content: center;
                        min-height: 220px;
                        border: 1px dashed #cbd5e1;
                        border-radius: 0.9rem;
                        background: rgba(255,255,255,0.7);
                        padding: 1rem;
                    }}
                    .chart-placeholder p {{
                        margin: 0;
                        color: var(--charts-muted);
                    }}
                    .chart-placeholder a {{
                        width: fit-content;
                        text-decoration: none;
                        color: #1d4ed8;
                        font-weight: 700;
                    }}
                    .charts-empty {{
                        color: var(--charts-muted);
                        margin: 0;
                    }}
                    .charts-modal {{
                        position: fixed;
                        inset: 0;
                        background: rgba(15, 23, 42, 0.62);
                        display: none;
                        align-items: center;
                        justify-content: center;
                        padding: 1.25rem;
                        z-index: 1000;
                    }}
                    .charts-modal.open {{
                        display: flex;
                    }}
                    .charts-modal-panel {{
                        width: min(1100px, 100%);
                        max-height: calc(100vh - 2.5rem);
                        overflow: auto;
                        border-radius: 1.2rem;
                        background: #fffefb;
                        box-shadow: 0 30px 90px rgba(15, 23, 42, 0.3);
                        padding: 1.1rem;
                    }}
                    .charts-modal-header {{
                        display: flex;
                        align-items: flex-start;
                        justify-content: space-between;
                        gap: 1rem;
                        margin-bottom: 0.8rem;
                    }}
                    .charts-modal-title {{
                        margin: 0;
                        font-size: 1.3rem;
                        color: var(--charts-ink);
                    }}
                    .charts-modal-close {{
                        border: 1px solid #cbd5e1;
                        background: #fff;
                        color: #334155;
                        border-radius: 999px;
                        padding: 0.4rem 0.8rem;
                        font-size: 0.8rem;
                        font-weight: 700;
                        cursor: pointer;
                    }}
                    .charts-modal-chart {{
                        height: 540px;
                    }}
                    @media (max-width: 720px) {{
                        .chart-canvas-wrap {{
                            height: 220px;
                        }}
                        .charts-modal-chart {{
                            height: 360px;
                        }}
                    }}
                </style>
            </head>
            <body class="report">
                {render_nav("charts")}
                <div class="container">
                    <section class="card">
                        <div class="charts-hero">
                            <div>
                                <h1 class="charts-title">Charts</h1>
                                <p class="charts-subtitle">Track all subscribed company charts in one place, reorder them by priority, and expand any chart for a larger technical view.</p>
                            </div>
                            <div class="charts-meta" id="charts-meta">Loading subscribed charts...</div>
                        </div>
                    </section>
                    <section class="card">
                        <div class="charts-grid" id="charts-grid"></div>
                        <p class="charts-empty" id="charts-empty" style="display:none;">No subscribed companies yet.</p>
                    </section>
                </div>
                <div class="charts-modal" id="charts-modal" aria-hidden="true">
                    <div class="charts-modal-panel">
                        <div class="charts-modal-header">
                            <div>
                                <h2 class="charts-modal-title" id="charts-modal-title">Chart</h2>
                                <div class="chart-status" id="charts-modal-status"></div>
                            </div>
                            <button class="charts-modal-close" id="charts-modal-close" type="button">Close</button>
                        </div>
                        <div class="chart-controls" id="charts-modal-controls"></div>
                        <div class="charts-modal-chart">
                            <canvas id="charts-modal-canvas"></canvas>
                        </div>
                    </div>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                {shared_assets}
                <script>
                    const gridEl = document.getElementById("charts-grid");
                    const emptyEl = document.getElementById("charts-empty");
                    const metaEl = document.getElementById("charts-meta");
                    const modalEl = document.getElementById("charts-modal");
                    const modalTitleEl = document.getElementById("charts-modal-title");
                    const modalStatusEl = document.getElementById("charts-modal-status");
                    const modalControlsEl = document.getElementById("charts-modal-controls");
                    const modalCanvasEl = document.getElementById("charts-modal-canvas");
                    const modalCloseEl = document.getElementById("charts-modal-close");
                    let orderedCompanies = [];
                    let activeDragCompany = "";
                    let modalController = null;
                    const INITIAL_CHART_LOAD_CONCURRENCY = 2;

                    function escapeHtml(value) {{
                        return String(value || "")
                            .replaceAll("&", "&amp;")
                            .replaceAll("<", "&lt;")
                            .replaceAll(">", "&gt;")
                            .replaceAll('"', "&quot;")
                            .replaceAll("'", "&#39;");
                    }}

                    function companyPriceIntelligenceHref(companyName) {{
                        return `/company/${{encodeURIComponent(companyName)}}?view=stock#price-intelligence`;
                    }}

                    async function fetchLayout() {{
                        const response = await fetch("/api/charts/layout");
                        const payload = await response.json();
                        if (!response.ok || payload.error) {{
                            throw new Error((payload && payload.error) || "Failed to load charts layout.");
                        }}
                        return payload;
                    }}

                    async function saveLayout() {{
                        const response = await fetch("/api/charts/layout", {{
                            method: "PUT",
                            headers: {{ "Content-Type": "application/json" }},
                            body: JSON.stringify({{ company_names: orderedCompanies.map((item) => item.company_name) }}),
                        }});
                        const payload = await response.json();
                        if (!response.ok || payload.error) {{
                            throw new Error((payload && payload.error) || "Failed to save charts layout.");
                        }}
                        return payload;
                    }}

                    function renderEmptyState(show) {{
                        if (emptyEl) {{
                            emptyEl.style.display = show ? "block" : "none";
                        }}
                    }}

                    function updateMeta() {{
                        if (!metaEl) return;
                        metaEl.textContent = `${{orderedCompanies.length}} subscribed chart${{orderedCompanies.length === 1 ? "" : "s"}}`;
                    }}

                    function openModal(company) {{
                        if (!company || !company.ticker || !modalEl) return;
                        if (modalController) {{
                            modalController.destroy();
                            modalController = null;
                        }}
                        modalTitleEl.textContent = `${{company.company_name}} · ${{company.ticker}}`;
                        modalControlsEl.innerHTML = window.MarketAgentStockChart.buildRangeButtonsHtml(company.currentRange || window.MarketAgentStockChart.DEFAULT_RANGE);
                        modalEl.classList.add("open");
                        modalEl.setAttribute("aria-hidden", "false");
                        modalController = window.MarketAgentStockChart.createController({{
                            companyName: company.company_name,
                            controlsEl: modalControlsEl,
                            statusEl: modalStatusEl,
                            chartEl: modalCanvasEl,
                            initialRange: company.currentRange || window.MarketAgentStockChart.DEFAULT_RANGE,
                            retryCount: 2,
                            retryDelayMs: 800,
                            onRangeChange(rangeKey) {{
                                company.currentRange = rangeKey;
                                if (company.controller && company.controller.activeRange !== rangeKey) {{
                                    company.controller.setRange(rangeKey, {{ notify: false }}).catch(() => {{}});
                                }}
                            }},
                        }});
                        modalController.load().catch(() => {{}});
                    }}

                    function closeModal() {{
                        if (modalController) {{
                            modalController.destroy();
                            modalController = null;
                        }}
                        if (modalEl) {{
                            modalEl.classList.remove("open");
                            modalEl.setAttribute("aria-hidden", "true");
                        }}
                    }}

                    function buildChartCard(company) {{
                        const article = document.createElement("article");
                        article.className = "chart-card";
                        article.draggable = true;
                        article.dataset.companyName = company.company_name;
                        if (!company.ticker) {{
                            article.innerHTML = `
                                <div class="chart-card-header">
                                    <div>
                                        <h2 class="chart-card-title">${{escapeHtml(company.company_name)}}</h2>
                                        <div class="chart-card-ticker">No ticker</div>
                                    </div>
                                    <div class="chart-card-actions">
                                        <a class="chart-card-link" href="${{companyPriceIntelligenceHref(company.company_name)}}" target="_blank">Open Price Intelligence</a>
                                    </div>
                                </div>
                                <div class="chart-placeholder">
                                    <p>This subscribed company does not have a ticker yet, so the chart cannot load.</p>
                                    <a href="${{companyPriceIntelligenceHref(company.company_name)}}" target="_blank">Set ticker on company page</a>
                                </div>
                            `;
                            return article;
                        }}
                        article.innerHTML = `
                            <div class="chart-card-header">
                                <div>
                                    <h2 class="chart-card-title">${{escapeHtml(company.company_name)}}</h2>
                                    <div class="chart-card-ticker">${{escapeHtml(company.ticker)}}</div>
                                </div>
                                <div class="chart-card-actions">
                                    <a class="chart-card-link" href="${{companyPriceIntelligenceHref(company.company_name)}}" target="_blank">Open Price Intelligence</a>
                                    <button class="chart-expand-btn" type="button">Expand</button>
                                </div>
                            </div>
                            <div class="chart-status"></div>
                            <div class="chart-controls">${{window.MarketAgentStockChart.buildRangeButtonsHtml(company.currentRange || window.MarketAgentStockChart.DEFAULT_RANGE)}}</div>
                            <div class="chart-canvas-wrap">
                                <canvas></canvas>
                            </div>
                        `;
                        const statusEl = article.querySelector(".chart-status");
                        const controlsEl = article.querySelector(".chart-controls");
                        const chartEl = article.querySelector("canvas");
                        const expandBtn = article.querySelector(".chart-expand-btn");
                        company.controller = window.MarketAgentStockChart.createController({{
                            companyName: company.company_name,
                            controlsEl,
                            statusEl,
                            chartEl,
                            initialRange: company.currentRange || window.MarketAgentStockChart.DEFAULT_RANGE,
                            retryCount: 2,
                            retryDelayMs: 800,
                            onRangeChange(rangeKey) {{
                                company.currentRange = rangeKey;
                                if (
                                    modalController &&
                                    modalEl.classList.contains("open") &&
                                    modalTitleEl.textContent.startsWith(company.company_name) &&
                                    modalController.activeRange !== rangeKey
                                ) {{
                                    modalController.setRange(rangeKey, {{ notify: false }}).catch(() => {{}});
                                }}
                            }},
                        }});
                        if (expandBtn) {{
                            expandBtn.addEventListener("click", () => openModal(company));
                        }}
                        return article;
                    }}

                    function wireDrag(article) {{
                        article.addEventListener("dragstart", () => {{
                            activeDragCompany = article.dataset.companyName || "";
                            article.classList.add("dragging");
                        }});
                        article.addEventListener("dragend", () => {{
                            activeDragCompany = "";
                            article.classList.remove("dragging");
                            article.classList.remove("drag-over");
                        }});
                        article.addEventListener("dragover", (event) => {{
                            event.preventDefault();
                            article.classList.add("drag-over");
                        }});
                        article.addEventListener("dragleave", () => {{
                            article.classList.remove("drag-over");
                        }});
                        article.addEventListener("drop", async (event) => {{
                            event.preventDefault();
                            article.classList.remove("drag-over");
                            const targetCompany = article.dataset.companyName || "";
                            if (!activeDragCompany || !targetCompany || activeDragCompany === targetCompany) {{
                                return;
                            }}
                            const fromIndex = orderedCompanies.findIndex((item) => item.company_name === activeDragCompany);
                            const toIndex = orderedCompanies.findIndex((item) => item.company_name === targetCompany);
                            if (fromIndex < 0 || toIndex < 0) {{
                                return;
                            }}
                            const [moved] = orderedCompanies.splice(fromIndex, 1);
                            orderedCompanies.splice(toIndex, 0, moved);
                            renderGrid();
                            try {{
                                await saveLayout();
                            }} catch (error) {{
                                if (metaEl) {{
                                    metaEl.textContent = error && error.message ? error.message : "Failed to save layout.";
                                }}
                            }}
                        }});
                    }}

                    function renderGrid() {{
                        orderedCompanies.forEach((company) => {{
                            if (company.controller) {{
                                company.controller.destroy();
                                company.controller = null;
                            }}
                        }});
                        gridEl.innerHTML = "";
                        renderEmptyState(!orderedCompanies.length);
                        updateMeta();
                        orderedCompanies.forEach((company) => {{
                            const article = buildChartCard(company);
                            wireDrag(article);
                            gridEl.appendChild(article);
                        }});
                    }}

                    async function loadChartsInBatches() {{
                        const pending = orderedCompanies.filter((company) => company && company.ticker && company.controller);
                        for (let index = 0; index < pending.length; index += INITIAL_CHART_LOAD_CONCURRENCY) {{
                            const batch = pending.slice(index, index + INITIAL_CHART_LOAD_CONCURRENCY);
                            await Promise.all(batch.map((company) => company.controller.load().catch(() => null)));
                        }}
                    }}

                    async function init() {{
                        try {{
                            const payload = await fetchLayout();
                            orderedCompanies = Array.isArray(payload.companies)
                                ? payload.companies.map((item) => ({{
                                    company_name: String(item.company_name || ""),
                                    ticker: String(item.ticker || ""),
                                    currentRange: window.MarketAgentStockChart.DEFAULT_RANGE,
                                    controller: null,
                                }}))
                                : [];
                            renderGrid();
                            await loadChartsInBatches();
                        }} catch (error) {{
                            renderEmptyState(true);
                            if (metaEl) {{
                                metaEl.textContent = error && error.message ? error.message : "Failed to load charts.";
                            }}
                        }}
                    }}

                    if (modalCloseEl) {{
                        modalCloseEl.addEventListener("click", closeModal);
                    }}
                    if (modalEl) {{
                        modalEl.addEventListener("click", (event) => {{
                            if (event.target === modalEl) {{
                                closeModal();
                            }}
                        }});
                    }}
                    document.addEventListener("keydown", (event) => {{
                        if (event.key === "Escape") {{
                            closeModal();
                        }}
                    }});

                    init();
                </script>
            </body>
        </html>
    """
