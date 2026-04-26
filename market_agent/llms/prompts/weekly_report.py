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
    output_language: str = "en",
) -> str:
    section_lines = "\n".join(f"- {field}" for field, _ in ANALYSIS_FIELDS)
    language_line = ""
    normalized_lang = str(output_language or "en").strip().lower()
    if normalized_lang in {"zh", "zh-cn", "zh_hans", "chinese", "simplified chinese"}:
        language_line = "Write all section content in Simplified Chinese.\n"
    return (
        "You are compiling a weekly report for {company} using the company's full-week news set.\n"
        "Inputs may include raw news-derived items and/or daily reports; combine them into one coherent weekly report.\n"
        "Ignore duplicate or near-duplicate coverage across items and across days.\n"
        "Keep all material company-related developments and rank by importance.\n"
        "{language_line}"
        "Return a JSON object where each section below is present, and each value is an array of concise bullet points:\n"
        "{sections}\n"
        "Facts section requirements:\n"
        "- every bullet must include the relevant news datetime\n"
        "- order facts chronologically by datetime so progression across the week is clear\n"
        "- if an item is a daily report summary, preserve chronology using that report date\n"
        "Do not omit any section.\n"
        "News items JSON:\n{items}\n"
    ).format(
        company=company_name,
        language_line=language_line,
        sections=section_lines,
        items=dump_items_json(articles),
    )
