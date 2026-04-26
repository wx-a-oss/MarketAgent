"""Backward-compatible re-exports. Now lives in market_agent.datasources.finnhub.finnhub_news."""

from market_agent.datasources.finnhub.finnhub_news import *  # noqa: F401,F403
from market_agent.datasources.finnhub.finnhub_news import (
    FinnhubNewsSource,
    resolve_finnhub_news_source,
)

__all__ = ["FinnhubNewsSource", "resolve_finnhub_news_source"]
