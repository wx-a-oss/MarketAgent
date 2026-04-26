"""Finnhub data source package."""

from .finnhub_client import FinnhubClient
from .finnhub_indicator_fetcher import FinnhubIndicatorFetcher
from .finnhub_news import FinnhubNewsSource, resolve_finnhub_news_source
from .news_interfaces import NewsSourceProvider
from .news_registry import get_news_source, list_news_sources, news_source_metadata

__all__ = [
    "FinnhubClient",
    "FinnhubIndicatorFetcher",
    "FinnhubNewsSource",
    "NewsSourceProvider",
    "get_news_source",
    "list_news_sources",
    "news_source_metadata",
    "resolve_finnhub_news_source",
]
