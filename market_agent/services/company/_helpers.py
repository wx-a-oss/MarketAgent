"""Private helper/utility functions shared across company service sub-modules."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.db.bootstrap import ensure_database_schema
from market_agent.services.company.prompts import _build_output_language_line  # noqa: F401 (re-export)

logger = logging.getLogger("uvicorn.error")


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_company_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    if not normalized:
        return ""
    return normalized[:1].upper() + normalized[1:]


def _normalize_ticker(ticker: Optional[str]) -> Optional[str]:
    if ticker is None:
        return None
    normalized = str(ticker).strip().upper()
    return normalized or None


def _normalize_note_tag(tag: Optional[str]) -> str:
    normalized = str(tag or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:80]


def _normalize_note_tags(tags: Optional[Iterable[str]]) -> List[Dict[str, str]]:
    values: List[str] = []
    if tags is None:
        values = []
    elif isinstance(tags, str):
        raw = re.split(r"[,#\n]+", tags)
        values = [part.strip() for part in raw if str(part or "").strip()]
    else:
        values = [str(part or "").strip() for part in tags if str(part or "").strip()]
    dedup: Dict[str, str] = {}
    for value in values:
        clean = re.sub(r"\s+", " ", value).strip()
        normalized = _normalize_note_tag(clean)
        if not clean or not normalized:
            continue
        dedup.setdefault(normalized, clean[:80])
    return [
        {"tag_text": display, "normalized_tag": normalized}
        for normalized, display in dedup.items()
    ]


def _replace_user_note_tags(cur: Any, *, note_id: int, tag_rows: List[Dict[str, str]]) -> None:
    cur.execute("DELETE FROM user_note_tag WHERE note_id = %s", (int(note_id),))
    for row in tag_rows:
        cur.execute(
            """
            INSERT INTO user_note_tag (note_id, tag_text, normalized_tag)
            VALUES (%s, %s, %s)
            ON CONFLICT (note_id, normalized_tag) DO UPDATE
            SET tag_text = EXCLUDED.tag_text
            """,
            (int(note_id), row["tag_text"], row["normalized_tag"]),
        )


def _normalize_story_key(value: Any, *, fallback_title: str = "", fallback_index: int = 0) -> str:
    text = str(value or "").strip().lower()
    if not text:
        text = str(fallback_title or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = f"story-{fallback_index + 1}"
    return text[:80]


def _normalize_story_record(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = _as_text(item.get("story_title") or item.get("title"))
    if not title:
        return None
    rank_raw = item.get("importance_rank")
    try:
        rank = int(rank_raw)
    except (TypeError, ValueError):
        rank = 999
    confidence_raw = item.get("confidence")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(confidence, 1.0))
    story_key = _normalize_story_key(item.get("story_key"), fallback_title=title, fallback_index=rank)
    timeline_items = item.get("timeline_items") if isinstance(item.get("timeline_items"), list) else []
    future_and_impact = item.get("future_and_impact") if isinstance(item.get("future_and_impact"), list) else []
    story_summary = _as_text(item.get("story_summary")) or ""
    happened_text = _as_text(item.get("happened_text")) or ""
    happening_text = _as_text(item.get("happening_text")) or ""
    next_text = _as_text(item.get("next_text")) or ""
    if not story_summary:
        story_summary = happening_text or happened_text or next_text
    if not timeline_items:
        timeline_items = _story_timeline_from_legacy_fields(
            happened_text=happened_text,
            happening_text=happening_text,
        )
    if not future_and_impact and next_text:
        future_and_impact = [{"scenario": next_text, "probability": "", "impact": ""}]
    priority = _as_text(item.get("priority")) or "normal"
    return {
        "story_key": story_key,
        "story_title": title,
        "story_summary": story_summary,
        "importance_rank": max(1, rank),
        "story_status": _as_text(item.get("story_status")) or "stable",
        "priority": priority,
        "confidence": confidence,
        "happened_text": happened_text,
        "happening_text": happening_text,
        "next_text": next_text,
        "timeline_items": [entry for entry in timeline_items if isinstance(entry, dict)],
        "future_and_impact": [entry for entry in future_and_impact if isinstance(entry, dict)],
        "open_questions": item.get("open_questions") if isinstance(item.get("open_questions"), list) else [],
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "change_log": item.get("change_log") if isinstance(item.get("change_log"), list) else [],
    }


def _story_timeline_from_legacy_fields(*, happened_text: str, happening_text: str) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for label, text in (("Past", happened_text), ("Now", happening_text)):
        cleaned = str(text or "").strip()
        if not cleaned:
            continue
        timeline.append({"date": "", "label": label, "summary": cleaned})
    return timeline


def _row_to_story_state(row: Dict[str, Any]) -> Dict[str, Any]:
    from market_agent.schema_fields import COL_OUTPUT_LANGUAGE, COL_STORY_KEY

    def _safe_json_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return []
        return []

    return {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "story_key": row[COL_STORY_KEY],
        "story_title": row["story_title"] or "",
        "story_summary": row.get("story_summary") or "",
        "importance_rank": int(row["importance_rank"] or 999),
        "story_status": row["story_status"] or "stable",
        "priority": row.get("priority") or "normal",
        "confidence": float(row["confidence"] or 0.5),
        "happened_text": row["happened_text"] or "",
        "happening_text": row["happening_text"] or "",
        "next_text": row["next_text"] or "",
        "timeline_items": _safe_json_list(row.get("timeline_json")),
        "future_and_impact": _safe_json_list(row.get("future_impact_json")),
        "open_questions": _safe_json_list(row["open_questions_json"]),
        "evidence": _safe_json_list(row["evidence_json"]),
        "change_log": _safe_json_list(row["change_log_json"]),
        "last_event_at": row["last_event_at"].strftime("%Y-%m-%d %H:%M:%S") if row["last_event_at"] else "",
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "is_active": bool(row["is_active"]),
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _row_to_story_warmup_state(row: Dict[str, Any]) -> Dict[str, Any]:
    from market_agent.schema_fields import COL_OUTPUT_LANGUAGE
    from market_agent.services.company._constants import (
        DEFAULT_STORY_WARMUP_DAYS,
        DEFAULT_STORY_WARMUP_SLICE_DAYS,
    )

    started_at = row.get("started_at")
    completed_at = row.get("completed_at")
    updated_at = row.get("updated_at")
    current_time = completed_at or updated_at or started_at
    elapsed_sec = 0.0
    if started_at and current_time:
        elapsed_sec = max(
            0.0,
            round((current_time - started_at).total_seconds(), 2),
        )
    return {
        "company_name": row["company_name"],
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "job_state": row["job_state"] or "not_started",
        "current_stage": row["current_stage"] or "idle",
        "window_days": int(row.get("window_days") or DEFAULT_STORY_WARMUP_DAYS),
        "slice_days": int(row.get("slice_days") or DEFAULT_STORY_WARMUP_SLICE_DAYS),
        "window_start_date": row["window_start_date"].isoformat() if row.get("window_start_date") else "",
        "window_end_date": row["window_end_date"].isoformat() if row.get("window_end_date") else "",
        "total_slices": int(row.get("total_slices") or 0),
        "completed_slices": int(row.get("completed_slices") or 0),
        "current_slice_start_date": row["current_slice_start_date"].isoformat() if row.get("current_slice_start_date") else "",
        "current_slice_end_date": row["current_slice_end_date"].isoformat() if row.get("current_slice_end_date") else "",
        "last_completed_slice_end_date": row["last_completed_slice_end_date"].isoformat() if row.get("last_completed_slice_end_date") else "",
        "analysis_started": bool(row.get("analysis_started")),
        "analysis_completed": bool(row.get("analysis_completed")),
        "raw_fetched_count": int(row.get("raw_fetched_count") or 0),
        "raw_stored_count": int(row.get("raw_stored_count") or 0),
        "filtered_kept_count": int(row.get("filtered_kept_count") or 0),
        "ongoing_story_count": int(row.get("ongoing_story_count") or 0),
        "finished_story_count": int(row.get("finished_story_count") or 0),
        "retry_count": int(row.get("retry_count") or 0),
        "last_retry_at": row["last_retry_at"].strftime("%Y-%m-%d %H:%M:%S") if row.get("last_retry_at") else "",
        "last_error": row.get("last_error") or "",
        "failed_stage": row.get("failed_stage") or "",
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S") if started_at else "",
        "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S") if updated_at else "",
        "completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S") if completed_at else "",
        "elapsed_sec": elapsed_sec,
    }


def _parse_story_warmup_state_datetime(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    text = str(raw_value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _group_story_states(
    stories: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    ongoing: List[Dict[str, Any]] = []
    finished: List[Dict[str, Any]] = []
    for story in stories:
        status = str(story.get("story_status") or "").strip().lower()
        if status in {"resolved", "finished", "closed"}:
            finished.append(story)
        else:
            ongoing.append(story)
    return {
        "ongoing_stories": ongoing,
        "finished_stories": finished,
    }


def _format_story_section_bullets(items: List[Any]) -> str:
    cleaned: List[str] = []
    for item in items:
        text = _as_text(item)
        if text:
            cleaned.append(text)
    if not cleaned:
        return ""
    return "\n".join(f"- {item}" for item in cleaned)


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_iso_date(value: Any) -> Optional[date]:
    text = _as_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _decode_llm_content(
    llm_content: Optional[str],
    original_content: Optional[str],
) -> Dict[str, Any]:
    if llm_content:
        try:
            payload = json.loads(llm_content)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {"summary": original_content or ""}


def _parse_date_time(raw: Any, *, end_date: date) -> datetime:
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc)
    if isinstance(raw, date):
        return datetime.combine(raw, time(12, 0), tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        try:
            timestamp = float(raw)
            # Finnhub commonly returns epoch seconds; guard for epoch milliseconds too.
            if timestamp > 1_000_000_000_000:
                timestamp = timestamp / 1000.0
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(raw, str):
        raw = raw.strip()
        try:
            if "T" in raw:
                parsed = datetime.fromisoformat(raw)
            else:
                parsed = datetime.fromisoformat(f"{raw}T12:00:00")
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.combine(end_date, time(12, 0), tzinfo=timezone.utc)


def _is_item_relevant(item: Dict[str, Any]) -> bool:
    for key in ("keep_for_company", "is_relevant", "keep"):
        if key not in item:
            continue
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        lowered = str(value).strip().lower()
        if lowered in {"true", "1", "yes", "y", "keep", "relevant"}:
            return True
        if lowered in {"false", "0", "no", "n", "drop", "irrelevant"}:
            return False
    signal = str(item.get("filter_signal") or item.get("relevance_signal") or "").strip().lower()
    if signal in {"drop", "irrelevant"}:
        return False
    if signal in {"keep", "relevant"}:
        return True
    return True


def _tag_source(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    for item in items:
        item["news_source"] = source
    return items


def _extract_analyzed_content(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata_keys = {
        "id",
        "company_name",
        "news_date_time",
        "news_title",
        "original_content",
        "news_source",
        "news_source_link",
        "source",
        "source_link",
        "publisher",
        "is_analyzed",
        "is_filtered",
        "keep_for_company",
    }
    content: Dict[str, Any] = {}
    for key, value in item.items():
        if key in metadata_keys:
            continue
        content[key] = value
    return content


def _extract_drop_reason(item: Dict[str, Any]) -> Optional[str]:
    for key in ("drop_reason", "reason", "filter_reason"):
        value = _as_text(item.get(key))
        if value:
            return value
    return None


def _days(count: int) -> timedelta:
    return timedelta(days=count)


def _ensure_news_schema() -> None:
    ensure_database_schema()


def _resolve_symbol_from_lookup(
    payload: Dict[str, Any],
    company_name: str,
) -> Optional[str]:
    results = payload.get("result") or []
    if not results:
        return None
    target = company_name.lower()
    exact = next(
        (
            item
            for item in results
            if str(item.get("symbol", "")).lower() == target
            or str(item.get("displaySymbol", "")).lower() == target
        ),
        None,
    )
    if exact:
        return exact.get("symbol") or exact.get("displaySymbol")
    return results[0].get("symbol") or results[0].get("displaySymbol")
