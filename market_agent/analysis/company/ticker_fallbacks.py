"""Manual company-name to ticker fallbacks for weak external resolution."""

from __future__ import annotations

from typing import Optional

_COMPANY_TICKER_FALLBACKS = {
    "alphabet": "GOOGL",
    "alphabet inc": "GOOGL",
    "alphabet inc.": "GOOGL",
    "amazon": "AMZN",
    "amazon.com": "AMZN",
    "amazon.com inc": "AMZN",
    "amazon.com inc.": "AMZN",
    "apple": "AAPL",
    "apple inc": "AAPL",
    "apple inc.": "AAPL",
    "google": "GOOGL",
    "google inc": "GOOGL",
    "google inc.": "GOOGL",
    "meta": "META",
    "meta platforms": "META",
    "meta platforms inc": "META",
    "meta platforms inc.": "META",
    "microsoft": "MSFT",
    "microsoft corp": "MSFT",
    "microsoft corporation": "MSFT",
    "nvidia": "NVDA",
    "nvidia corp": "NVDA",
    "nvidia corporation": "NVDA",
    "oracle": "ORCL",
    "oracle corp": "ORCL",
    "oracle corporation": "ORCL",
    "tesla": "TSLA",
    "tesla inc": "TSLA",
    "tesla inc.": "TSLA",
}


def resolve_company_ticker_fallback(company_name: str) -> Optional[str]:
    normalized = str(company_name or "").strip().lower()
    if not normalized:
        return None
    return _COMPANY_TICKER_FALLBACKS.get(normalized)


__all__ = ["resolve_company_ticker_fallback"]
