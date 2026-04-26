"""Structured analysis schema and requirements for news prompts."""

from __future__ import annotations

from typing import List

ANALYSIS_FIELDS: List[tuple[str, str]] = [
    ("summary", "A concise summary of the article"),
    ("facts", "Objective facts in the news"),
    ("viewpoint", "The viewpoints presented in the article"),
    (
        "reasoning",
        "Insights about the facts and viewpoints, and the reasoning behind it",
    ),
    (
        "uncertainties",
        "What uncertainties the article points out or implies that require future validation or materialization",
    ),
    ("short_term_impact", "Expected short-term impact"),
    ("long_term_impact", "Expected long-term impact"),
    ("priced_in", "How much may already be priced in"),
    ("insider_signals", "Potential insider signals or implications"),
    ("trends", "Possible future trends for the stock"),
    ("sentiment", "Overall bullish/bearish/neutral sentiment"),
]

_ANALYSIS_COMMON_REQUIREMENTS: List[str] = [
    "- dedupe repeated or near-duplicate items",
    "- prioritize quality, relevance, and decision usefulness over quantity",
]

_ANALYSIS_FETCH_ONLY_REQUIREMENTS: List[str] = [
    "- run enough web searches to cover this range comprehensively",
    "- do not stop at one headline; return all materially relevant items you can find",
    "- if many relevant items exist, include as many as possible and dedupe near-duplicates",
]

_ANALYSIS_INPUT_ONLY_REQUIREMENTS: List[str] = [
    "- input items may contain limited metadata only (headline/title, datetime, source link, brief summary)",
    "- do not assume the input includes full article content",
    "- for each item, try to open the source link to obtain fuller article content/context",
    "- if the source link is inaccessible or incomplete, use online search to recover the article's key details",
    "- if full content still cannot be obtained, analyze conservatively using available evidence",
]


def analysis_field_lines() -> List[str]:
    lines = [
        "Return ONLY valid JSON as a JSON array of objects.",
        "Each object must include:",
        "news_date_time (ISO 8601 date or datetime)",
        "news_title",
        "news_source",
        "news_source_link",
        "Also include:",
    ]
    for field, description in ANALYSIS_FIELDS:
        lines.append(f"{field} ({description})")
    return lines


def analysis_requirements_lines(*, with_input_items: bool) -> List[str]:
    mode_specific = (
        _ANALYSIS_INPUT_ONLY_REQUIREMENTS
        if with_input_items
        else _ANALYSIS_FETCH_ONLY_REQUIREMENTS
    )
    return ["Requirements:", *mode_specific, *_ANALYSIS_COMMON_REQUIREMENTS]
