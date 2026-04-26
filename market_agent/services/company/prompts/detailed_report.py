from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict

from .common import _build_output_language_line


def _build_company_price_intelligence_prompt(
    company_name: str,
    *,
    as_of_date: date,
    status_input: Dict[str, Any],
    output_language: str = "zh-CN",
) -> str:
    payload_json = json.dumps(status_input, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"You are building a detailed stock-price technical report for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal: produce a comprehensive long-form report explaining where the current stock price sits inside its recent price history, how volume has behaved, what kind of price structure the stock is showing, and what matters next by short, medium, and long horizon.\n"
        "Use only the attached price and volume context from our own database.\n"
        "Do not use company news, market news, macro events, fundamentals, products, earnings, or outside narratives.\n"
        "Stay grounded in price action, trend structure, moving averages, highs/lows, volatility, range behavior, and participation/volume.\n"
        "Be detailed and preserve important nuance. Do not compress this into a short memo.\n"
        "You must explicitly separate short / medium / long horizon views.\n"
        "You must identify the stock personality and which horizon currently dominates, if one horizon clearly dominates.\n"
        "Every horizon view must include confidence, price judgment, rationale, watch signals, and invalidation conditions.\n"
        "The output_markdown must be a long-form technical report based only on the supplied price window.\n"
        "Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "technical_summary": "detailed summary",\n'
        '  "dominant_personality": {"label": "text", "dominant_horizon": "short|medium|long|balanced", "why": "text"},\n'
        '  "price_position_summary": "text",\n'
        '  "volume_participation": "text",\n'
        '  "volatility_range_context": "text",\n'
        '  "short_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "medium_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "long_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "risk_map": ["..."],\n'
        '  "uncertainty_map": ["..."],\n'
        '  "output_markdown": "a comprehensive long-form markdown report with sections: Technical Summary, Price Position, Trend Structure, Volume and Participation, Volatility and Range, Short Horizon, Medium Horizon, Long Horizon, Risks and Uncertainties, Bottom Line"\n'
        "}\n"
        "Requirements for output_markdown:\n"
        "- It must be a detailed technical-style report, not a short memo.\n"
        "- Explain what changed recently in price behavior, what looks durable, and what looks noisy.\n"
        "- Preserve important evidence and nuance from the supplied price and volume inputs.\n"
        "- Use headings and bullets so the report is readable, but do not make it overly compressed.\n"
        f"Inputs JSON:\n{payload_json}\n"
    )
