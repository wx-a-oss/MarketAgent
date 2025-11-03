"""
Indicator data structures for stock-related metrics.

These classes provide a lightweight way to bundle together raw indicator values
before they are persisted or sent to downstream consumers.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Return indicator values merged with any extra attributes."""
        data = {
            "symbol": self.symbol,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "market_cap": self.market_cap,
        }
        if self.extra:
            data.update(self.extra)
        return {key: value for key, value in data.items() if value is not None}


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
        return {key: value for key, value in data.items() if value is not None}
