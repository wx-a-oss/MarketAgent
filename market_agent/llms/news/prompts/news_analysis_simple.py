"""Simple metadata-based summary prompt for quick readability."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .common import dump_items_json, lines_to_prompt


# Lightweight version: summarize using metadata/brief snippets in easy-to-read sections.
def build_news_analysis_prompt_metadata_summary(
    company_name: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    lines = [
        f"Summarize these news items for {company_name} in simple words.",
        "Use only given metadata and brief content.",
        "Return ONLY valid JSON array.",
        "Each object must include:",
        "- news_date_time",
        "- news_title",
        "- news_source",
        "- news_source_link",
        "- summary (2-3 short sentences, but include all material facts)",
        "- key_facts (array of short bullet strings; include all material facts, no omissions)",
        "- critical_insights (array of short bullet strings; include key implications/risks/uncertainties)",
        "- why_it_matters (1-2 short sentences, decision-focused)",
        "- sentiment (bullish|bearish|neutral|mixed)",
        "Rules:",
        "- keep writing concise and easy to read",
        "- avoid jargon when possible",
        "- do not omit critical facts or key insights just to stay short",
        "- prioritize most material facts/insights first",
        "- if evidence is weak, state uncertainty briefly",
        "Input items JSON:",
        dump_items_json(items),
    ]
    return lines_to_prompt(lines)


# Backward-compatible alias.
def build_input_news_metadata_summary_prompt(
    company_name: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    return build_news_analysis_prompt_metadata_summary(company_name, items)
