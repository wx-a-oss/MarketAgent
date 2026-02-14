"""Prompt builder for weekly company news reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .common import dump_items_json
from .news_analysis_structured import ANALYSIS_FIELDS


# Weekly report currently uses structured analysis sections.
def build_weekly_report_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    articles: Iterable[Dict[str, Any]],
) -> str:
    section_lines = "\n".join(f"- {field}" for field, _ in ANALYSIS_FIELDS)
    return (
        "You are compiling a weekly report for {company} using the company's full-week news set.\n"
        "Combine the week's items into one coherent weekly report.\n"
        "Return a JSON object where each section below is present, and each value is an array of concise bullet points:\n"
        "{sections}\n"
        "Facts section requirements:\n"
        "- every bullet must include the relevant news datetime\n"
        "- order facts chronologically by datetime so progression across the week is clear\n"
        "Do not omit any section.\n"
        "News items JSON:\n{items}\n"
    ).format(
        company=company_name,
        sections=section_lines,
        items=dump_items_json(articles),
    )
