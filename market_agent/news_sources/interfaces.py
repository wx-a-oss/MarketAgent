"""Backward-compatible re-exports. Now lives in market_agent.datasources.finnhub.news_interfaces."""

from market_agent.datasources.finnhub.news_interfaces import *  # noqa: F401,F403
from market_agent.datasources.finnhub.news_interfaces import NewsSourceProvider

__all__ = ["NewsSourceProvider"]
