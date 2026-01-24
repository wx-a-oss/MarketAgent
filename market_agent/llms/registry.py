"""Provider registry for LLM models."""

from __future__ import annotations

from typing import Dict, List, Optional

from market_agent.analysis.stock.interfaces import AnalysisProvider
from market_agent.llms.openai import resolve_openai_provider


def get_provider(
    name: str,
    *,
    model: str,
    api_key: Optional[str] = None,
    temperature: float = 0.2,
    timeout_sec: int = 30,
) -> AnalysisProvider:
    normalized = name.lower()
    if normalized == "openai":
        return resolve_openai_provider(
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )
    raise ValueError(f"Unknown provider: {name}")


def list_models() -> Dict[str, List[str]]:
    return {
        "openai": [
            "gpt-5-mini",
            "gpt-5.2",
        ]
    }


def list_providers() -> List[str]:
    return ["openai"]


__all__ = ["get_provider", "list_models", "list_providers"]
