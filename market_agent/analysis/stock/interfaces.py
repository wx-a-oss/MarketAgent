"""Provider interface definitions for analysis."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class AnalysisProvider(Protocol):
    name: str

    def analyze_section(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single section payload and return a structured response."""
