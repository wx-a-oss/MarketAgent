"""Prompt builder for analyzing pre-fetched company news."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from .common import dump_items_json, lines_to_prompt
from .news_analysis_simple import build_news_analysis_prompt_metadata_summary
from .news_analysis_structured import analysis_field_lines, analysis_requirements_lines


# Default analysis prompt for pre-fetched items (structured format).
def build_news_analysis_prompt_structured(
    company_name: str,
    start_date: str,
    end_date: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    lines = [
        f"Analyze the provided financial news items for {company_name}.",
    ]
    lines.extend(analysis_field_lines())
    lines.extend(analysis_requirements_lines(with_input_items=True))
    lines.append("Input items JSON:")
    lines.append(dump_items_json(items))
    return lines_to_prompt(lines)


# Lightweight alternative using metadata-focused simple summaries.
def build_news_analysis_prompt_simple(
    company_name: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    return build_news_analysis_prompt_metadata_summary(company_name, items)


# Backward-compatible aliases.
def build_input_news_analysis_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    return build_news_analysis_prompt_structured(
        company_name,
        start_date,
        end_date,
        items,
    )


def build_input_news_simple_summary_prompt(
    company_name: str,
    items: Iterable[Dict[str, Any]],
) -> str:
    return build_news_analysis_prompt_simple(company_name, items)
