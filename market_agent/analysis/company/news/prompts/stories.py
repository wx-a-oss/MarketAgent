from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

from .common import _build_company_story_context, _build_output_language_line


def _build_company_story_warmup_prompt(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    output_language: str,
    items: List[Dict[str, Any]],
) -> str:
    language_line = _build_output_language_line(output_language)
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        f"You are building a {company_name} story map from company news between {start_date.isoformat()} and {end_date.isoformat()}.\n"
        "Find all material storylines for this company.\n"
        "Do not miss important storylines.\n"
        "Merge duplicate or overlapping coverage.\n"
        "Separate ongoing stories from finished stories.\n"
        "Use the timeline across all news to connect related events into storylines.\n"
        "Mark a story as finished only if the main event is resolved or no longer actively developing.\n"
        "Rules:\n"
        "- Focus on company-specific and investor-relevant developments.\n"
        "- Past and Now must be bullet points.\n"
        "- Next must be bullet points, and each bullet must include expected scenario, impact, probability/confidence, and sentiment.\n"
        "- Keep evidence references so we know which news supports each storyline.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "ongoing_stories": [\n'
        "    {\n"
        '      "story_key": "stable_key",\n'
        '      "story_title": "short title",\n'
        '      "importance_rank": 1,\n'
        '      "past": ["..."],\n'
        '      "now": ["..."],\n'
        '      "next": ["Scenario: ... | Impact: ... | Probability: ... | Sentiment: ..."],\n'
        '      "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}]\n'
        "    }\n"
        "  ],\n"
        '  "finished_stories": [\n'
        "    {\n"
        '      "story_key": "stable_key",\n'
        '      "story_title": "short title",\n'
        '      "importance_rank": 1,\n'
        '      "past": ["..."],\n'
        '      "now": ["Final state / resolution ..."],\n'
        '      "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"News corpus JSON:\n{items_json}\n"
    )


