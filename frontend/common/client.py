from __future__ import annotations

from market_agent.api import query_stock
from market_agent.models import QueryStockOutput


class StockFrontendClient:
    """Thin wrapper ensuring all frontends share the same stock query logic."""

    def query(self, symbol: str) -> QueryStockOutput:
        return query_stock(symbol)
