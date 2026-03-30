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
        f"You are building a detailed company stock report for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal: produce a comprehensive long-form report explaining where the current stock price sits, why it sits there, what the company has been doing, what the market is pricing, and what matters next by short, medium, and long horizon.\n"
        "This is the deep-dive report, not the short daily price-intelligence note.\n"
        "Use company daily reports as the primary company source. Use company price context, market daily summaries, and macro context to refine the judgment. Use raw-news fallback only when daily-report coverage is missing.\n"
        "Be detailed and preserve important nuance. Do not compress this into a short memo.\n"
        "Explain both the business/fundamental side and the market/trading side.\n"
        "You must explicitly separate short / medium / long horizon views.\n"
        "You must identify the stock personality and which horizon currently dominates, if one horizon clearly dominates.\n"
        "Every horizon view must include confidence, price judgment, rationale, watch signals, and invalidation conditions.\n"
        "The output_markdown must be materially longer and more detailed than the short price-intelligence product.\n"
        "Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "company_summary": "detailed summary",\n'
        '  "dominant_personality": {"label": "text", "dominant_horizon": "short|medium|long|balanced", "why": "text"},\n'
        '  "price_position_summary": "text",\n'
        '  "market_regime_context": "text",\n'
        '  "decision_brief": {"summary": "text", "key_reasons": ["..."], "top_watch_signals": ["..."]},\n'
        '  "research_memo": {"company_state": "text", "market_belief": "text", "advantages": ["..."], "disadvantages": ["..."], "certainties": ["..."], "uncertainties": ["..."], "valuation_vs_expectations": "text"},\n'
        '  "trader_view": {"behavior_driver": "text", "setup_fit": ["..."], "entry_signals": ["..."], "exit_signals": ["..."], "wait_signals": ["..."], "short_term_notes": "text"},\n'
        '  "short_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "medium_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "long_horizon_view": {"confidence": 0.0, "price_judgment": "text", "rationale": ["..."], "watch_signals": ["..."], "invalidations": ["..."]},\n'
        '  "signals_to_watch": ["..."],\n'
        '  "risk_map": ["..."],\n'
        '  "uncertainty_map": ["..."],\n'
        '  "trading_style_fit": ["..."],\n'
        '  "supporting_reasoning": ["..."],\n'
        '  "output_markdown": "a comprehensive long-form markdown report with sections: Executive Summary, Price Position, Company Progress and Operating Story, Active Storylines, Earnings and Fundamentals, Market and Macro Context, Trader Lens, Short Horizon, Medium Horizon, Long Horizon, Signals to Watch, Risks and Uncertainties, Final Bottom Line"\n'
        "}\n"
        "Requirements for output_markdown:\n"
        "- It must be a detailed research-style report, not a short memo.\n"
        "- Explain what changed recently, what is durable, what is noisy, and what the market seems to be pricing.\n"
        "- Preserve important evidence and nuance from company, market, and macro inputs.\n"
        "- Use headings and bullets so the report is readable, but do not make it overly compressed.\n"
        f"Inputs JSON:\n{payload_json}\n"
    )
