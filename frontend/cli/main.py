from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from frontend.common import StockFrontendClient

app = typer.Typer(help="CLI frontend that surfaces stock indicators via MarketAgent.")
console = Console()


def _render_indicator_sections(data: dict) -> List[Panel]:
    panels: List[Panel] = []
    for section, rows in _group_indicators(data):
        table = Table(show_header=False, padding=(0, 1))
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        for label, value in rows:
            display = "-" if value is None else str(value)
            table.add_row(label, display)
        panels.append(Panel(table, title=section, border_style="green"))
    return panels


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
        help="Toggle fetching of extended indicators (may require extra API calls).",
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
    for panel in _render_indicator_sections(snapshot.base.as_dict()):
        console.print(panel)


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
        "3rd Party Recommendation",
    ]

    grouped: List[Tuple[str, List[Tuple[str, object]]]] = []
    for section in ordered_sections:
        rows = sections.get(section)
        if not rows:
            continue
        rows.sort(key=lambda item: _sort_key(item[0]))
        grouped.append((section, [(_label_for_key(k), v) for k, v in rows]))
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
        return "3rd Party Recommendation"

    return "Price & Returns"


def _label_for_key(key: str) -> str:
    overrides = {
        "3MonthAvgDailyReturnStdDev": "3MonthAvgDailyReturnVolatilityStdDev",
        "recommendation": "FinnhubRecommendation",
        "recommendation_counts": "FinnhubRecommendationCounts",
        "focfCagr5Y": "FreeOperatingCashFlowCagr5Y",
        "tbvCagr5Y": "TangibleBookValueCagr5Y",
    }
    return overrides.get(key, _to_title_camel(key))


def _to_title_camel(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", value)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    parts = [part for part in spaced.split() if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _sort_key(key: str) -> Tuple[str, int, str]:
    priority = {
        "quote_timestamp": -100,
        "open_price": -90,
        "high_price": -89,
        "low_price": -88,
        "close_price": -87,
        "previous_close": -86,
        "market_cap": -85,
        "volume": -84,
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


if __name__ == "__main__":
    app()
