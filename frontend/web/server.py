from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from frontend.common import StockFrontendClient

app = FastAPI(
    title="MarketAgent Web Frontend",
    description="Lightweight HTML frontend powered by the shared MarketAgent stock API.",
)

client = StockFrontendClient()


@app.get("/", response_class=HTMLResponse)
async def index(symbol: str = Query("AAPL", description="Ticker symbol to query")) -> str:
    result = client.query(symbol)
    data = result.data

    peers = ", ".join(data.analytics.peers[:10]) if data.analytics.peers else "N/A"

    return f"""
    <html>
        <head>
            <title>MarketAgent – {data.symbol}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 2rem; }}
                .card {{ border: 1px solid #ddd; padding: 1.5rem; border-radius: 0.5rem; }}
                h1 {{ margin-top: 0; }}
                .metrics {{ margin-top: 1rem; }}
                .metrics dt {{ font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>{data.basics.company.name or data.symbol} ({data.symbol})</h1>
                <p>Price: {data.basics.price.current} (Δ {data.basics.price.change}, {data.basics.price.percent}%)</p>
                <p>Exchange: {data.basics.company.exchange or 'N/A'} | Industry: {data.basics.company.industry or 'N/A'}</p>
                <p>Peers: {peers}</p>
                <dl class="metrics">
                    <dt>P/E Ratio</dt><dd>{data.analytics.metrics.pe_ratio or 'N/A'}</dd>
                    <dt>P/B Ratio</dt><dd>{data.analytics.metrics.pb_ratio or 'N/A'}</dd>
                    <dt>EPS</dt><dd>{data.analytics.metrics.eps or 'N/A'}</dd>
                </dl>
            </div>
        </body>
    </html>
    """
