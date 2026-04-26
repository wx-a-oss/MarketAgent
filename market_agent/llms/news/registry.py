"""Backward-compatible re-exports. Now lives in market_agent.llms.news_registry."""

from market_agent.llms.news_registry import *  # noqa: F401,F403
from market_agent.llms.news_registry import (
    get_news_provider,
    list_news_models,
    list_news_providers,
)

__all__ = ["get_news_provider", "list_news_models", "list_news_providers"]
