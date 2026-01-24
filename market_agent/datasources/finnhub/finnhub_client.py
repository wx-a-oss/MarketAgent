from __future__ import annotations

from typing import Any, Callable, Dict, List, TypeVar

import finnhub  # pip install finnhub-python
import requests


T = TypeVar("T")


class FinnhubClient:
    def __init__(self, api_key: str):
        self._client = finnhub.Client(api_key=api_key)

    def quote(self, symbol: str) -> Dict[str, Any]:
        return self._safe_call(lambda: self._client.quote(symbol), default={})

    def company_profile(self, symbol: str) -> Dict[str, Any]:
        return self._safe_call(
            lambda: self._client.company_profile2(symbol=symbol), default={}
        )

    def basic_financials(self, symbol: str, metric: str = "all") -> Dict[str, Any]:
        return self._safe_call(
            lambda: self._client.company_basic_financials(symbol, metric),
            default={},
        )

    def earnings(self, symbol: str) -> Dict[str, Any]:
        data = self._safe_call(lambda: self._client.earnings(symbol), default=[])
        return {"data": data}

    def peers(self, symbol: str) -> List[str]:
        return self._safe_call(lambda: self._client.company_peers(symbol), default=[])

    @staticmethod
    def _safe_call(func: Callable[[], T], default: T) -> T:
        try:
            return func()
        except requests.exceptions.RequestException:
            return default
