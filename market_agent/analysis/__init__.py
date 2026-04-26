"""Backward-compatible re-exports. Logic now lives in market_agent.services."""

from market_agent.services import (
    AnalysisProvider,
    OpenAIProvider,
    resolve_openai_provider,
    analyze_single_stock_sections,
)

__all__ = [
    "AnalysisProvider",
    "OpenAIProvider",
    "resolve_openai_provider",
    "analyze_single_stock_sections",
]
