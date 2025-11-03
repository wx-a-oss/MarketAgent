from __future__ import annotations

from typing import Optional

from market_agent.api import StockIndicatorSnapshot, query_stock_indicators


class StockFrontendClient:
    """Thin wrapper ensuring all frontends share the same stock query logic."""

    def __init__(self, api_key: Optional[str] = None, include_analysis: bool = True):
        self._api_key = api_key
        self._include_analysis = include_analysis

    def query(
        self, symbol: str, *, include_analysis: Optional[bool] = None
    ) -> StockIndicatorSnapshot:
        effective_include = (
            self._include_analysis if include_analysis is None else include_analysis
        )
        return query_stock_indicators(
            symbol,
            api_key=self._api_key,
            include_analysis=effective_include,
        )
