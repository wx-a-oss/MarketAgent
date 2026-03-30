from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Optional

from .common import _build_output_language_line


def _build_company_quick_price_intelligence_prompt(
    *,
    company_name: str,
    as_of_date: date,
    quick_input: Dict[str, Any],
    previous_run: Optional[Dict[str, Any]],
    output_language: str,
) -> str:
    del previous_run
    payload_json = json.dumps(
        {"quick_input": quick_input},
        ensure_ascii=False,
        indent=2,
    )
    language_line = _build_output_language_line(output_language)
    return (
        f"You are generating price intelligence for {company_name} as of {as_of_date.isoformat()}.\n"
        "Use a 1-year context to judge stock personality, regime, major price structure, and valuation context.\n"
        "Focus your written analysis on what changed and what matters now in roughly the last 2 months.\n"
        "Generate three blocks: Technical View, Fundamental/Market View, and Synthesis.\n"
        "Lead with a fair price zone and current price judgment.\n"
        "Return JSON only.\n"
        f"{language_line}"
        "Required JSON schema:\n"
        "{\n"
        '  "current_price": 0,\n'
        '  "fair_price_zone": {"low": 0, "mid": 0, "high": 0, "basis": "..."},\n'
        '  "price_position": {"label": "below_fair|near_fair|above_fair", "explanation": "..."},\n'
        '  "bottom_line": "...",\n'
        '  "technical_view": {\n'
        '    "summary": "...",\n'
        '    "fair_price_read": "...",\n'
        '    "signals": ["..."],\n'
        '    "risks": ["..."]\n'
        '  },\n'
        '  "fundamental_market_view": {\n'
        '    "summary": "...",\n'
        '    "fair_price_read": "...",\n'
        '    "signals": ["..."],\n'
        '    "risks": ["..."]\n'
        '  },\n'
        '  "synthesis_view": {\n'
        '    "summary": "...",\n'
        '    "dominant_method": "technical|fundamental_market|balanced",\n'
        '    "triggers": ["..."],\n'
        '    "invalidations": ["..."]\n'
        '  }\n'
        "}\n"
        "Do not add extra top-level fields beyond this schema.\n"
        "Do not add extra nested fields beyond this schema.\n\n"
        f"Inputs JSON:\n{payload_json}\n"
    )
