"""Backward-compatible re-exports. Logic now lives in market_agent.services.stock."""

from market_agent.services.stock import (
    AnalysisProvider,
    OpenAIProvider,
    resolve_openai_provider,
    get_provider,
    list_models,
    list_providers,
    analyze_single_stock_sections,
)

__all__ = [
    "AnalysisProvider",
    "OpenAIProvider",
    "resolve_openai_provider",
    "get_provider",
    "list_models",
    "list_providers",
    "analyze_single_stock_sections",
]
