"""Interfaces for news-capable LLM providers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol


class NewsProvider(Protocol):
    name: str

    def fetch_news(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Return a list of news items as dictionaries."""

    def fetch_weekly_report(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
        articles: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a weekly report object with required sections."""
