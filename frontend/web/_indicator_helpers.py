"""Pure indicator display / formatting helpers.

Extracted from server.py — no logic changes.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _serialize_indicator_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _serialize_indicator_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_indicator_value(v) for v in value]
    return value


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
        shortened = shortened[: max_len - 1] + "\u2026"
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
    suffixes = (
        "TTM",
        "Annual",
        "Quarterly",
        "5Y",
        "3Y",
        "Yoy",
        "YTD",
        "Ytd",
        "4Week",
        "13Week",
        "26Week",
        "52Week",
    )
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
        "4Week": 28,
        "13Week": 91,
        "26Week": 182,
        "52Week": 364,
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
