"""Shared prompt templates for analysis providers."""

from __future__ import annotations

import json
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You are a market analysis assistant. Provide a concise, actionable analysis "
    "for a single stock section. Use the provided current metrics only. "
    "Avoid investment advice or price targets. Return JSON."
)


def build_user_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Analyze this section. Return JSON with keys: summary, highlights, risks, "
        "questions. Keep each list to 3-5 short bullets.\n\nSection payload:\n"
        f"{json.dumps(payload, indent=2)}"
    )
