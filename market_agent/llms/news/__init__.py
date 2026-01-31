"""News provider registry exports."""

from .interfaces import NewsProvider
from .registry import get_news_provider, list_news_models, list_news_providers

__all__ = ["NewsProvider", "get_news_provider", "list_news_models", "list_news_providers"]
