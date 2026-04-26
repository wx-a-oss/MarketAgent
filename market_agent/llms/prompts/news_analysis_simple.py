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
        "Input metadata may only include headline/title, datetime, source link, and brief summary.",
        "For each item, open the source link first and extract key details from the full article when possible.",
        "If the source link is inaccessible or incomplete, use web search to recover key details.",
        "Do not just rewrite the provided summary when fuller source information is available.",
        "Return ONLY valid JSON array.",
        "Each object must include:",
        "- news_date_time",
        "- news_title",
        "- news_source",
        "- news_source_link",
        "- summary",
        "- key_facts (array of short bullet strings; include all material facts, no omissions)",
        "- critical_insights (array of short bullet strings; include key implications/risks/uncertainties)",
        "- why_it_matters (1-2 short sentences, decision-focused)",
        "- sentiment (bullish|bearish|neutral|mixed)",
        "Rules:",
        "- keep writing concise and easy to read",
        "- do not omit critical facts or key insights just to stay short",
        "- prioritize most material facts/insights first",
        "- if full content is unavailable, state uncertainty briefly and rely on available evidence",
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
