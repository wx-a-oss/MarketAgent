"""News source provider registry exports."""

from .interfaces import NewsSourceProvider
from .registry import get_news_source, list_news_sources, news_source_metadata

__all__ = ["NewsSourceProvider", "get_news_source", "list_news_sources", "news_source_metadata"]
