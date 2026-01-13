"""
High-level indicator query helpers used by multiple frontends.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from market_agent.datasources import (
    FinnhubClient,
    FinnhubIndicatorFetcher,
    StockAnalysisIndicators,
    StockBaseIndicators,
)

DEFAULT_API_ENV_VAR = "FINNHUB_API_KEY"


@dataclass(slots=True)
class StockIndicatorSnapshot:
    """Container bundling base and analysis indicators for a stock symbol."""

    symbol: str
    base: StockBaseIndicators
    analysis: Optional[StockAnalysisIndicators]

    def as_dict(self) -> dict:
        """Serialize the snapshot into a JSON-friendly dict."""
        payload = {
            "symbol": self.symbol,
            "base": self.base.as_dict(),
        }
        if self.analysis is not None:
            payload["analysis"] = self.analysis.as_dict()
        return payload


def query_stock_indicators(
    symbol: str,
    *,
    api_key: Optional[str] = None,
    include_analysis: bool = True,
) -> StockIndicatorSnapshot:
    """
    Fetch indicator data for a stock symbol using the Finnhub-backed fetcher.

    Parameters
    ----------
    symbol:
        Ticker symbol (e.g. AAPL, MSFT).
    api_key:
        Optional Finnhub API key. Falls back to the ``FINNHUB_API_KEY`` env var.
    include_analysis:
        If False, skip the slower analysis fetch step.
    """

    resolved_key = api_key or os.getenv(DEFAULT_API_ENV_VAR)
    if not resolved_key:
        raise RuntimeError(
            "Finnhub API key is required. Set FINNHUB_API_KEY or pass api_key explicitly."
        )

    client = FinnhubClient(api_key=resolved_key)
    fetcher = FinnhubIndicatorFetcher(client)

    base = fetcher.build_base_indicators(symbol, include_analysis=include_analysis)
    analysis = None

    return StockIndicatorSnapshot(symbol=symbol, base=base, analysis=analysis)


__all__ = ["StockIndicatorSnapshot", "query_stock_indicators"]
