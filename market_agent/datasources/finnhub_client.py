from typing import Dict, Any, List
import finnhub  # pip install finnhub-python

class FinnhubClient:
    def __init__(self, api_key: str):
        self._client = finnhub.Client(api_key=api_key)

    # Individual calls
    def quote(self, symbol: str) -> Dict[str, Any]:
        return self._client.quote(symbol)

    def company_profile(self, symbol: str) -> Dict[str, Any]:
        # Newer SDK uses company_profile2
        return self._client.company_profile2(symbol=symbol)

    def basic_financials(self, symbol: str, metric: str = "all") -> Dict[str, Any]:
        return self._client.company_basic_financials(symbol, metric)

    def recommendation_trends(self, symbol: str) -> List[Dict[str, Any]]:
        return self._client.recommendation_trends(symbol)

    def earnings(self, symbol: str) -> Dict[str, Any]:
        # earnings (EPS surprise) - returns list
        return {"data": self._client.earnings(symbol)}

    def peers(self, symbol: str) -> List[str]:
        return self._client.company_peers(symbol)