def _build_company_story_warmup_consolidation_prompt(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    output_language: str,
    chunk_results: List[Dict[str, Any]],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(chunk_results, ensure_ascii=False, indent=2)
    return (
        f"Merge chunk-level story drafts for {company_name} between {start_date.isoformat()} and {end_date.isoformat()}.\n"
        "Goal:\n"
        "- Merge duplicate or overlapping stories.\n"
        "- Keep all material company storylines.\n"
        "- Separate ongoing stories from finished stories.\n"
        "- Preserve timeline continuity.\n"
        "- Return JSON only with keys ongoing_stories and finished_stories.\n"
        f"{language_line}"
        f"Chunk story drafts JSON:\n{payload_json}\n"
    )


def _build_company_story_update_prompt(
    company_name: str,
    *,
    as_of_date: date,
    prompt_style: str,
    output_language: str,
    existing_stories: List[Dict[str, Any]],
    status_input: Dict[str, Any],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload = {
        "existing_stories": existing_stories,
        "new_evidence": status_input,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    normalized_prompt = str(prompt_style or "simple").strip().lower()
    if normalized_prompt == "structured":
        return (
            f"You maintain a rolling story map for {company_name} as of {as_of_date.isoformat()}.\n"
            "Update the existing stories with new evidence.\n"
            "Rules:\n"
            "- Keep story continuity across time; move points between happened/happening/next when state changes.\n"
            "- Merge duplicate or near-duplicate stories.\n"
            "- Preserve material company-related developments.\n"
            "- Rank stories by importance.\n"
            "- Return JSON only.\n"
            f"{language_line}"
            "Output JSON schema:\n"
            "{\n"
            '  "stories": [\n'
            "    {\n"
            '      "story_key": "stable_slug_key",\n'
            '      "story_title": "short title",\n'
            '      "importance_rank": 1,\n'
            '      "story_status": "rising|stable|fading|resolved",\n'
            '      "confidence": 0.0,\n'
            '      "happened_text": "what happened",\n'
            '      "happening_text": "what is happening now",\n'
            '      "next_text": "what may happen next",\n'
            '      "open_questions": ["..."],\n'
            '      "evidence": ["..."],\n'
            '      "change_log": ["..."]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            f"Inputs JSON:\n{payload_json}\n"
        )
    return (
        f"Update the company stories for {company_name} as of {as_of_date.isoformat()}.\n"
        "Use existing stories + new evidence to update story progression.\n"
        "Rules:\n"
        "- Keep continuity over time.\n"
        "- If a predicted item is now happening or happened, move it to the right section.\n"
        "- Ignore duplicates.\n"
        "- Rank stories by importance.\n"
        "- Return JSON only with key `stories`.\n"
        f"{language_line}"
        "Each story object fields:\n"
        "story_key, story_title, importance_rank, story_status, confidence, happened_text, happening_text, next_text, open_questions, evidence, change_log.\n"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _build_company_daily_cluster_prompt(
    company_name: str,
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    output_language: str,
    cluster_min: int = 3,
    cluster_max: int = 8,
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Cluster the company news for {company_name} on {target_date.isoformat()} into a small set of distinct daily company narratives.\n"
        "Goal:\n"
        f"- Produce {cluster_min} to {cluster_max} meaningful clusters when possible.\n"
        "- Group duplicate or overlapping coverage into one cluster.\n"
        "- Each cluster should have a short title and a compact summary.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "clusters": [\n'
        "    {\n"
        '      "cluster_key": "short-stable-key",\n'
        '      "cluster_title": "short title",\n'
        '      "cluster_summary": "one compact summary paragraph",\n'
        '      "source_news": [{"news_id": 123, "headline": "...", "url": "...", "datetime_text": "..."}]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"News items JSON:\n{items_json}\n"
    )


def _build_company_story_warmup_cluster_prompt(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    output_language: str,
    items: List[Dict[str, Any]],
) -> str:
    language_line = _build_output_language_line(output_language)
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        f"You are building the initial company story map for {company_name} from daily clusters between {start_date.isoformat()} and {end_date.isoformat()}.\n"
        "Find the distinct company storylines across the period.\n"
        "Each story must include a title, a compact summary, an ordered timeline_items list, and a future_and_impact list.\n"
        "Timeline items should reflect meaningful developments in chronological order.\n"
        "Future and impact items should describe plausible forward scenarios with probability and impact.\n"
        "Return JSON only as an object with key stories.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "stories": [\n'
        "    {\n"
        '      "story_key": "stable-key",\n'
        '      "story_title": "short title",\n'
        '      "story_summary": "compact summary",\n'
        '      "importance_rank": 1,\n'
        '      "story_status": "ongoing|finished|resolved|closed",\n'
        '      "priority": "normal|high",\n'
        '      "timeline_items": [{"date": "2026-03-10", "label": "event", "summary": "..."}],\n'
        '      "future_and_impact": [{"scenario": "...", "probability": "low|medium|high", "impact": "..."}],\n'
        '      "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '      "change_log": ["..."]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Daily company clusters JSON:\n{items_json}\n"
    )


def _build_company_story_routing_prompt(
    company_name: str,
    *,
    as_of_date: date,
    prompt_style: str,
    output_language: str,
    existing_stories: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
) -> str:
    del prompt_style
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {
            "existing_stories": _build_company_story_context(existing_stories),
            "daily_clusters": clusters,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"You are routing daily company clusters into the live story map for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal:\n"
        "- Assign each cluster to exactly one outcome.\n"
        "- Prefer an existing story if the cluster clearly belongs there.\n"
        "- Create a new story only if the cluster introduces a distinct new storyline.\n"
        "- Ignore only if the cluster is duplicate or not materially useful.\n"
        "Rules:\n"
        "- One cluster can belong to only one story bucket.\n"
        "- Do not assign the same cluster to multiple stories.\n"
        "- Use story title, story summary, and priority as the routing context.\n"
        "- If the match is ambiguous, choose the best-fit story and keep story boundaries clean.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "cluster_key": "cluster-key",\n'
        '      "action": "existing_story|new_story|ignore",\n'
        '      "story_key": "existing_story_key",\n'
        '      "new_story_title": "title only when action=new_story",\n'
        '      "reason": "not_related|duplicate|best_fit note"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _build_incremental_existing_story_prompt(
    company_name: str,
    *,
    as_of_date: date,
    output_language: str,
    story: Dict[str, Any],
    clusters: List[Dict[str, Any]],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {
            "existing_story": _build_company_story_context([story])[0],
            "daily_clusters": clusters,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"Update one existing company story for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal:\n"
        "- Use the assigned daily clusters to update this single story only.\n"
        "- Preserve continuity and keep the same story_key.\n"
        "- Update story_summary, timeline_items, and future_and_impact.\n"
        "- Timeline items must be ordered chronologically.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "story": {\n'
        '    "story_key": "same_existing_key",\n'
        '    "story_title": "short title",\n'
        '    "importance_rank": 1,\n'
        '    "story_status": "ongoing|stable|rising|fading|resolved|finished|closed",\n'
        '    "priority": "normal|high",\n'
        '    "story_summary": "compact summary",\n'
        '    "timeline_items": [{"date": "2026-03-10", "label": "event", "summary": "..."}],\n'
        '    "future_and_impact": [{"scenario": "...", "probability": "low|medium|high", "impact": "..."}],\n'
        '    "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '    "change_log": ["..."]\n'
        "  }\n"
        "}\n"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _build_incremental_new_story_prompt(
    company_name: str,
    *,
    as_of_date: date,
    output_language: str,
    story_key: str,
    story_title: str,
    clusters: List[Dict[str, Any]],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {
            "new_story_key": story_key,
            "new_story_title": story_title,
            "daily_clusters": clusters,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"Create one new company story for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal:\n"
        "- Build exactly one distinct new story from the assigned daily clusters.\n"
        "- Provide a compact summary, timeline_items, and future_and_impact.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "story": {\n'
        '    "story_key": "provided_key",\n'
        '    "story_title": "short title",\n'
        '    "importance_rank": 1,\n'
        '    "story_status": "ongoing|stable|rising|fading|resolved|finished|closed",\n'
        '    "priority": "normal|high",\n'
        '    "story_summary": "compact summary",\n'
        '    "timeline_items": [{"date": "2026-03-10", "label": "event", "summary": "..."}],\n'
        '    "future_and_impact": [{"scenario": "...", "probability": "low|medium|high", "impact": "..."}],\n'
        '    "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '    "change_log": ["..."]\n'
        "  }\n"
        "}\n"
        f"Inputs JSON:\n{payload_json}\n"
    )
