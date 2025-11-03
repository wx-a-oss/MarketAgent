from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from frontend.common import StockFrontendClient

app = FastAPI(
    title="MarketAgent Web Frontend",
    description="Lightweight HTML frontend powered by the shared MarketAgent stock API.",
)

client = StockFrontendClient()


@app.get("/", response_class=HTMLResponse)
async def index(
    symbol: Optional[str] = Query(
        None, description="Ticker symbol to query (e.g. AAPL, MSFT)"
    ),
    analysis: str = Query(
        "true", description="Whether to include analysis indicators (true/false)"
    ),
) -> str:
    include_analysis = analysis.lower() != "false"
    symbol_value = (symbol or "").strip().upper()
    snapshot = (
        client.query(symbol_value, include_analysis=include_analysis)
        if symbol_value
        else None
    )

    base_rows = ""
    if snapshot is not None:
        base_rows = "".join(
            f"<tr><th>{key}</th><td>{_format_value(value)}</td></tr>"
            for key, value in snapshot.base.as_dict().items()
            if key != "symbol"
        )

    if snapshot is not None and snapshot.analysis is not None:
        analysis_rows = "".join(
            f"<tr><th>{key}</th><td>{_format_value(value)}</td></tr>"
            for key, value in snapshot.analysis.as_dict().items()
            if key != "symbol"
        )
        analysis_section = f"""
            <section class="card">
                <h2>Analysis Indicators</h2>
                <table>{analysis_rows}</table>
            </section>
        """
    else:
        analysis_section = """
            <section class="card">
                <h2>Analysis Indicators</h2>
                <p class="muted">Enter a ticker symbol to fetch analysis indicators.</p>
            </section>
        """

    base_section = (
        f"""
            <section class="card">
                <h2>Base Indicators</h2>
                <table>{base_rows}</table>
            </section>
        """
        if snapshot is not None
        else """
            <section class="card">
                <h2>Base Indicators</h2>
                <p class="muted">Enter a ticker symbol to fetch indicators.</p>
            </section>
        """
    )

    return f"""
        <html>
            <head>
                <title>MarketAgent – Stock Indicators</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }}
                    .container {{ max-width: 960px; margin: auto; display: grid; gap: 1.5rem; }}
                    .card {{ background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
                    h1, h2 {{ margin-top: 0; }}
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ padding: 0.35rem 0.5rem; text-align: left; border-bottom: 1px solid #eee; }}
                    th {{ width: 40%; color: #555; }}
                    .muted {{ color: #888; }}
                    form {{ display: flex; gap: 0.5rem; }}
                    input[type="text"] {{ flex: 1; padding: 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }}
                    button {{ padding: 0.65rem 1.2rem; border: none; border-radius: 0.5rem; background: #2563eb; color: white; cursor: pointer; }}
                    button:hover {{ background: #1d4ed8; }}
                    label {{ display: flex; align-items: center; gap: 0.5rem; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <section class="card">
                        <h1>Stock Indicators</h1>
                        <form method="get">
                            <input type="text" name="symbol" value="{symbol_value}" placeholder="Enter ticker (e.g. AAPL)" required />
                            <label>
                                <select name="analysis">
                                    <option value="true" {"selected" if include_analysis else ""}>Include analysis</option>
                                    <option value="false" {"selected" if not include_analysis else ""}>Skip analysis</option>
                                </select>
                            </label>
                            <button type="submit">Query</button>
                        </form>
                    </section>
                    {base_section}
                    {analysis_section}
                </div>
            </body>
        </html>
    """


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)
