from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

from frontend.common import StockFrontendClient
from frontend.web.company_page import render_company_page
from frontend.web.person_page import render_person_page
from frontend.web.shared_page import render_nav
from market_agent.analysis import analyze_single_stock_sections, get_provider, list_models

app = FastAPI(
    title="MarketAgent Web Frontend",
    description="Lightweight HTML frontend powered by the shared MarketAgent stock API.",
)

client = StockFrontendClient()


@app.post("/analysis")
async def analyze(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    symbols = payload.get("symbols") or []
    model = payload.get("model") or "gpt-4o-mini"
    provider_name = payload.get("provider") or "openai"
    if not isinstance(symbols, list):
        return {"error": "symbols must be a list"}

    results: Dict[str, Any] = {}
    provider = get_provider(provider_name, model=model)
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        snapshot = client.query(symbol)
        results[symbol] = analyze_single_stock_sections(
            snapshot,
            provider=provider,
        )
    return {"provider": provider_name, "model": model, "results": results}


@app.get("/", response_class=HTMLResponse)
async def index(
    symbol: Optional[str] = Query(
        None, description="Ticker symbols to query (e.g. AAPL, MSFT)"
    ),
) -> str:
    symbol_value = (symbol or "").strip().upper()
    symbols = [item.strip().upper() for item in symbol_value.split(",") if item.strip()]
    error_message = None
    stocks: List[Tuple[str, Optional[Dict[str, object]], Optional[Any]]] = []
    missing_symbols: List[str] = []
    if symbols:
        for item in symbols:
            try:
                snapshot = client.query(item)
                data = snapshot.base.as_dict()
                if len(data) <= 1:
                    missing_symbols.append(item)
                stocks.append((item, data, snapshot))
            except Exception as exc:
                error_message = str(exc)
                stocks.append((item, None, None))

    valid_stocks = [
        (symbol, data, snapshot)
        for symbol, data, snapshot in stocks
        if data is not None and len(data) > 1 and snapshot is not None
    ]
    sections_html = (
        _render_comparison_sections(valid_stocks)
        if valid_stocks
        else ""
    )

    base_section = (
        f"""
            {sections_html}
        """
        if stocks
        else """
            <section class="card">
                <h2>Indicators</h2>
                <p class="muted">Add a stock using the + button to fetch indicators.</p>
            </section>
        """
    )

    return f"""
        <html>
            <head>
                <title>MarketAgent – Stock Indicators</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }}
                    nav {{ background: white; border-radius: 0.75rem; padding: 0.75rem 1.25rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); max-width: 960px; margin: 0 auto 1.5rem; }}
                    nav a {{ margin-right: 1rem; text-decoration: none; color: #1f2937; font-weight: 600; }}
                    nav a.active {{ color: #2563eb; }}
                    .container {{ max-width: 960px; margin: 0 auto; padding: 0 1rem; display: grid; gap: 1.5rem; }}
                    .card {{ background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
                    h1, h2 {{ margin-top: 0; }}
                    .comparison-wrap {{ overflow-x: auto; }}
                    .comparison-wrap::-webkit-scrollbar {{ height: 8px; }}
                    .comparison-wrap::-webkit-scrollbar-thumb {{ background: #e2e8f0; border-radius: 999px; }}
                    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
                    .comparison-table {{ width: max-content; min-width: 100%; }}
                    .comparison-table th:first-child,
                    .comparison-table td:first-child {{
                        border-right: 2px solid #e5e7eb;
                        padding-right: 0;
                        background: #f8fafc;
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }}
                    .comparison-table th, .comparison-table td {{
                        overflow-wrap: anywhere;
                        word-break: break-word;
                        white-space: normal;
                        vertical-align: top;
                    }}
                    .comparison-table td {{ padding-left: 0.5rem; }}
                    .comparison-wrap .comparison-table {{ margin: 0 auto; }}
                    th, td {{ padding: 0.25rem 0.35rem; text-align: left; border-bottom: 1px solid #eee; }}
                    th {{ width: 40%; color: #555; }}
                    .muted {{ color: #888; }}
                    form {{ display: flex; gap: 0.5rem; }}
                    input[type="text"] {{ flex: 1; padding: 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }}
                    button {{ padding: 0.65rem 1.2rem; border: none; border-radius: 0.5rem; background: #2563eb; color: white; cursor: pointer; }}
                    button:hover {{ background: #1d4ed8; }}
                    label {{ display: flex; align-items: center; gap: 0.5rem; }}
                    #symbol-list {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }}
                    .chip {{ display: inline-flex; align-items: center; gap: 0.35rem; background: #eef2ff; color: #1e3a8a; padding: 0.3rem 0.6rem; border-radius: 999px; font-size: 0.9rem; }}
                    .chip .remove {{ background: transparent; color: #1e3a8a; border: none; cursor: pointer; font-size: 1rem; padding: 0; line-height: 1; }}
                    .chip .remove:hover {{ color: #1d4ed8; }}
                    #add-symbol {{ width: 3rem; padding: 0.65rem 0; font-weight: bold; }}
                    .analysis-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-top: 1rem; }}
                    .analysis-card {{ border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 0.75rem; background: #f9fafb; }}
                    .analysis-card h3 {{ margin: 0 0 0.5rem; font-size: 1rem; }}
                    .analysis-card ul {{ padding-left: 1.1rem; margin: 0.35rem 0; }}
                    .analysis-controls {{ display: flex; gap: 0.5rem; align-items: center; margin-top: 0.75rem; flex-wrap: wrap; }}
                    select {{ padding: 0.5rem 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }}
                    #analyze-button {{ background: #16a34a; }}
                    #analyze-button:hover {{ background: #15803d; }}
                    #analysis-status {{ color: #666; font-size: 0.9rem; }}
                </style>
            </head>
            <body>
                {render_nav("stock")}
                <div class="container">
                    <section class="card">
                        <h1>Stock Ticker</h1>
                        <form method="get">
                            <input type="text" id="symbol-input" value="" placeholder="Add ticker (e.g. AAPL)" />
                            <button type="button" id="add-symbol">+</button>
                        </form>
                        <div id="symbol-list" data-symbols="{symbol_value}"></div>
                        <div class="analysis-controls">
                            <label for="model-select">Model</label>
                            <select id="model-select">
                                {''.join(f'<option value="{model}">{model}</option>' for model in list_models().get("openai", []))}
                            </select>
                            <button type="button" id="analyze-button">Generate Analysis</button>
                            <span id="analysis-status"></span>
                        </div>
                    </section>
                    {f'<section class="card"><p class="muted">Note: {error_message}</p></section>' if error_message else ''}
                    {f'<section class="card"><p class="muted">Ticker not found: {", ".join(missing_symbols)}</p></section>' if missing_symbols else ''}
                    {base_section}
                </div>
                <script>
                    const listContainer = document.getElementById("symbol-list");
                    const input = document.getElementById("symbol-input");
                    const addButton = document.getElementById("add-symbol");
                    const analyzeButton = document.getElementById("analyze-button");
                    const modelSelect = document.getElementById("model-select");
                    const analysisStatus = document.getElementById("analysis-status");
                    const symbols = (listContainer.dataset.symbols || "")
                        .split(",")
                        .map((item) => item.trim().toUpperCase())
                        .filter((item) => item);

                    function renderList() {{
                        if (!symbols.length) {{
                            listContainer.innerHTML = '<p class="muted">No stocks selected yet.</p>';
                            return;
                        }}
                        listContainer.innerHTML = symbols
                            .map(
                                (symbol) =>
                                    `<span class="chip">${{symbol}}<button class="remove" data-symbol="${{symbol}}" aria-label="Remove ${{symbol}}">×</button></span>`
                            )
                            .join("");
                        listContainer.querySelectorAll("button.remove").forEach((button) => {{
                            button.addEventListener("click", () => {{
                                const symbol = button.dataset.symbol;
                                const index = symbols.indexOf(symbol);
                                if (index >= 0) {{
                                    symbols.splice(index, 1);
                                    updateQuery();
                                }}
                            }});
                        }});
                    }}

                    function updateQuery() {{
                        const next = symbols.join(",");
                        const url = new URL(window.location.href);
                        if (next) {{
                            url.searchParams.set("symbol", next);
                        }} else {{
                            url.searchParams.delete("symbol");
                        }}
                        window.location.href = url.toString();
                    }}

                    addButton.addEventListener("click", () => {{
                        const raw = input.value.trim();
                        if (!raw) {{
                            return;
                        }}
                        raw.split(",").forEach((value) => {{
                            const symbol = value.trim().toUpperCase();
                            if (symbol && !symbols.includes(symbol)) {{
                                symbols.push(symbol);
                            }}
                        }});
                        input.value = "";
                        updateQuery();
                    }});

                    input.addEventListener("keydown", (event) => {{
                        if (event.key === "Enter") {{
                            event.preventDefault();
                            addButton.click();
                        }}
                    }});

                    if (analyzeButton) {{
                        analyzeButton.addEventListener("click", async () => {{
                            if (!symbols.length) {{
                                return;
                            }}
                            analysisStatus.textContent = "Running analysis...";
                            try {{
                                const response = await fetch("/analysis", {{
                                    method: "POST",
                                    headers: {{
                                        "Content-Type": "application/json",
                                    }},
                                    body: JSON.stringify({{
                                        symbols: symbols,
                                        model: modelSelect ? modelSelect.value : "gpt-4o-mini",
                                    }}),
                                }});
                                if (!response.ok) {{
                                    throw new Error(`Analysis failed: ${{response.status}}`);
                                }}
                                const payload = await response.json();
                                renderAnalysis(payload);
                                analysisStatus.textContent = "Analysis complete.";
                            }} catch (error) {{
                                analysisStatus.textContent = "Analysis failed.";
                                console.error(error);
                            }}
                        }});
                    }}

                    renderList();
                
                    function renderAnalysis(payload) {{
                        const results = payload.results || {{}};
                        document.querySelectorAll("[data-analysis-section]").forEach((node) => {{
                            const section = node.dataset.analysisSection;
                            const cards = [];
                            Object.entries(results).forEach(([symbol, analysis]) => {{
                                const sectionResult = analysis.sections?.[section];
                                if (!sectionResult) {{
                                    return;
                                }}
                                cards.push(`
                                    <div class="analysis-card">
                                        <h3>${{symbol}}</h3>
                                        <div><strong>Summary:</strong> ${{sectionResult.summary || "No summary provided."}}</div>
                                        ${{renderList("Highlights", sectionResult.highlights)}}
                                        ${{renderList("Risks", sectionResult.risks)}}
                                        ${{renderList("Questions", sectionResult.questions)}}
                                    </div>
                                `);
                            }});
                            node.innerHTML = cards.join("");
                        }});
                    }}

                    function renderList(title, items) {{
                        if (!items || !items.length) {{
                            return "";
                        }}
                        const rows = items.map((item) => `<li>${{item}}</li>`).join("");
                        return `<div><strong>${{title}}:</strong><ul>${{rows}}</ul></div>`;
                    }}

                    function resizeComparisonTables() {{
                        document.querySelectorAll(".comparison-table").forEach((table) => {{
                            const labelCells = table.querySelectorAll("tr > th:first-child");
                            let maxWidth = 0;
                            const labelCol = table.querySelector("col.label-col");
                            const valueCols = table.querySelectorAll("col.value-col");
                            if (!labelCol || !valueCols.length) {{
                                return;
                            }}
                            labelCol.style.width = "auto";
                            valueCols.forEach((col) => {{
                                col.style.width = "auto";
                            }});
                            table.style.width = "max-content";
                            labelCells.forEach((cell) => {{
                                maxWidth = Math.max(maxWidth, cell.scrollWidth);
                            }});
                            const container = table.parentElement;
                            const containerWidth = container ? container.clientWidth : table.clientWidth;
                            const maxLabelWidth = 260;
                            const labelWidth = Math.min(maxWidth, maxLabelWidth);
                            const minValueWidth = 120;
                            const requiredWidth = labelWidth + minValueWidth * valueCols.length;
                            const tableWidth = Math.max(containerWidth, requiredWidth);
                            table.style.width = `${{tableWidth}}px`;
                            labelCol.style.width = `${{labelWidth}}px`;
                            const valueWidth = Math.max((tableWidth - labelWidth) / valueCols.length, minValueWidth);
                            valueCols.forEach((col) => {{
                                col.style.width = `${{valueWidth}}px`;
                            }});
                        }});
                    }}

                    window.addEventListener("load", resizeComparisonTables);
                    window.addEventListener("resize", resizeComparisonTables);
                </script>
                {f'<script>window.addEventListener("load", () => {{ alert("Ticker not found: {", ".join(missing_symbols)}"); }});</script>' if missing_symbols else ''}
            </body>
        </html>
    """


@app.get("/company", response_class=HTMLResponse)
async def company() -> str:
    return render_company_page()


@app.get("/person", response_class=HTMLResponse)
async def person() -> str:
    return render_person_page()


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _render_sections(data: Dict[str, object]) -> str:
    grouped = _group_indicators(data)
    return "".join(
        f"""
            <section class="card">
                <h2>{section}</h2>
                <table>
                    {''.join(f'<tr><th>{label}</th><td>{_format_value(value)}</td></tr>' for label, value in rows)}
                </table>
            </section>
        """
        for section, rows in grouped
    )


def _render_comparison_sections(
    stocks: List[Tuple[str, Dict[str, object], Any]],
) -> str:
    grouped = _group_indicator_keys(stocks)
    return "".join(
        f"""
            <section class="card">
                <h2>{section}</h2>
                <div class="comparison-wrap">
                    <table class="comparison-table">
                        <colgroup>
                            <col class="label-col" />
                            {''.join('<col class="value-col" />' for _ in stocks)}
                        </colgroup>
                        <tr>
                            <th>Stock</th>
                            {''.join(f'<th>{symbol}</th>' for symbol, _, _ in stocks)}
                        </tr>
                        {''.join(_render_comparison_row(label, key, stocks) for label, key in rows)}
                    </table>
                </div>
                <div class="analysis-grid" data-analysis-section="{section}"></div>
            </section>
        """
        for section, rows in grouped
    )


def _render_comparison_row(
    label: str,
    key: str,
    stocks: List[Tuple[str, Dict[str, object], Any]],
) -> str:
    cells = "".join(
        f"<td>{_format_value_cell(data.get(key))}</td>" for _, data, _ in stocks
    )
    return f"<tr><th title=\"{label}\">{label}</th>{cells}</tr>"




def _format_value_cell(value: object) -> str:
    if isinstance(value, dict):
        lines = "".join(
            f"<div>{subkey}: {_format_value(subvalue)}</div>"
            for subkey, subvalue in value.items()
        )
        return lines or "-"
    return _format_value(value)


def _group_indicators(data: Dict[str, object]) -> List[Tuple[str, List[Tuple[str, object]]]]:
    sections: Dict[str, List[Tuple[str, object]]] = {}
    for key, value in data.items():
        if key == "symbol":
            continue
        section = _classify_indicator(key)
        sections.setdefault(section, []).append((key, value))

    ordered_sections = [
        "Quote",
        "Price & Returns",
        "Volume & Liquidity",
        "Valuation",
        "Profitability & Margins",
        "Growth",
        "Cash Flow",
        "Balance Sheet",
        "Per-Share",
        "Leverage & Coverage",
    ]

    grouped: List[Tuple[str, List[Tuple[str, object]]]] = []
    for section in ordered_sections:
        rows = sections.get(section)
        if not rows:
            continue
        rows.sort(key=lambda item: _sort_key(item[0]))
        grouped.append((section, [(_label_for_key(k), v) for k, v in rows]))
    return grouped


def _group_indicator_keys(
    stocks: List[Tuple[str, Dict[str, object], Any]]
) -> List[Tuple[str, List[Tuple[str, str]]]]:
    sections: Dict[str, List[str]] = {}
    for _, data, _ in stocks:
        for key in data.keys():
            if key == "symbol":
                continue
            section = _classify_indicator(key)
            sections.setdefault(section, [])
            if key not in sections[section]:
                sections[section].append(key)

    ordered_sections = [
        "Quote",
        "Price & Returns",
        "Volume & Liquidity",
        "Valuation",
        "Profitability & Margins",
        "Growth",
        "Cash Flow",
        "Balance Sheet",
        "Per-Share",
        "Leverage & Coverage",
        "3rd Party Recommendation",
    ]

    grouped: List[Tuple[str, List[Tuple[str, str]]]] = []
    for section in ordered_sections:
        keys = sections.get(section)
        if not keys:
            continue
        keys.sort(key=_sort_key)
        grouped.append((section, [(_label_for_key(k), k) for k in keys]))
    return grouped




def _classify_indicator(key: str) -> str:
    lower_key = key.lower()

    if key == "quote_timestamp":
        return "Quote"
    if key == "previous_close":
        return "Price & Returns"

    if any(token in lower_key for token in ("volume", "liquidity")):
        return "Volume & Liquidity"

    if key in {"beta", "moving_averages", "rsi", "macd"}:
        return "Price & Returns"

    if any(token in lower_key for token in ("price", "return", "weekhigh", "weeklow")):
        return "Price & Returns"

    if any(token in lower_key for token in ("marketcap", "enterprisevalue", "ev", "pe")):
        return "Valuation"
    if lower_key.startswith("eps"):
        return "Valuation"

    if any(token in lower_key for token in ("margin", "profit", "operatingmargin")):
        if "growth" in lower_key:
            return "Growth"
        return "Profitability & Margins"

    if any(token in lower_key for token in ("growth", "cagr", "yoy")):
        return "Growth"

    if any(token in lower_key for token in ("cashflow", "free_cash_flow", "capex")):
        return "Cash Flow"

    if any(token in lower_key for token in ("cash", "debt", "equity", "bookvalue")):
        return "Balance Sheet"

    if "pershare" in lower_key:
        return "Per-Share"

    if any(token in lower_key for token in ("ratio", "coverage")):
        return "Leverage & Coverage"

    if any(token in lower_key for token in ("recommendation",)):
        return "Price & Returns"

    return "Price & Returns"


def _label_for_key(key: str) -> str:
    overrides = {
        "3MonthAvgDailyReturnStdDev": "3MoAvgDailyReturnVolStdDev",
        "recommendation": "FinnhubRecommendation",
        "recommendation_counts": "FinnhubRecommendationCounts",
        "focfCagr5Y": "FreeOperatingCashFlowCagr5Y",
        "tbvCagr5Y": "TangibleBookValueCagr5Y",
    }
    label = overrides.get(key, _to_title_camel(key))
    max_len = len(overrides["3MonthAvgDailyReturnStdDev"])
    if len(label) > max_len:
        label = _shorten_label(label, max_len)
    return label


def _to_title_camel(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", value)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    parts = [part for part in spaced.split() if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _shorten_label(label: str, max_len: int) -> str:
    replacements = [
        ("Average", "Avg"),
        ("Quarterly", "Qtr"),
        ("Annual", "Ann"),
        ("Revenue", "Rev"),
        ("Profit", "Prof"),
        ("Operating", "Op"),
        ("Interest", "Int"),
        ("Coverage", "Cov"),
        ("Current", "Curr"),
        ("Relative", "Rel"),
        ("Volatility", "Vol"),
        ("Return", "Ret"),
        ("CashFlow", "CF"),
        ("PerShare", "PerShr"),
        ("Employee", "Emp"),
        ("Share", "Shr"),
        ("LongTerm", "LT"),
        ("Total", "Tot"),
        ("Equity", "Eq"),
        ("Debt", "Debt"),
        ("Tangible", "Tang"),
        ("BookValue", "BV"),
    ]
    shortened = label
    for old, new in replacements:
        if len(shortened) <= max_len:
            break
        shortened = shortened.replace(old, new)
    if len(shortened) > max_len:
        shortened = shortened[: max_len - 1] + "…"
    return shortened


def _sort_key(key: str) -> Tuple[str, int, str]:
    priority = {
        "quote_timestamp": -100,
        "open_price": -90,
        "high_price": -89,
        "low_price": -88,
        "close_price": -87,
        "previous_close": -86,
        "price_change_pct": -85,
        "volume": -84,
        "turnover_rate": -83,
        "market_cap": -82,
    }
    if key in priority:
        return ("", priority[key], key.lower())
    category_rank = _price_return_group_rank(key)
    base_key = _strip_time_tokens(key)
    return (f"{category_rank:02d}-{base_key.lower()}", _time_rank(key), key.lower())


def _strip_time_tokens(key: str) -> str:
    prefixes = ("5Day", "10Day", "13Week", "26Week", "52Week", "3Month", "4Week")
    for prefix in prefixes:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    suffixes = ("TTM", "Annual", "Quarterly", "5Y", "3Y", "Yoy", "YTD", "Ytd")
    for suffix in suffixes:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    return key


def _time_rank(key: str) -> int:
    prefix_ranks = {
        "5Day": 5,
        "10Day": 10,
        "4Week": 28,
        "13Week": 91,
        "26Week": 182,
        "3Month": 90,
        "52Week": 364,
    }
    for prefix, rank in prefix_ranks.items():
        if key.startswith(prefix):
            return rank
    suffix_ranks = {
        "Quarterly": 800,
        "Yoy": 820,
        "TTM": 900,
        "Annual": 1000,
        "3Y": 1200,
        "5Y": 1500,
        "YTD": 600,
        "Ytd": 600,
    }
    for suffix, rank in suffix_ranks.items():
        if key.endswith(suffix):
            return rank
    if re.search(r"monthtodate", key, re.IGNORECASE):
        return 550
    if re.search(r"yeartodate", key, re.IGNORECASE):
        return 600
    return 0


def _price_return_group_rank(key: str) -> int:
    lower_key = key.lower()
    if "return" in lower_key or "pricerelativetosp500" in lower_key:
        return 2
    if any(token in lower_key for token in ("price", "weekhigh", "weeklow", "highdate", "lowdate")):
        return 1
    return 3
