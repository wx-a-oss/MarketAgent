"""Central model defaults for app/runtime configuration."""

from __future__ import annotations

import os
from typing import Dict


DEFAULT_OPENAI_MODEL = os.getenv("MARKETAGENT_OPENAI_DEFAULT_MODEL", "gpt-5.4").strip() or "gpt-5.4"

DEFAULT_PROVIDER_MODELS: Dict[str, str] = {
    "openai": DEFAULT_OPENAI_MODEL,
    "perplexity": "sonar-pro",
    "gemini": "gemini-2.5-flash",
}


def get_default_model(provider_name: str = "openai") -> str:
    return DEFAULT_PROVIDER_MODELS.get(str(provider_name or "openai").lower(), DEFAULT_OPENAI_MODEL)


__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_PROVIDER_MODELS",
    "get_default_model",
]
