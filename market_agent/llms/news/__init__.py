"""Backward-compatible re-exports. Providers now live in market_agent.llms flat modules."""

from market_agent.llms.interfaces import NewsProvider
from market_agent.llms.news_registry import get_news_provider, list_news_models, list_news_providers

__all__ = ["NewsProvider", "get_news_provider", "list_news_models", "list_news_providers"]
