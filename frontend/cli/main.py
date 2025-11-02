from __future__ import annotations

import typer
from rich.console import Console

from frontend.common import StockFrontendClient

app = typer.Typer(help="Frontend-only CLI that consumes the MarketAgent stock API.")
console = Console()
client = StockFrontendClient()


@app.command("stock")
def stock(
    symbol: str = typer.Argument(..., help="Ticker symbol (e.g. AAPL, MSFT)"),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Print raw JSON response instead of formatted text."
    ),
    include_raw: bool = typer.Option(
        False,
        "--raw",
        help="Include raw payloads returned by the upstream data provider.",
    ),
) -> None:
    """Query a stock snapshot using the shared MarketAgent API."""
    result = client.query(symbol, include_raw=include_raw)

    if json_output:
        console.print_json(result.model_dump_json(indent=2))
        return

    data = result.data
    console.print(f"[bold]{data.symbol}[/bold] {data.basics.company.name or ''}")
    console.print(f"Price: {data.basics.price.current} (change {data.basics.price.change})")


if __name__ == "__main__":
    app()
