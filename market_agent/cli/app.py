import json
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from market_agent import MarketAgent

    app = typer.Typer(help="MarketAgent CLI — Finnhub-powered stock and company info")
    console = Console()

    @app.command("check")
    def check(
        symbol: str = typer.Argument(..., help="Ticker symbol (e.g., AAPL, MSFT, TSLA)"),
        format: str = typer.Option("table", "--format", help="Output format: table|json"),
        raw: bool = typer.Option(False, "--raw", help="Include raw API blobs in output (JSON only)"),
    ):
        agent = MarketAgent()
        data = agent.check_stock(symbol, include_raw=raw)

        if format == "json":
            console.print_json(json.dumps(data.model_dump(), default=str))
            return

        # default: table
        profile = data.profile
        quote = data.quote

        header = f"[b]{profile.name or data.symbol}[/b] ({data.symbol})"
        sub = f"{profile.exchange or ''}  •  {profile.country or ''}  •  IPO {profile.ipo or '—'}  •  Industry: {profile.industry or '—'}"
        console.print(Panel(f"""{sub}
Website: {profile.weburl or '—'}
Market Cap: {profile.market_cap if profile.market_cap is not None else '—'}""", title=header))

        # Quote table
        qt = Table(title="Quote", box=box.SIMPLE_HEAVY)
        qt.add_column("Field"); qt.add_column("Value")
        rows = [
            ("Current", str(quote.current)),
            ("Open", str(quote.open)),
            ("High", str(quote.high)),
            ("Low", str(quote.low)),
            ("Prev Close", str(quote.prev_close)),
            ("Change", str(quote.change)),
            ("% Change", f"{quote.percent}%"),
        ]
        for k, v in rows:
            qt.add_row(k, v)
        console.print(qt)

        # Metrics (a small selection if available)
        if data.metrics and isinstance(data.metrics.metric, dict) and data.metrics.metric:
            mt = Table(title="Selected Metrics", box=box.SIMPLE_HEAVY)
            mt.add_column("Metric"); mt.add_column("Value")
            keys = ["peBasicExclExtraTTM", "pbAnnual", "epsBasicExclExtraItemsTTM", "revenuePerShareTTM", "netDebtAnnual", "freeCashFlowPerShareTTM"]
            for k in keys:
                if k in data.metrics.metric and data.metrics.metric[k] is not None:
                    mt.add_row(k, str(data.metrics.metric[k]))
            console.print(mt)

        # Recommendations
        if data.recommendations:
            rt = Table(title="Recommendation Trends", box=box.SIMPLE_HEAVY)
            rt.add_column("Period"); rt.add_column("Strong Buy"); rt.add_column("Buy"); rt.add_column("Hold"); rt.add_column("Sell"); rt.add_column("Strong Sell")
            for r in data.recommendations[:6]:
                rt.add_row(str(r.period), str(r.strongBuy), str(r.buy), str(r.hold), str(r.sell), str(r.strongSell))
            console.print(rt)

        # EPS history
        if data.eps:
            et = Table(title="EPS Actual vs Estimate (recent)", box=box.SIMPLE_HEAVY)
            et.add_column("Period"); et.add_column("Actual"); et.add_column("Estimate")
            for e in data.eps[:6]:
                et.add_row(str(e.period), str(e.actual), str(e.estimate))
            console.print(et)

        # Peers
        if data.peers:
            pt = Table(title="Peers", box=box.SIMPLE_HEAVY)
            pt.add_column("Tickers")
            pt.add_row(", ".join(data.peers[:20]))
            console.print(pt)

    if __name__ == "__main__":
        app()