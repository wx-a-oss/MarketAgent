"""Finnhub news source provider."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from market_agent.datasources.finnhub.finnhub_client import FinnhubClient
from market_agent.datasources.finnhub.news_interfaces import NewsSourceProvider


@dataclass(slots=True)
class FinnhubNewsSource(NewsSourceProvider):
    api_key: str
    name: str = "finnhub"

    def fetch_news(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        logger = logging.getLogger("uvicorn.error")
        client = FinnhubClient(self.api_key)
        logger.info(
            "FinnhubNewsSource.fetch_news: symbol=%s range=%s..%s",
            company_name,
            start_date,
            end_date,
        )
        items = client.company_news(company_name, start_date, end_date)
        logger.info("FinnhubNewsSource.fetch_news: returned %d items", len(items))
        return [
            {
                "news_date_time": item.get("datetime"),
                "news_title": item.get("headline"),
                "original_content": item.get("summary"),
                "news_source_link": item.get("url"),
                "news_source": self.name,
                "publisher": item.get("source"),
            }
            for item in items
        ]


def resolve_finnhub_news_source(api_key: str | None = None) -> FinnhubNewsSource:
    resolved = api_key or os.getenv("FINNHUB_API_KEY")
    if not resolved:
        raise RuntimeError("FINNHUB_API_KEY is required for Finnhub news.")
    return FinnhubNewsSource(api_key=resolved)


__all__ = ["FinnhubNewsSource", "resolve_finnhub_news_source"]
