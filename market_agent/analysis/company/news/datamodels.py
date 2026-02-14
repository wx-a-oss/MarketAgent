"""Datamodels for company news."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class NewsArticle:
    company_name: str
    news_date_time: datetime
    news_title: str
    original_content: Optional[str]
    llm_analyzed_content: Optional[str] = None
    news_source_link: Optional[str] = None
    news_source: Optional[str] = None
    id: Optional[int] = None
    is_analyzed: bool = False
    is_filtered: bool = False
