from __future__ import annotations

from typing import Any, Dict, List


def _build_output_language_line(output_language: str) -> str:
    normalized = str(output_language or "").strip().lower()
    if normalized in {"zh", "zh-cn", "zh_hans", "chinese", "simplified chinese"}:
        return "- Output should be written in Simplified Chinese.\n"
    return ""


def _build_company_story_context(existing_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "story_key": item.get("story_key"),
            "story_title": item.get("story_title"),
            "story_summary": item.get("story_summary") or "",
            "story_status": item.get("story_status") or "ongoing",
            "importance_rank": item.get("importance_rank") or 999,
            "priority": item.get("priority") or "normal",
        }
        for item in existing_stories
        if isinstance(item, dict)
    ]
