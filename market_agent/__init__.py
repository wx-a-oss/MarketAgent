"""MarketAgent package exports."""

from __future__ import annotations

from typing import Optional

from market_agent.api import StockIndicatorSnapshot, query_stock_indicators


class MarketAgent:
    """Convenience wrapper for querying stock indicators."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    def query_stock(
        self, symbol: str, *, include_analysis: bool = True
    ) -> StockIndicatorSnapshot:
        return query_stock_indicators(
            symbol, api_key=self._api_key, include_analysis=include_analysis
        )


__all__ = ["MarketAgent", "StockIndicatorSnapshot", "query_stock_indicators"]
