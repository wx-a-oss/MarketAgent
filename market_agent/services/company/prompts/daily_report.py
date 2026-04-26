from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

from .common import _build_output_language_line


def _build_company_daily_report_prompt(
    company_name: str,
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    prompt_style: str,
    output_language: str = "zh-CN",
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Please summarize all {company_name} news for {target_date.isoformat()}.\n"
        "Goal: help me quickly understand what happened to the company today, why it matters, and what to watch next.\n"
        "Requirements:\n"
        "- Ignore duplicate or near-duplicate news items.\n"
        "- Keep all material points and do not omit important company-related information.\n"
        "- Ignore points not related to this company or its market/investor outlook.\n"
        "- Rank information by importance to this company (most important first).\n"
        "- Try to open links first for fuller context. If inaccessible, use available content and best available information.\n"
        "- Use a clear layered structure that is easy to read.\n"
        "- Start with a short top summary.\n"
        "- Then list the important news items in importance order.\n"
        "- For each important news item, include exactly two bullet labels: Facts and Impact.\n"
        "- Do not add a separate watch or follow-up subsection for each item.\n"
        "- End with one final section for what investors should watch next.\n"
        "- In that final section, include concise bullet points on upcoming catalysts, risks, confirmations, or developments that may matter next.\n"
        f"{language_line}"
        f"News items JSON:\n{items_json}\n"
    )
