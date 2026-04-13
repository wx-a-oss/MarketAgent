"""Central model defaults for app/runtime configuration."""

from __future__ import annotations

import os
from typing import Dict


DEFAULT_MARKET_OPENAI_MODEL = (
    os.getenv("MARKETAGENT_MARKET_OPENAI_DEFAULT_MODEL", "gpt-5.4").strip() or "gpt-5.4"
)
DEFAULT_COMPANY_OPENAI_MODEL = (
    os.getenv("MARKETAGENT_COMPANY_OPENAI_DEFAULT_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"
)
# Backward-compatible alias for callers that still expect one shared OpenAI default.
DEFAULT_OPENAI_MODEL = DEFAULT_MARKET_OPENAI_MODEL

DEFAULT_PROVIDER_MODELS: Dict[str, str] = {
    "openai": DEFAULT_MARKET_OPENAI_MODEL,
    "perplexity": "sonar-pro",
    "gemini": "gemini-2.5-flash",
}


def get_default_model(provider_name: str = "openai") -> str:
    return DEFAULT_PROVIDER_MODELS.get(str(provider_name or "openai").lower(), DEFAULT_OPENAI_MODEL)


def get_default_market_model(provider_name: str = "openai") -> str:
    normalized = str(provider_name or "openai").lower()
    if normalized == "openai":
        return DEFAULT_MARKET_OPENAI_MODEL
    return get_default_model(normalized)


def get_default_company_model(provider_name: str = "openai") -> str:
    normalized = str(provider_name or "openai").lower()
    if normalized == "openai":
        return DEFAULT_COMPANY_OPENAI_MODEL
    return get_default_model(normalized)


__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_MARKET_OPENAI_MODEL",
    "DEFAULT_COMPANY_OPENAI_MODEL",
    "DEFAULT_PROVIDER_MODELS",
    "get_default_model",
    "get_default_market_model",
    "get_default_company_model",
]
