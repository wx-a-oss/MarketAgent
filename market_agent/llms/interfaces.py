"""Provider interface definitions for LLM providers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol


class AnalysisProvider(Protocol):
    name: str

    def analyze_section(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single section payload and return a structured response."""


class NewsProvider(Protocol):
    name: str

    def generate_text(
        self,
        *,
        prompt: str,
    ) -> str:
        """Generate free-form text output for a prompt."""

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
        output_language: str = "en",
    ) -> Dict[str, Any]:
        """Return a weekly report object with required sections."""

    def analyze_news_items(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
        items: Iterable[Dict[str, Any]],
        analysis_prompt: str = "simple",
    ) -> List[Dict[str, Any]]:
        """Analyze raw news items and return enriched items."""

    def filter_news_items(
        self,
        *,
        company_name: str,
        items: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return relevance decisions for items (keep/drop + reason)."""
