"""Model-backed analysis for a single stock, grouped by indicator section."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from market_agent.api import StockIndicatorSnapshot

from .interfaces import AnalysisProvider
from market_agent.llms.openai import resolve_openai_provider
from .schema import normalize_section_result


def analyze_single_stock_sections(
    snapshot: StockIndicatorSnapshot,
    *,
    provider: Optional[AnalysisProvider] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-5-mini",
    temperature: float = 0.2,
    timeout_sec: int = 30,
) -> Dict[str, Any]:
    """
    Analyze each indicator section for a single stock using a model provider.

    Parameters
    ----------
    snapshot:
        Current indicator snapshot (base indicators already include analysis fields).
    provider:
        Optional analysis provider. Defaults to OpenAI if omitted.
    api_key:
        OpenAI API key. Falls back to OPENAI_API_KEY env var when using OpenAI.
    model:
        OpenAI model name.
    temperature:
        Sampling temperature for the model.
    timeout_sec:
        HTTP timeout for the API request.
    """

    analyzer = provider or resolve_openai_provider(
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )

    sections = _group_indicators(snapshot.base.as_dict())
    results: Dict[str, Any] = {
        "symbol": snapshot.symbol,
        "provider": analyzer.name,
        "sections": {},
    }

    for section, rows in sections:
        current_metrics = {key: value for key, value in rows}
        payload = {
            "symbol": snapshot.symbol,
            "section": section,
            "current": current_metrics,
        }
        raw = analyzer.analyze_section(payload)
        results["sections"][section] = normalize_section_result(raw).as_dict()

    return results


def _group_indicators(data: Dict[str, Any]) -> List[Tuple[str, List[Tuple[str, Any]]]]:
    sections: Dict[str, List[Tuple[str, Any]]] = {}
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

    grouped: List[Tuple[str, List[Tuple[str, Any]]]] = []
    for section in ordered_sections:
        rows = sections.get(section)
        if not rows:
            continue
        rows.sort(key=lambda item: _sort_key(item[0]))
        grouped.append((section, rows))
    return grouped


def _classify_indicator(key: str) -> str:
    lower_key = key.lower()

    if key == "quote_timestamp":
        return "Quote"
    if key == "previous_close":
        return "Price & Returns"

    if key in {"beta", "moving_averages", "rsi", "macd"}:
        return "Price & Returns"

    if any(token in lower_key for token in ("volume", "liquidity")):
        return "Volume & Liquidity"

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

    return "Price & Returns"


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


def _price_return_group_rank(key: str) -> int:
    lower_key = key.lower()
    if "return" in lower_key or "pricerelativetosp500" in lower_key:
        return 2
    if any(token in lower_key for token in ("price", "weekhigh", "weeklow", "highdate", "lowdate")):
        return 1
    return 3


def _strip_time_tokens(key: str) -> str:
    prefixes = ("5Day", "10Day", "13Week", "26Week", "52Week", "3Month", "4Week")
    for prefix in prefixes:
        if key.startswith(prefix):
            key = key[len(prefix) :]
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
