"""Registry for news-capable LLM providers."""

from __future__ import annotations

from typing import Dict, List, Optional

from market_agent.llms.news.interfaces import NewsProvider
from market_agent.llms.news.openai import (
    DEFAULT_NEWS_MODEL,
    resolve_openai_news_provider,
)


def get_news_provider(
    name: str,
    *,
    model: str = DEFAULT_NEWS_MODEL,
    api_key: Optional[str] = None,
    temperature: float = 0.2,
    timeout_sec: int = 60,
    use_web_search: Optional[bool] = None,
) -> NewsProvider:
    normalized = name.lower()
    if normalized == "openai":
        return resolve_openai_news_provider(
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_sec=timeout_sec,
            use_web_search=use_web_search,
        )
    raise ValueError(f"Unknown news provider: {name}")


def list_news_models() -> Dict[str, List[str]]:
    return {
        "openai": [
            DEFAULT_NEWS_MODEL,
            "gpt-5-mini",
            "gpt-5.2",
        ]
    }


def list_news_providers() -> List[str]:
    return ["openai"]


__all__ = ["get_news_provider", "list_news_models", "list_news_providers"]
