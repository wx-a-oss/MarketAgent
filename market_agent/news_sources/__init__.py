"""Backward-compatible re-exports. News sources now live in market_agent.datasources.finnhub."""

from market_agent.datasources.finnhub.news_interfaces import NewsSourceProvider
from market_agent.datasources.finnhub.news_registry import (
    get_news_source,
    list_news_sources,
    news_source_metadata,
)

__all__ = ["NewsSourceProvider", "get_news_source", "list_news_sources", "news_source_metadata"]
