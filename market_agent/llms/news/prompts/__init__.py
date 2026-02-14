"""Prompt builders for news flows."""

from .analyze_news import (
    build_news_analysis_prompt_simple,
    build_news_analysis_prompt_structured,
    build_input_news_analysis_prompt,
    build_input_news_simple_summary_prompt,
)
from .fetch_news import build_fetch_news_analysis_prompt
from .filter_news import build_news_filter_prompt
from .news_analysis_simple import build_news_analysis_prompt_metadata_summary
from .weekly_report import build_weekly_report_prompt

__all__ = [
    "build_fetch_news_analysis_prompt",
    "build_news_analysis_prompt_structured",
    "build_news_analysis_prompt_simple",
    "build_news_analysis_prompt_metadata_summary",
    "build_input_news_analysis_prompt",
    "build_input_news_simple_summary_prompt",
    "build_news_filter_prompt",
    "build_weekly_report_prompt",
]
