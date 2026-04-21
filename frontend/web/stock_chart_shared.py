"""Shared stock chart UI helpers for web pages."""

from __future__ import annotations

import json

STOCK_CHART_RANGE_KEYS = ("1D", "5D", "1M", "3M", "6M", "8M", "1Y", "2Y", "3Y", "5Y")
DEFAULT_STOCK_CHART_RANGE = "1Y"
DEFAULT_STOCK_CHART_MA_WINDOWS = (20, 50, 200)


def render_stock_range_buttons_html(active_range: str = DEFAULT_STOCK_CHART_RANGE) -> str:
    normalized = str(active_range or DEFAULT_STOCK_CHART_RANGE).strip().upper() or DEFAULT_STOCK_CHART_RANGE
    return "".join(
        f'<button class="stock-range-btn{" active" if range_key == normalized else ""}" '
        f'data-range="{range_key}" type="button">{range_key}</button>'
        for range_key in STOCK_CHART_RANGE_KEYS
    )


def render_shared_stock_chart_assets() -> str:
    ranges_json = json.dumps(list(STOCK_CHART_RANGE_KEYS), ensure_ascii=False)
    ma_windows_json = json.dumps(list(DEFAULT_STOCK_CHART_MA_WINDOWS), ensure_ascii=False)
    default_range_json = json.dumps(DEFAULT_STOCK_CHART_RANGE, ensure_ascii=False)
    default_ma_query_json = json.dumps(
        ",".join(str(item) for item in DEFAULT_STOCK_CHART_MA_WINDOWS),
        ensure_ascii=False,
    )
    return f"""
        <script>
            (function() {{
                if (window.MarketAgentStockChart) return;
                const RANGE_KEYS = {ranges_json};
                const MA_WINDOWS = {ma_windows_json};
                const DEFAULT_RANGE = {default_range_json};
                const DEFAULT_MA_QUERY = {default_ma_query_json};

                function normalizeRangeKey(raw) {{
                    const token = String(raw || "").trim().toUpperCase();
                    return RANGE_KEYS.includes(token) ? token : DEFAULT_RANGE;
                }}

                function buildRangeButtonsHtml(activeRange) {{
                    const normalized = normalizeRangeKey(activeRange);
                    return RANGE_KEYS.map((rangeKey) =>
                        `<button class="stock-range-btn${{rangeKey === normalized ? " active" : ""}}" data-range="${{rangeKey}}" type="button">${{rangeKey}}</button>`
                    ).join("");
                }}

                function renderChart(canvasEl, existingChart, points) {{
                    if (!canvasEl || !window.Chart) return existingChart || null;
                    const labels = points.map((p) => String(p.date || ""));
                    const closeData = points.map((p) => (typeof p.close === "number" ? p.close : null));
                    const volumeData = points.map((p) => (typeof p.volume === "number" ? p.volume : null));
                    const ma20 = points.map((p) => (typeof p.ma_20 === "number" ? p.ma_20 : null));
                    const ma50 = points.map((p) => (typeof p.ma_50 === "number" ? p.ma_50 : null));
                    const ma200 = points.map((p) => (typeof p.ma_200 === "number" ? p.ma_200 : null));
                    if (existingChart) {{
                        existingChart.destroy();
                    }}
                    return new window.Chart(canvasEl, {{
                        type: "line",
                        data: {{
                            labels,
                            datasets: [
                                {{
                                    label: "Close",
                                    data: closeData,
                                    borderColor: "#0f172a",
                                    backgroundColor: "rgba(15,23,42,0.06)",
                                    tension: 0.15,
                                    pointRadius: 0,
                                    yAxisID: "y",
                                }},
                                {{
                                    label: "MA20",
                                    data: ma20,
                                    borderColor: "#2563eb",
                                    borderDash: [5, 4],
                                    tension: 0.1,
                                    pointRadius: 0,
                                    yAxisID: "y",
                                }},
                                {{
                                    label: "MA50",
                                    data: ma50,
                                    borderColor: "#16a34a",
                                    borderDash: [6, 5],
                                    tension: 0.1,
                                    pointRadius: 0,
                                    yAxisID: "y",
                                }},
                                {{
                                    label: "MA200",
                                    data: ma200,
                                    borderColor: "#dc2626",
                                    borderDash: [8, 6],
                                    tension: 0.1,
                                    pointRadius: 0,
                                    yAxisID: "y",
                                }},
                                {{
                                    label: "Volume",
                                    type: "bar",
                                    data: volumeData,
                                    backgroundColor: "rgba(59,130,246,0.18)",
                                    borderWidth: 0,
                                    yAxisID: "y1",
                                }},
                            ],
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            interaction: {{ mode: "index", intersect: false }},
                            plugins: {{
                                legend: {{ display: true, labels: {{ boxWidth: 14 }} }},
                            }},
                            scales: {{
                                y: {{
                                    position: "left",
                                    title: {{ display: true, text: "Price" }},
                                }},
                                y1: {{
                                    position: "right",
                                    grid: {{ drawOnChartArea: false }},
                                    title: {{ display: true, text: "Volume" }},
                                }},
                                x: {{
                                    ticks: {{ maxTicksLimit: 10 }},
                                }},
                            }},
                        }},
                    }});
                }}

                function formatStatus(payload, points, activeRange) {{
                    const ticker = String((payload && payload.ticker) || "");
                    const firstDate = points.length ? String(points[0].date || "") : "";
                    const lastDate = points.length ? String(points[points.length - 1].date || "") : "";
                    return `${{ticker}} · ${{normalizeRangeKey(activeRange)}} · ${{points.length}} points · ${{firstDate}} → ${{lastDate}}`;
                }}

                async function fetchSeries(companyName, rangeKey) {{
                    const normalizedRange = normalizeRangeKey(rangeKey);
                    const response = await fetch(
                        `/api/company/${{encodeURIComponent(companyName)}}/stock/series?range_key=${{encodeURIComponent(normalizedRange)}}&ma_windows=${{encodeURIComponent(DEFAULT_MA_QUERY)}}`
                    );
                    const payload = await response.json();
                    if (!response.ok || payload.error) {{
                        throw new Error((payload && payload.error) || "Failed to load stock series.");
                    }}
                    return payload;
                }}

                class StockChartController {{
                    constructor(options) {{
                        this.companyName = String((options && options.companyName) || "");
                        this.controlsEl = options && options.controlsEl ? options.controlsEl : null;
                        this.statusEl = options && options.statusEl ? options.statusEl : null;
                        this.chartEl = options && options.chartEl ? options.chartEl : null;
                        this.onLoaded = options && typeof options.onLoaded === "function" ? options.onLoaded : null;
                        this.onError = options && typeof options.onError === "function" ? options.onError : null;
                        this.onRangeChange = options && typeof options.onRangeChange === "function" ? options.onRangeChange : null;
                        this.activeRange = normalizeRangeKey(options && options.initialRange);
                        this.chart = null;
                        this.latestSeries = [];
                        this.latestPayload = null;
                        this._handleControlClick = this._handleControlClick.bind(this);
                        this._bindControls();
                    }}

                    _bindControls() {{
                        if (!this.controlsEl) return;
                        this.controlsEl.addEventListener("click", this._handleControlClick);
                        this._syncRangeButtons();
                    }}

                    _handleControlClick(event) {{
                        const button = event.target && typeof event.target.closest === "function"
                            ? event.target.closest(".stock-range-btn")
                            : null;
                        if (!button || !this.controlsEl || !this.controlsEl.contains(button)) return;
                        const nextRange = normalizeRangeKey(button.dataset.range || this.activeRange);
                        if (nextRange === this.activeRange) return;
                        this.setRange(nextRange);
                    }}

                    _syncRangeButtons() {{
                        if (!this.controlsEl) return;
                        this.controlsEl.querySelectorAll(".stock-range-btn").forEach((button) => {{
                            const isActive = normalizeRangeKey(button.dataset.range || "") === this.activeRange;
                            button.classList.toggle("active", isActive);
                        }});
                    }}

                    async load() {{
                        if (this.statusEl) {{
                            this.statusEl.textContent = `Loading ${{this.activeRange}} series...`;
                        }}
                        try {{
                            const payload = await fetchSeries(this.companyName, this.activeRange);
                            const points = Array.isArray(payload.points) ? payload.points : [];
                            this.latestPayload = payload;
                            this.latestSeries = points;
                            if (this.statusEl) {{
                                this.statusEl.textContent = formatStatus(payload, points, this.activeRange);
                            }}
                            this.chart = renderChart(this.chartEl, this.chart, points);
                            if (this.onLoaded) {{
                                this.onLoaded(payload, points);
                            }}
                            return payload;
                        }} catch (error) {{
                            if (this.statusEl) {{
                                this.statusEl.textContent = error && error.message ? error.message : "Failed to load stock series.";
                            }}
                            this.latestPayload = null;
                            this.latestSeries = [];
                            if (this.chart) {{
                                this.chart.destroy();
                                this.chart = null;
                            }}
                            if (this.onError) {{
                                this.onError(error);
                            }}
                            throw error;
                        }}
                    }}

                    async setRange(nextRange, options) {{
                        const shouldNotify = !options || options.notify !== false;
                        this.activeRange = normalizeRangeKey(nextRange);
                        this._syncRangeButtons();
                        if (shouldNotify && this.onRangeChange) {{
                            this.onRangeChange(this.activeRange);
                        }}
                        return this.load();
                    }}

                    destroy() {{
                        if (this.controlsEl) {{
                            this.controlsEl.removeEventListener("click", this._handleControlClick);
                        }}
                        if (this.chart) {{
                            this.chart.destroy();
                            this.chart = null;
                        }}
                    }}
                }}

                window.MarketAgentStockChart = {{
                    RANGE_KEYS,
                    MA_WINDOWS,
                    DEFAULT_RANGE,
                    buildRangeButtonsHtml,
                    normalizeRangeKey,
                    createController(options) {{
                        return new StockChartController(options || {{}});
                    }},
                }};
            }})();
        </script>
    """
