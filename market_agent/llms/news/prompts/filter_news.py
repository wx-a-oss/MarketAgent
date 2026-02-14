"""Prompt builder for filtering irrelevant company news."""

from __future__ import annotations

from typing import Any, Iterable

from .common import dump_items_json


def build_news_filter_prompt(
    company_name: str,
    items: Iterable[Any],
) -> str:
    return (
        "You are filtering company news relevance.\n"
        "Input is a JSON array of unique news titles.\n"
        f"Keep true only if the title is materially related and informative for {company_name}.\n"
        "Return ONLY valid JSON as a boolean array in the SAME order as input titles.\n"
        "true means keep, false means drop.\n"
        "Titles JSON:\n"
        f"{dump_items_json(items)}\n"
    )
