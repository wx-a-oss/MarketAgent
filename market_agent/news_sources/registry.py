"""Backward-compatible re-exports. Now lives in market_agent.datasources.finnhub.news_registry."""

from market_agent.datasources.finnhub.news_registry import *  # noqa: F401,F403
from market_agent.datasources.finnhub.news_registry import (
    get_news_source,
    list_news_sources,
    news_source_metadata,
)

__all__ = ["get_news_source", "list_news_sources", "news_source_metadata"]
