"""
Indicator data structures for stock-related metrics.

These classes provide a lightweight way to bundle together raw indicator values
before they are persisted or sent to downstream consumers.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional


def _format_base_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key == "quote_timestamp":
        return _format_timestamp(value)
    if key == "rsi":
        return _format_percent(value)
    if key == "macd":
        return _format_currency(value)

    price_keys = {
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "previous_close",
    }
    volume_keys = {"volume"}
    percent_keys = {"short_interest_pct_float", "fcf_margin", "cash_conversion"}
    ratio_keys = {"beta"}
    compact_currency_keys = {
        "market_cap",
        "enterprise_value",
        "cash_and_equivalents",
        "total_debt",
        "capex",
        "operating_cash_flow",
        "free_cash_flow",
    }

    if key in price_keys:
        return _format_currency(value)
    if key in volume_keys:
        return _format_shares(value)
    if key in percent_keys:
        return _format_percent(value)
    if key in ratio_keys:
        return _format_ratio(value)
    if key in compact_currency_keys:
        return _format_compact_currency(value)

    formatted_metric = _format_metric_value(key, value)
    if formatted_metric is not None:
        return formatted_metric

    if isinstance(value, float):
        return f"{value:.2f}"
    return value


def _format_analysis_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key == "moving_averages" and isinstance(value, dict):
        return {ma_key: _format_currency(ma_val) for ma_key, ma_val in value.items()}
    if key == "rsi":
        return _format_percent(value)
    if key == "macd":
        return _format_currency(value)
    if key == "beta":
        return _format_ratio(value)
    return value


def _format_metric_value(key: str, value: Any) -> Optional[Any]:
    if value is None:
        return None
    lower_key = key.lower()

    if key in {"10DayAverageTradingVolume", "3MonthAverageTradingVolume"}:
        return _format_shares_from_millions(value)

    if "marketcapitalization" in lower_key:
        return _format_compact_currency(value)

    if "weekhigh" in lower_key or "weeklow" in lower_key:
        return _format_currency(value)

    if any(token in lower_key for token in ("pershare", "eps", "netincomeemployee")):
        return _format_currency(value)

    ratio_tokens = (
        "currentratio",
        "debt/equity",
        "totaldebt/totalequity",
        "ev/",
        "coverage",
    )
    if any(token in lower_key for token in ratio_tokens) or lower_key.startswith("pe"):
        return _format_ratio(value)

    percent_tokens = (
        "return",
        "growth",
        "margin",
        "cagr",
        "yoy",
        "payout",
        "pricerelativetosp500",
        "std",
    )
    if any(token in lower_key for token in percent_tokens):
        return _format_percent(value)

    return None


def _format_currency(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    return f"${numeric:.2f}"


def _format_compact_currency(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    compact = _format_market_cap(numeric)
    return f"${compact}" if compact is not None else value


def _format_percent(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    return f"{numeric:.2f}%"


def _format_ratio(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    return f"{numeric:.2f}x"


def _format_shares(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    abs_value = abs(numeric)
    if abs_value >= 1_000_000_000:
        scaled = numeric / 1_000_000_000
        unit = "B"
    elif abs_value >= 1_000_000:
        scaled = numeric / 1_000_000
        unit = "M"
    elif abs_value >= 1_000:
        scaled = numeric / 1_000
        unit = "K"
    else:
        scaled = numeric
        unit = ""
    if unit:
        return f"{scaled:.2f}{unit} shares"
    return f"{scaled:.2f} shares"


def _format_shares_from_millions(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    return _format_shares(numeric * 1_000_000)


def _format_market_cap(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    # Finnhub market cap is reported in millions, so scale from that base.
    abs_value = abs(numeric)
    if abs_value >= 1_000_000:
        scaled = numeric / 1_000_000
        unit = "T"
    elif abs_value >= 1_000:
        scaled = numeric / 1_000
        unit = "B"
    else:
        scaled = numeric
        unit = "M"
    return f"{scaled:.2f}{unit}"


def _format_timestamp(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    try:
        pacific = ZoneInfo("America/Los_Angeles")
        timestamp = datetime.fromtimestamp(numeric, tz=pacific)
    except (OverflowError, OSError, ValueError):
        return value
    return timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class StockBaseIndicators:
    """Holds basic price and volume information for a specific stock symbol."""

    symbol: str
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    beta: Optional[float] = None
    short_interest_pct_float: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None
    capex: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    fcf_margin: Optional[float] = None
    cash_conversion: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Return indicator values merged with any extra attributes."""
        ordered_keys = [
            "symbol",
            "quote_timestamp",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "previous_close",
            "volume",
            "market_cap",
            "enterprise_value",
            "beta",
            "short_interest_pct_float",
            "cash_and_equivalents",
            "total_debt",
            "capex",
            "operating_cash_flow",
            "free_cash_flow",
            "fcf_margin",
            "cash_conversion",
        ]
        data: Dict[str, Any] = {
            "symbol": self.symbol,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "market_cap": self.market_cap,
            "enterprise_value": self.enterprise_value,
            "beta": self.beta,
            "short_interest_pct_float": self.short_interest_pct_float,
            "cash_and_equivalents": self.cash_and_equivalents,
            "total_debt": self.total_debt,
            "capex": self.capex,
            "operating_cash_flow": self.operating_cash_flow,
            "free_cash_flow": self.free_cash_flow,
            "fcf_margin": self.fcf_margin,
            "cash_conversion": self.cash_conversion,
        }
        if self.extra:
            data.update(self.extra)
        ordered = []
        seen = set()
        for key in ordered_keys:
            if key in data:
                ordered.append((key, data[key]))
                seen.add(key)
        for key, value in data.items():
            if key not in seen:
                ordered.append((key, value))
        return {
            key: _format_base_value(key, value)
            for key, value in ordered
            if value is not None
        }


@dataclass(slots=True)
class StockAnalysisIndicators:
    """Captures derived metrics that result from analysing base stock data."""

    symbol: str
    moving_averages: Dict[str, float] = field(default_factory=dict)
    rsi: Optional[float] = None
    macd: Optional[float] = None
    beta: Optional[float] = None
    recommendation: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Return indicator values merged with any extra attributes."""
        data: Dict[str, Any] = {
            "symbol": self.symbol,
            "moving_averages": self.moving_averages or None,
            "rsi": self.rsi,
            "macd": self.macd,
            "beta": self.beta,
            "recommendation": self.recommendation,
        }
        if self.extra:
            data.update(self.extra)
        return {
            key: _format_analysis_value(key, value)
            for key, value in data.items()
            if value is not None
        }
