"""Prompt builder for fetching and analyzing company news."""

from __future__ import annotations

from .common import lines_to_prompt
from .news_analysis_structured import analysis_field_lines, analysis_requirements_lines


# Default fetch-and-analyze prompt (structured format).
def build_fetch_news_analysis_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
) -> str:
    lines = [
        f"Retrieve and analyze financial news for {company_name} from {start_date} to {end_date}.",
    ]
    lines.extend(analysis_field_lines())
    lines.extend(analysis_requirements_lines(with_input_items=False))
    return lines_to_prompt(lines)
