"""Interfaces for news source providers."""

from __future__ import annotations

from typing import Any, Dict, List, Protocol


class NewsSourceProvider(Protocol):
    name: str

    def fetch_news(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Return raw news items with original content from a data source."""
