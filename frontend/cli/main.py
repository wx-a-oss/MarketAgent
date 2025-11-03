from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from frontend.common import StockFrontendClient

app = typer.Typer(help="CLI frontend that surfaces stock indicators via MarketAgent.")
console = Console()


def _render_indicator_table(title: str, data: dict) -> Panel:
    table = Table(show_header=False, padding=(0, 1))
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    for key, value in data.items():
        if key == "symbol":
            continue
        display = "-" if value is None else str(value)
        table.add_row(key, display)

    return Panel(table, title=title, border_style="green")


@app.command("stock")
def stock(
    symbol: str = typer.Argument(..., help="Ticker symbol (e.g. AAPL, MSFT)"),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print raw JSON payload instead of formatted tables.",
    ),
    include_analysis: bool = typer.Option(
        True,
        "--analysis/--no-analysis",
        help="Toggle fetching of analysis indicators (may require extra API calls).",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="FINNHUB_API_KEY",
        help="Finnhub API key. Falls back to FINNHUB_API_KEY env var when omitted.",
    ),
) -> None:
    """Query indicators for a stock symbol using the shared MarketAgent API."""
    client = StockFrontendClient(api_key=api_key, include_analysis=include_analysis)
    snapshot = client.query(symbol)

    if json_output:
        console.print_json(json.dumps(snapshot.as_dict(), indent=2))
        return

    console.print(f"[bold green]Indicator snapshot for {snapshot.symbol}[/bold green]")
    console.print(_render_indicator_table("Base Indicators", snapshot.base.as_dict()))

    if snapshot.analysis is not None:
        console.print(
            _render_indicator_table(
                "Analysis Indicators", snapshot.analysis.as_dict()
            )
        )
    else:
        console.print("[yellow]Analysis indicators skipped.[/yellow]")


if __name__ == "__main__":
    app()
