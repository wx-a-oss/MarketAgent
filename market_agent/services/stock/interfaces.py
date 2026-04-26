"""Backward-compatible re-exports. AnalysisProvider now lives in market_agent.llms.interfaces."""

from market_agent.llms.interfaces import AnalysisProvider

__all__ = ["AnalysisProvider"]
