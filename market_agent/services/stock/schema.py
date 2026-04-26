"""Unified analysis result schema for UI rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class SectionAnalysis:
    summary: str
    highlights: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "highlights": self.highlights,
            "risks": self.risks,
            "questions": self.questions,
        }


def normalize_section_result(raw: Any) -> SectionAnalysis:
    if isinstance(raw, dict):
        summary = str(raw.get("summary") or "").strip() or "No summary provided."
        highlights = _ensure_list(raw.get("highlights"))
        risks = _ensure_list(raw.get("risks"))
        questions = _ensure_list(raw.get("questions"))
        return SectionAnalysis(
            summary=summary,
            highlights=highlights,
            risks=risks,
            questions=questions,
        )
    return SectionAnalysis(summary=str(raw))


def _ensure_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]
