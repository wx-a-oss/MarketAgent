"""Registry for news-capable LLM providers."""

from __future__ import annotations

from typing import Dict, List, Optional

from market_agent.config.models import OPENAI_ANALYSIS_MODELS
from market_agent.llms.gemini_news import (
    DEFAULT_GEMINI_MODEL,
    resolve_gemini_news_provider,
)
from market_agent.llms.interfaces import NewsProvider
from market_agent.llms.openai_news import (
    DEFAULT_NEWS_MODEL,
    resolve_openai_news_provider,
)
from market_agent.llms.perplexity_news import (
    DEFAULT_PERPLEXITY_MODEL,
    resolve_perplexity_news_provider,
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
    if normalized == "perplexity":
        return resolve_perplexity_news_provider(
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )
    if normalized == "gemini":
        return resolve_gemini_news_provider(
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )
    raise ValueError(f"Unknown news provider: {name}")


def list_news_models() -> Dict[str, List[str]]:
    return {
        "openai": list(OPENAI_ANALYSIS_MODELS),
        "perplexity": [
            DEFAULT_PERPLEXITY_MODEL,
            "sonar",
            "sonar-pro",
        ],
        "gemini": [
            DEFAULT_GEMINI_MODEL,
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ],
    }


def list_news_providers() -> List[str]:
    return ["openai", "perplexity", "gemini"]


__all__ = ["get_news_provider", "list_news_models", "list_news_providers"]
