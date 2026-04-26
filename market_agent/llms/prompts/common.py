"""Shared generic helpers for news prompts."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def lines_to_prompt(lines: List[str]) -> str:
    """Join prompt lines and ensure a trailing newline."""
    return "\n".join(lines) + "\n"


def dump_items_json(items: Iterable[Dict[str, Any]]) -> str:
    """Serialize prompt input items to compact JSON."""
    return json.dumps(list(items))
