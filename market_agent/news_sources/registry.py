"""Registry for news source providers."""

from __future__ import annotations

from typing import Dict, List, Optional

from market_agent.news_sources.interfaces import NewsSourceProvider
from market_agent.news_sources.finnhub import resolve_finnhub_news_source


def get_news_source(
    name: str,
    *,
    api_key: Optional[str] = None,
) -> NewsSourceProvider:
    normalized = name.lower()
    if normalized == "finnhub":
        return resolve_finnhub_news_source(api_key=api_key)
    raise ValueError(f"Unknown news source: {name}")


def list_news_sources() -> List[str]:
    return ["finnhub"]


def news_source_metadata() -> Dict[str, str]:
    return {"finnhub": "Finnhub company news"}


__all__ = ["get_news_source", "list_news_sources", "news_source_metadata"]
