"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
import os
import re
import logging
import math
import threading
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.config.models import DEFAULT_OPENAI_MODEL, DEFAULT_COMPANY_OPENAI_MODEL
from market_agent.llms.news import get_news_provider
from market_agent.analysis.company.news.db import ensure_database_schema, get_connection
from market_agent.analysis.company.news.datamodels import NewsArticle
from market_agent.analysis.company.ticker_fallbacks import resolve_company_ticker_fallback
from market_agent.datasources.finnhub import FinnhubClient
from market_agent.news_sources import get_news_source
from market_agent.analysis.company.news.prompts import (
    _build_company_daily_cluster_prompt,
    _build_company_daily_report_prompt,
    _build_company_price_intelligence_prompt,
    _build_company_quick_price_intelligence_prompt,
    _build_company_story_context,
    _build_company_story_qa_merge_prompt,
    _build_company_story_qa_prompt,
    _build_company_story_routing_prompt,
    _build_company_story_update_prompt,
    _build_company_story_warmup_cluster_prompt,
    _build_company_story_warmup_consolidation_prompt,
    _build_company_story_warmup_prompt,
    _build_incremental_existing_story_prompt,
    _build_incremental_new_story_prompt,
    _build_output_language_line,
)
from market_agent.llms.news.prompts.news_analysis_structured import ANALYSIS_FIELDS
from market_agent.schema_fields import (
    COL_OUTPUT_JSON,
    COL_OUTPUT_LANGUAGE,
    COL_PAYLOAD,
    COL_POINT_DATE_TIME,
    COL_RANGE_KEY,
    COL_SNAPSHOT_DATE,
    COL_STORY_KEY,
    TBL_COMPANY_NEWS_ANALYZED,
    TBL_COMPANY_NEWS_DAILY_CLUSTER,
    TBL_COMPANY_PRICE_INTELLIGENCE_RUN,
    TBL_COMPANY_PRICE_MOVE_ANALYSIS,
    TBL_COMPANY_STATUS_SNAPSHOT,
    TBL_COMPANY_STORY_QA,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
    TBL_COMPANY_STORY_WARMUP_STATE,
    TBL_MARKET_PRICE_DAILY_SNAPSHOT,
)

DEFAULT_MODEL = DEFAULT_COMPANY_OPENAI_MODEL
DEFAULT_PROVIDER = "openai"
DEFAULT_SOURCE = "openai"
FINNHUB_AUTO_ANALYZE_LIMIT = 10
ANALYZE_DAY_BATCH_SIZE = 3
FILTER_DAY_BATCH_SIZE = 10
DEFAULT_STORY_WARMUP_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_DAYS", "14").strip() or "14")
)
DEFAULT_STORY_WARMUP_SLICE_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_SLICE_DAYS", "1").strip() or "1")
)
DEFAULT_STORY_WARMUP_MAX_RETRIES = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_MAX_RETRIES", "3").strip() or "3")
)
DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_RETRY_DELAY_SEC", "60").strip() or "60")
)
DEFAULT_STORY_WARMUP_STALE_MINUTES = max(
    5, int(os.getenv("COMPANY_STORY_WARMUP_STALE_MINUTES", "180").strip() or "180")
)
STORY_WARMUP_PROMPT_JSON_LIMIT = max(
    12000, int(os.getenv("COMPANY_STORY_WARMUP_PROMPT_JSON_LIMIT", "45000").strip() or "45000")
)
STORY_WARMUP_CHUNK_SIZE = max(
    5, int(os.getenv("COMPANY_STORY_WARMUP_CHUNK_SIZE", "25").strip() or "25")
)
COMPANY_DAILY_CLUSTER_MIN = 3
COMPANY_DAILY_CLUSTER_MAX = 8
PRICE_ANALYSIS_REPORT_LIMIT = 30
PRICE_ANALYSIS_RAW_FALLBACK_LIMIT = 30
PRICE_ANALYSIS_MARKET_SUMMARY_LIMIT = 5

logger = logging.getLogger("uvicorn.error")
_WARMUP_THREADS: Dict[str, threading.Thread] = {}
_WARMUP_THREADS_LOCK = threading.Lock()


def list_watchlist_companies() -> List[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_name FROM company_watchlist ORDER BY added_at DESC"
            )
            return [row["company_name"] for row in cur.fetchall()]


def list_watchlist_company_rows() -> List[Dict[str, Optional[str]]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    w.company_name,
                    COALESCE(NULLIF(TRIM(w.llm_model), ''), %s) AS llm_model,
                    p.ticker
                FROM company_watchlist AS w
                LEFT JOIN LATERAL (
                    SELECT
                        COALESCE(
                            cp.ticker,
                            cp.properties_extension->>'symbol',
                            cp.properties_extension->>'ticker'
                        ) AS ticker
                    FROM company_profile AS cp
                    WHERE cp.company_name = w.company_name
                       OR LOWER(cp.company_name) = LOWER(w.company_name)
                    ORDER BY
                        CASE WHEN cp.company_name = w.company_name THEN 0 ELSE 1 END,
                        cp.fetched_at DESC
                    LIMIT 1
                ) AS p ON TRUE
                ORDER BY w.added_at DESC
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL,),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "company_name": row["company_name"],
                        "llm_model": str(row.get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL),
                        "ticker": _normalize_ticker(row.get("ticker")),
                    }
                )
            return rows


def list_company_chart_layout_rows() -> List[Dict[str, Optional[str]]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    w.company_name,
                    COALESCE(NULLIF(TRIM(w.llm_model), ''), %s) AS llm_model,
                    p.ticker,
                    l.position_index
                FROM company_watchlist AS w
                LEFT JOIN LATERAL (
                    SELECT
                        COALESCE(
                            cp.ticker,
                            cp.properties_extension->>'symbol',
                            cp.properties_extension->>'ticker'
                        ) AS ticker
                    FROM company_profile AS cp
                    WHERE cp.company_name = w.company_name
                       OR LOWER(cp.company_name) = LOWER(w.company_name)
                    ORDER BY
                        CASE WHEN cp.company_name = w.company_name THEN 0 ELSE 1 END,
                        cp.fetched_at DESC
                    LIMIT 1
                ) AS p ON TRUE
                LEFT JOIN company_chart_layout AS l
                    ON l.company_name = w.company_name
                ORDER BY
                    CASE WHEN l.position_index IS NULL THEN 1 ELSE 0 END,
                    l.position_index ASC,
                    w.added_at DESC
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL,),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "company_name": row["company_name"],
                        "llm_model": str(row.get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL),
                        "ticker": _normalize_ticker(row.get("ticker")),
                        "position_index": int(row["position_index"]) if row.get("position_index") is not None else None,
                    }
                )
            return rows


def save_company_chart_layout(company_names: Iterable[str]) -> List[str]:
    ensure_database_schema()
    normalized_names: List[str] = []
    seen: set[str] = set()
    for item in company_names:
        normalized = _normalize_company_name(item)
        if not normalized:
            continue
        if normalized in seen:
            raise ValueError(f"duplicate company_name in layout: {normalized}")
        seen.add(normalized)
        normalized_names.append(normalized)

    current_rows = list_watchlist_company_rows()
    current_names = [
        str(row.get("company_name") or "").strip()
        for row in current_rows
        if str(row.get("company_name") or "").strip()
    ]
    if set(normalized_names) != set(current_names) or len(normalized_names) != len(current_names):
        raise ValueError("layout must contain every subscribed company exactly once")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_chart_layout")
            if normalized_names:
                cur.executemany(
                    """
                    INSERT INTO company_chart_layout (company_name, position_index, updated_at)
                    VALUES (%s, %s, NOW())
                    """,
                    [(company_name, idx) for idx, company_name in enumerate(normalized_names)],
                )
        conn.commit()
    return normalized_names


def get_company_watchlist_model(company_name: str) -> str:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(llm_model), ''), %s) AS llm_model
                FROM company_watchlist
                WHERE company_name = %s
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL, normalized),
            )
            row = cur.fetchone()
    return str((row or {}).get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL)


def update_company_watchlist_model(company_name: str, model: Optional[str]) -> Dict[str, str]:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        raise ValueError("company_name is required")
    selected_model = str(model or "").strip() or DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_watchlist (company_name, llm_model)
                VALUES (%s, %s)
                ON CONFLICT (company_name)
                DO UPDATE SET llm_model = EXCLUDED.llm_model
                RETURNING company_name, llm_model
                """,
                (normalized, selected_model),
            )
            row = cur.fetchone()
        conn.commit()
    ensure_company_profile(normalized)
    return {
        "company_name": str(row["company_name"]),
        "llm_model": str(row["llm_model"] or DEFAULT_COMPANY_OPENAI_MODEL),
    }


def add_company_to_watchlist(company_name: str, *, model: Optional[str] = None) -> None:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return
    selected_model = str(model or "").strip() or DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_watchlist (company_name, llm_model)
                VALUES (%s, %s)
                ON CONFLICT (company_name)
                DO UPDATE SET llm_model = EXCLUDED.llm_model
                """,
                (normalized, selected_model),
            )
        conn.commit()
    ensure_company_profile(normalized)


def remove_company_from_watchlist(company_name: str) -> None:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM company_watchlist WHERE company_name = %s",
                (normalized,),
            )
        conn.commit()


def create_user_note(
    *,
    title: str,
    body_markdown: str,
    tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    _ensure_news_schema()
    clean_title = str(title or "").strip()
    clean_body = str(body_markdown or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    if not clean_body:
        raise ValueError("body is required")
    tag_rows = _normalize_note_tags(tags)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_note (
                    title,
                    body_markdown,
                    validity_state,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, 'valid', NOW(), NOW())
                RETURNING id
                """,
                (clean_title, clean_body),
            )
            row = cur.fetchone()
            note_id = int(row["id"])
            _replace_user_note_tags(cur, note_id=note_id, tag_rows=tag_rows)
        conn.commit()
    note = get_user_note(note_id)
    if not note:
        raise ValueError("failed to create note")
    return note


def update_user_note(
    note_id: int,
    *,
    title: str,
    body_markdown: str,
    tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    _ensure_news_schema()
    clean_title = str(title or "").strip()
    clean_body = str(body_markdown or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    if not clean_body:
        raise ValueError("body is required")
    tag_rows = _normalize_note_tags(tags)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_note
                SET title = %s,
                    body_markdown = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (clean_title, clean_body, int(note_id)),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("note not found")
            _replace_user_note_tags(cur, note_id=int(note_id), tag_rows=tag_rows)
        conn.commit()
    note = get_user_note(int(note_id))
    if not note:
        raise KeyError("note not found")
    return note


def invalidate_user_note(note_id: int, *, reason: Optional[str] = None) -> Dict[str, Any]:
    _ensure_news_schema()
    note = get_user_note(int(note_id))
    if not note:
        raise KeyError("note not found")
    if str(note.get("validity_state") or "valid") == "invalid":
        return note
    clean_reason = str(reason or "").strip() or None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_note
                SET validity_state = 'invalid',
                    invalidation_reason = %s,
                    invalidated_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (clean_reason, int(note_id)),
            )
        conn.commit()
    updated = get_user_note(int(note_id))
    if not updated:
        raise KeyError("note not found")
    return updated


def get_user_note(note_id: int) -> Optional[Dict[str, Any]]:
    notes = list_user_notes(note_id=int(note_id))
    return notes[0] if notes else None


def list_user_notes(*, tag: Optional[str] = None, note_id: Optional[int] = None) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    params: List[Any] = []
    where = []
    join = ""
    if note_id is not None:
        where.append("n.id = %s")
        params.append(int(note_id))
    normalized_tag = _normalize_note_tag(tag)
    if normalized_tag:
        join = "JOIN user_note_tag t_filter ON t_filter.note_id = n.id"
        where.append("t_filter.normalized_tag = %s")
        params.append(normalized_tag)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    n.id,
                    n.title,
                    n.body_markdown,
                    n.validity_state,
                    n.invalidation_reason,
                    n.invalidated_at,
                    n.created_at,
                    n.updated_at
                FROM user_note AS n
                {join}
                {where_sql}
                ORDER BY n.created_at DESC, n.id DESC
                """
                ,
                tuple(params),
            )
            note_rows = cur.fetchall()
            if not note_rows:
                return []
            note_ids = [int(row["id"]) for row in note_rows]
            cur.execute(
                """
                SELECT note_id, tag_text, normalized_tag
                FROM user_note_tag
                WHERE note_id = ANY(%s)
                ORDER BY normalized_tag ASC, id ASC
                """,
                (note_ids,),
            )
            tag_rows = cur.fetchall()
    tags_by_note: Dict[int, List[Dict[str, str]]] = {}
    for row in tag_rows:
        bucket = tags_by_note.setdefault(int(row["note_id"]), [])
        bucket.append(
            {
                "tag": str(row["tag_text"] or "").strip(),
                "normalized_tag": str(row["normalized_tag"] or "").strip(),
            }
        )
    result: List[Dict[str, Any]] = []
    for row in note_rows:
        note_tags = tags_by_note.get(int(row["id"]), [])
        result.append(
            {
                "id": int(row["id"]),
                "title": str(row["title"] or ""),
                "body_markdown": str(row["body_markdown"] or ""),
                "validity_state": str(row["validity_state"] or "valid"),
                "invalidation_reason": str(row["invalidation_reason"] or ""),
                "invalidated_at": row["invalidated_at"].isoformat() if row.get("invalidated_at") else "",
                "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
                "tags": [item["tag"] for item in note_tags],
                "normalized_tags": [item["normalized_tag"] for item in note_tags],
            }
        )
    return result


def list_user_note_tags() -> List[Dict[str, Any]]:
    _ensure_news_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    normalized_tag,
                    MIN(tag_text) AS display_tag,
                    COUNT(DISTINCT note_id) AS note_count
                FROM user_note_tag
                GROUP BY normalized_tag
                ORDER BY COUNT(DISTINCT note_id) DESC, MIN(tag_text) ASC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "tag": str(row["display_tag"] or ""),
            "normalized_tag": str(row["normalized_tag"] or ""),
            "note_count": int(row["note_count"] or 0),
        }
        for row in rows
    ]


def get_company_story_warmup_state(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    _ensure_news_schema()
    normalized = _normalize_company_name(company_name)
    default_payload = {
        "company_name": normalized,
        "provider": provider_name,
        "prompt_style": prompt_style,
        "output_language": output_language,
        "job_state": "not_started",
        "current_stage": "idle",
        "window_days": DEFAULT_STORY_WARMUP_DAYS,
        "slice_days": DEFAULT_STORY_WARMUP_SLICE_DAYS,
        "window_start_date": "",
        "window_end_date": "",
        "total_slices": 0,
        "completed_slices": 0,
        "current_slice_start_date": "",
        "current_slice_end_date": "",
        "last_completed_slice_end_date": "",
        "analysis_started": False,
        "analysis_completed": False,
        "raw_fetched_count": 0,
        "raw_stored_count": 0,
        "filtered_kept_count": 0,
        "ongoing_story_count": 0,
        "finished_story_count": 0,
        "retry_count": 0,
        "last_retry_at": "",
        "last_error": "",
        "failed_stage": "",
        "started_at": "",
        "updated_at": "",
        "completed_at": "",
        "elapsed_sec": 0.0,
    }
    if not normalized:
        return default_payload
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_COMPANY_STORY_WARMUP_STATE}
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                LIMIT 1
                """,
                (normalized, provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    if not row:
        return default_payload
    return _row_to_story_warmup_state(row)


def is_company_story_warmup_invalid(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    state = get_company_story_warmup_state(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    reason = _get_company_story_warmup_invalid_reason(company_name, state=state)
    return reason is not None


def _get_company_story_warmup_invalid_reason(
    company_name: str,
    *,
    state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    current_state = state or get_company_story_warmup_state(company_name)
    profile = get_company_profile(company_name)
    ticker = ""
    if profile:
        ticker = str(profile.get("ticker") or profile.get("symbol") or "").strip()
    if not ticker:
        return "No valid ticker available for company warm-up."
    job_state = str(current_state.get("job_state") or "").strip().lower()
    if job_state == "failed":
        failed_stage = str(current_state.get("failed_stage") or "").strip().lower()
        if failed_stage == "fetching_raw":
            return "Warm-up previously failed while fetching raw news."
        if int(current_state.get("raw_fetched_count") or 0) <= 0:
            return "Warm-up failed before collecting any raw news."
        if "ticker" in str(current_state.get("last_error") or "").lower():
            return "Warm-up failed because ticker resolution was invalid."
        return None
    if job_state in {"not_started", ""}:
        return "Warm-up has not started."
    if job_state == "completed" and int(current_state.get("raw_fetched_count") or 0) <= 0:
        return "Warm-up completed without collecting raw news."
    if bool(current_state.get("analysis_completed")) and job_state != "completed":
        return "Warm-up state is inconsistent: analysis completed but job is not completed."
    if job_state in {"running", "analyzing", "partial"}:
        heartbeat = _parse_story_warmup_state_datetime(
            current_state.get("updated_at") or current_state.get("started_at")
        )
        if not heartbeat:
            return "Warm-up state is missing heartbeat timestamps."
        stale_sec = DEFAULT_STORY_WARMUP_STALE_MINUTES * 60
        age_sec = max(0.0, (datetime.now(timezone.utc) - heartbeat).total_seconds())
        if age_sec >= stale_sec:
            return (
                "Warm-up state is stale: "
                f"no update for {round(age_sec / 60.0, 1)} minutes."
            )
    return None


def ensure_company_story_warmup_started(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = DEFAULT_STORY_WARMUP_DAYS,
    slice_days: int = DEFAULT_STORY_WARMUP_SLICE_DAYS,
) -> Dict[str, Any]:
    _ensure_news_schema()
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return get_company_story_warmup_state(
            company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
    state = get_company_story_warmup_state(
        normalized,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    invalid_reason = _get_company_story_warmup_invalid_reason(normalized, state=state)
    if state.get("job_state") == "completed" and invalid_reason is None:
        return state
    if invalid_reason and str(state.get("job_state") or "").strip().lower() in {"running", "analyzing", "partial"}:
        _upsert_story_warmup_state(
            normalized,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "failed",
                "current_stage": "idle",
                "window_days": max(1, int(state.get("window_days") or warmup_days)),
                "slice_days": max(1, int(state.get("slice_days") or slice_days)),
                "analysis_started": bool(state.get("analysis_started")),
                "analysis_completed": False,
                "raw_fetched_count": int(state.get("raw_fetched_count") or 0),
                "raw_stored_count": int(state.get("raw_stored_count") or 0),
                "filtered_kept_count": int(state.get("filtered_kept_count") or 0),
                "ongoing_story_count": int(state.get("ongoing_story_count") or 0),
                "finished_story_count": int(state.get("finished_story_count") or 0),
                "retry_count": int(state.get("retry_count") or 0),
                "last_error": invalid_reason,
                "failed_stage": str(state.get("current_stage") or "stale_state"),
                "completed_at": datetime.now(timezone.utc),
            },
        )
    _ensure_story_warmup_thread(
        normalized,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        warmup_days=warmup_days,
        slice_days=slice_days,
    )
    return get_company_story_warmup_state(
        normalized,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )


def rebuild_company_story_warmup(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = DEFAULT_STORY_WARMUP_DAYS,
    slice_days: int = DEFAULT_STORY_WARMUP_SLICE_DAYS,
) -> Dict[str, Any]:
    _ensure_news_schema()
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return get_company_story_warmup_state(
            company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TBL_COMPANY_STORY_STATE} WHERE company_name = %s", (normalized,))
            cur.execute(f"DELETE FROM {TBL_COMPANY_STORY_UPDATE} WHERE company_name = %s", (normalized,))
            cur.execute(
                f"""
                UPDATE {TBL_COMPANY_STORY_WARMUP_STATE}
                SET job_state = 'not_started',
                    current_stage = 'idle',
                    total_slices = 0,
                    completed_slices = 0,
                    current_slice_start_date = NULL,
                    current_slice_end_date = NULL,
                    last_completed_slice_end_date = NULL,
                    analysis_started = FALSE,
                    analysis_completed = FALSE,
                    raw_fetched_count = 0,
                    raw_stored_count = 0,
                    filtered_kept_count = 0,
                    ongoing_story_count = 0,
                    finished_story_count = 0,
                    retry_count = 0,
                    last_retry_at = NULL,
                    last_error = '',
                    failed_stage = '',
                    started_at = NULL,
                    completed_at = NULL,
                    updated_at = NOW()
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (normalized, provider_name, prompt_style, output_language),
            )
        conn.commit()
    return ensure_company_story_warmup_started(
        normalized,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        warmup_days=warmup_days,
        slice_days=slice_days,
    )


def get_company_news(
    company_name: str,
    *,
    llm_model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
) -> List[NewsArticle]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    r.id AS raw_id,
                    r.company_name,
                    r.news_date_time,
                    r.news_title,
                    r.content AS original_content,
                    a.content AS llm_analyzed_content,
                    a.{COL_OUTPUT_LANGUAGE} AS analyzed_output_language,
                    COALESCE(a.source_link, r.source_link) AS news_source_link,
                    COALESCE(a.source, r.source) AS news_source,
                    COALESCE(r.is_analyzed, FALSE) AS is_analyzed,
                    COALESCE(r.is_filtered, FALSE) AS is_filtered
                FROM company_news_raw AS r
                LEFT JOIN LATERAL (
                    SELECT
                        aa.content,
                        aa.{COL_OUTPUT_LANGUAGE},
                        aa.source_link,
                        aa.source
                    FROM {TBL_COMPANY_NEWS_ANALYZED} AS aa
                    WHERE aa.company_name = r.company_name
                      AND aa.news_title = r.news_title
                      AND aa.news_date_time = r.news_date_time
                    ORDER BY
                        CASE WHEN aa.{COL_OUTPUT_LANGUAGE} = %s THEN 0 ELSE 1 END,
                        CASE WHEN aa.llm_model = %s THEN 0 ELSE 1 END,
                        aa.id DESC
                    LIMIT 1
                ) AS a ON TRUE
                WHERE r.company_name = %s
                ORDER BY r.news_date_time DESC, r.id DESC
                """,
                (output_language, llm_model, company_name),
            )
            return [
                NewsArticle(
                    id=row["raw_id"],
                    company_name=row["company_name"],
                    news_date_time=row["news_date_time"],
                    news_title=row["news_title"],
                    original_content=row["original_content"],
                    llm_analyzed_content=row["llm_analyzed_content"],
                    news_source_link=row["news_source_link"],
                    news_source=row["news_source"],
                    is_analyzed=bool(row["is_analyzed"]),
                    is_filtered=bool(row["is_filtered"]),
                    analyzed_output_language=row.get("analyzed_output_language"),
                )
                for row in cur.fetchall()
            ]


def get_news_report(
    company_name: str, *, beginning_date: date, end_date: date
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content
                FROM news_report
                WHERE company_name = %s
                  AND beginning_date = %s
                  AND end_date = %s
                """,
                (company_name, beginning_date, end_date),
            )
            row = cur.fetchone()
            if not row:
                return None
            try:
                payload = json.loads(row["content"])
                return payload if isinstance(payload, dict) else {"summary": row["content"]}
            except json.JSONDecodeError:
                return {"summary": row["content"]}


def get_company_daily_report(
    company_name: str,
    *,
    report_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    provider,
                    model,
                    prompt_style,
                    input_payload,
                    output_text,
                    created_at
                FROM company_news_daily_report
                WHERE company_name = %s
                  AND report_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (company_name, report_date, provider_name, prompt_style),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "provider": row["provider"],
                "model": row["model"],
                "prompt_style": row["prompt_style"],
                "input_payload": row["input_payload"],
                "output_text": row["output_text"],
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            }


def get_company_daily_reports_for_range(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (report_date)
                    report_date,
                    provider,
                    model,
                    prompt_style,
                    input_payload,
                    output_text,
                    created_at
                FROM company_news_daily_report
                WHERE company_name = %s
                  AND report_date >= %s
                  AND report_date <= %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY report_date DESC, created_at DESC, id DESC
                """,
                (company_name, start_date, end_date, provider_name, prompt_style),
            )
            rows = cur.fetchall()
    return [
        {
            "report_date": row["report_date"].isoformat(),
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "input_payload": row["input_payload"],
            "output_text": row["output_text"],
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def get_company_status_snapshot(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    snapshot_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    params: List[Any] = [company_name, provider_name, prompt_style]
    where_extra = ""
    if snapshot_id is not None:
        where_extra = " AND id = %s"
        params.append(int(snapshot_id))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    as_of_date,
                    window_start_date,
                    window_end_date,
                    provider,
                    model,
                    prompt_style,
                    input_payload,
                    output_json,
                    output_text,
                    created_at
                FROM company_status_snapshot
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                  {where_extra}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        return None
    structured = _parse_json_object(row["output_json"] or "") or {}
    if not structured:
        structured = _normalize_company_status_payload(
            {"output_markdown": row["output_text"] or ""},
            as_of_date=row["as_of_date"],
        )
    snapshot = {
        "id": int(row["id"]),
        "as_of_date": row["as_of_date"].isoformat(),
        "window_start_date": row["window_start_date"].isoformat(),
        "window_end_date": row["window_end_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "input_payload": row["input_payload"],
        "output_json": row["output_json"],
        "output_text": row["output_text"],
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }
    snapshot.update(structured)
    return snapshot


def list_company_status_snapshots(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, as_of_date, provider, model, prompt_style, output_json, output_text, created_at
                FROM company_status_snapshot
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (company_name, provider_name, prompt_style, safe_limit),
            )
            rows = cur.fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        structured = _parse_json_object(row["output_json"] or "") or {}
        result.append(
            {
                "id": int(row["id"]),
                "as_of_date": row["as_of_date"].isoformat(),
                "provider": row["provider"],
                "model": row["model"],
                "prompt_style": row["prompt_style"],
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "price_position_summary": str(structured.get("price_position_summary") or ""),
                "technical_summary": str(structured.get("technical_summary") or structured.get("company_summary") or ""),
            }
        )
    return result


def get_company_price_intelligence_run(
    company_name: str,
    *,
    run_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    where_sql = "company_name = %s"
    params: List[Any] = [company_name]
    if run_id is not None:
        where_sql += " AND id = %s"
        params.append(int(run_id))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, as_of_date, provider, model, {COL_OUTPUT_LANGUAGE},
                       context_window_days, focus_window_days, input_payload, output_json, output_text, created_at
                FROM {TBL_COMPANY_PRICE_INTELLIGENCE_RUN}
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        return None
    structured = _parse_json_object(row["output_json"] or "") or {}
    payload = {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "as_of_date": row["as_of_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "context_window_days": int(row["context_window_days"] or 0),
        "focus_window_days": int(row["focus_window_days"] or 0),
        "input_payload": _parse_json_object(row["input_payload"] or "") or {},
        "output_json": row["output_json"] or "",
        "output_text": row["output_text"] or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(structured)
    return payload


def list_company_price_intelligence_runs(company_name: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, as_of_date, provider, model, {COL_OUTPUT_LANGUAGE},
                       context_window_days, focus_window_days, output_json, output_text, created_at
                FROM {TBL_COMPANY_PRICE_INTELLIGENCE_RUN}
                WHERE company_name = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (company_name, safe_limit),
            )
            rows = cur.fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        structured = _parse_json_object(row["output_json"] or "") or {}
        result.append(
            {
                "id": int(row["id"]),
                "company_name": row["company_name"],
                "as_of_date": row["as_of_date"].isoformat(),
                "provider": row["provider"],
                "model": row["model"],
                "output_language": row[COL_OUTPUT_LANGUAGE],
                "context_window_days": int(row["context_window_days"] or 0),
                "focus_window_days": int(row["focus_window_days"] or 0),
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "bottom_line": str(structured.get("bottom_line") or ""),
                "current_price": structured.get("current_price"),
                "fair_price_zone": structured.get("fair_price_zone") if isinstance(structured.get("fair_price_zone"), dict) else {},
                "price_position": structured.get("price_position") if isinstance(structured.get("price_position"), dict) else {},
            }
        )
    return result


def get_company_news_for_range(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    llm_model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
) -> List[NewsArticle]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    r.id AS raw_id,
                    r.company_name,
                    r.news_date_time,
                    r.news_title,
                    r.content AS original_content,
                    a.content AS llm_analyzed_content,
                    a.{COL_OUTPUT_LANGUAGE} AS analyzed_output_language,
                    COALESCE(a.source_link, r.source_link) AS news_source_link,
                    COALESCE(a.source, r.source) AS news_source,
                    COALESCE(r.is_analyzed, FALSE) AS is_analyzed,
                    COALESCE(r.is_filtered, FALSE) AS is_filtered
                FROM company_news_raw AS r
                LEFT JOIN LATERAL (
                    SELECT
                        aa.content,
                        aa.{COL_OUTPUT_LANGUAGE},
                        aa.source_link,
                        aa.source
                    FROM {TBL_COMPANY_NEWS_ANALYZED} AS aa
                    WHERE aa.company_name = r.company_name
                      AND aa.news_title = r.news_title
                      AND aa.news_date_time = r.news_date_time
                    ORDER BY
                        CASE WHEN aa.{COL_OUTPUT_LANGUAGE} = %s THEN 0 ELSE 1 END,
                        CASE WHEN aa.llm_model = %s THEN 0 ELSE 1 END,
                        aa.id DESC
                    LIMIT 1
                ) AS a ON TRUE
                WHERE r.company_name = %s
                  AND r.news_date_time >= %s
                  AND r.news_date_time < %s
                ORDER BY r.news_date_time DESC, r.id DESC
                """,
                (output_language, llm_model, company_name, start_dt, end_dt),
            )
            return [
                NewsArticle(
                    id=row["raw_id"],
                    company_name=row["company_name"],
                    news_date_time=row["news_date_time"],
                    news_title=row["news_title"],
                    original_content=row["original_content"],
                    llm_analyzed_content=row["llm_analyzed_content"],
                    news_source_link=row["news_source_link"],
                    news_source=row["news_source"],
                    is_analyzed=bool(row["is_analyzed"]),
                    is_filtered=bool(row["is_filtered"]),
                    analyzed_output_language=row.get("analyzed_output_language"),
                )
                for row in cur.fetchall()
            ]


def generate_weekly_report(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    output_language: str = "zh-CN",
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return None
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    items = _build_weekly_report_input_items(
        company_name,
        start_date=start_date,
        end_date=end_date,
        llm_model=model,
        provider_name=provider_name,
    )
    if not items:
        return None
    report = provider.fetch_weekly_report(
        company_name=company_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        articles=items,
        output_language=output_language,
    )
    _store_weekly_report(
        company_name,
        start_date=start_date,
        end_date=end_date,
        report_payload=report,
    )
    return report


def generate_monthly_report(
    company_name: str,
    *,
    month_start: date,
    month_end: date,
    output_language: str = "zh-CN",
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return None
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    weekly_reports = _build_monthly_report_input_items(
        company_name,
        month_start=month_start,
        month_end=month_end,
    )
    if not weekly_reports:
        return None
    prompt = _build_company_monthly_report_prompt(
        company_name,
        month_start=month_start,
        month_end=month_end,
        weekly_reports=weekly_reports,
        output_language=output_language,
    )
    payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    report = _normalize_structured_period_report(payload)
    if not any(report.values()):
        return None
    _store_weekly_report(
        company_name,
        start_date=month_start,
        end_date=month_end,
        report_payload=report,
    )
    return report


def generate_company_daily_report(
    company_name: str,
    *,
    target_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 90,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "item_count": 0, "elapsed_sec": 0.0}

    items = _build_company_daily_report_input_items(
        company_name,
        target_date=target_date,
        llm_model=model,
    )
    if not items:
        return {"generated": False, "item_count": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_daily_report_prompt(
        company_name,
        target_date=target_date,
        items=items,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    output_text = provider.generate_text(prompt=prompt)
    _upsert_company_daily_report(
        company_name=company_name,
        report_date=target_date,
        provider=provider_name,
        model=model,
        prompt_style=prompt_style,
        input_payload={"items": items, "prompt": prompt},
        output_text=output_text,
    )
    return {
        "generated": True,
        "item_count": len(items),
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }


def list_company_daily_clusters(
    company_name: str,
    *,
    target_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                WHERE company_name = %s
                  AND cluster_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                """,
                (company_name, target_date, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "company_name": row["company_name"],
            "cluster_date": row["cluster_date"].isoformat(),
            "cluster_key": row["cluster_key"],
            "cluster_title": row["cluster_title"],
            "cluster_summary": row["cluster_summary"] or "",
            "source_news": row["source_news_json"] or [],
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if row["updated_at"] else "",
        }
        for row in rows
    ]


def refresh_company_daily_clusters(
    company_name: str,
    *,
    target_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "cluster_count": 0, "target_date": target_date.isoformat()}
    items = _build_company_story_incremental_news_items(
        company_name,
        target_date=target_date,
        llm_model=model,
        output_language=output_language,
    )
    if not items:
        return {"generated": False, "cluster_count": 0, "target_date": target_date.isoformat()}
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_daily_cluster_prompt(
        company_name,
        target_date=target_date,
        items=items,
        output_language=output_language,
    )
    payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    clusters = _normalize_company_cluster_rows(
        company_name=company_name,
        target_date=target_date,
        payload=payload,
    )
    _replace_company_daily_clusters(
        company_name=company_name,
        target_date=target_date,
        clusters=clusters,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"items": items, "prompt": prompt},
    )
    return {"generated": True, "cluster_count": len(clusters), "target_date": target_date.isoformat()}


def generate_company_status_snapshot(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    window_days: int = 90,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "daily_report_count": 0, "weekly_report_count": 0, "elapsed_sec": 0.0, "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}

    end_date = as_of_date or datetime.now(timezone.utc).date()
    safe_window_days = max(7, min(int(window_days), 90))
    start_date = end_date - timedelta(days=safe_window_days - 1)
    status_input = _build_company_price_intelligence_input(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        output_language=output_language,
    )
    price_point_count = int((status_input.get("price_context") or {}).get("point_count") or 0)
    if price_point_count <= 0:
        return {
            "generated": False,
            "price_point_count": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
            "input_item_count": 0,
            "prompt_char_count": 0,
            "output_char_count": 0,
        }

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_price_intelligence_prompt(
        company_name,
        as_of_date=end_date,
        status_input=status_input,
        output_language=output_language,
    )
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    normalized_output = _normalize_company_status_payload(payload, as_of_date=end_date)
    output_text = str(normalized_output.get("output_markdown") or "").strip() or raw_output
    _upsert_company_status_snapshot(
        company_name=company_name,
        as_of_date=end_date,
        window_start_date=start_date,
        window_end_date=end_date,
        provider=provider_name,
        model=model,
        prompt_style="simple",
        input_payload={"prompt": prompt, **status_input},
        output_json=normalized_output,
        output_text=output_text,
    )
    return {
        "generated": True,
        "price_point_count": price_point_count,
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        "input_item_count": int((status_input.get("input_coverage") or {}).get("input_item_count") or 0),
        "prompt_char_count": len(prompt),
        "output_char_count": len(output_text or ""),
    }


def generate_company_price_intelligence_run(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
    context_window_days: int = 365,
    focus_window_days: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "elapsed_sec": 0.0, "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    end_date = as_of_date or datetime.now(timezone.utc).date()
    safe_context_days = max(180, min(int(context_window_days), 365))
    safe_focus_days = max(14, min(int(focus_window_days), 90))
    context_start = end_date - timedelta(days=safe_context_days - 1)
    focus_start = end_date - timedelta(days=safe_focus_days - 1)
    previous_run = get_company_price_intelligence_run(company_name)
    pi_input = _build_company_quick_price_intelligence_input(
        company_name,
        context_start=context_start,
        focus_start=focus_start,
        end_date=end_date,
        provider_name=provider_name,
        output_language=output_language,
    )
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_quick_price_intelligence_prompt(
        company_name=company_name,
        as_of_date=end_date,
        quick_input=pi_input,
        previous_run=previous_run,
        output_language=output_language,
    )
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    normalized_output = _normalize_company_quick_price_intelligence_payload(
        payload,
        as_of_date=end_date,
        current_price=pi_input.get("latest_price"),
        previous_run=previous_run,
    )
    output_text = str(normalized_output.get("output_markdown") or "").strip() or raw_output
    run_id = _insert_company_price_intelligence_run(
        company_name=company_name,
        as_of_date=end_date,
        provider=provider_name,
        model=model,
        output_language=output_language,
        context_window_days=safe_context_days,
        focus_window_days=safe_focus_days,
        input_payload={"prompt": prompt, **pi_input},
        output_json=normalized_output,
        output_text=output_text,
    )
    return {
        "generated": True,
        "run_id": run_id,
        "daily_report_count": len(pi_input.get("daily_reports") or []),
        "raw_news_count": len(pi_input.get("raw_news_fallback") or []),
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        "input_item_count": int(pi_input.get("input_coverage", {}).get("input_item_count", 0)),
        "prompt_char_count": len(prompt),
        "output_char_count": len(output_text or ""),
    }


def list_company_story_states(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    story_title,
                    story_summary,
                    importance_rank,
                    story_status,
                    priority,
                    confidence,
                    happened_text,
                    happening_text,
                    next_text,
                    timeline_json,
                    future_impact_json,
                    open_questions_json,
                    evidence_json,
                    change_log_json,
                    last_event_at,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    is_active,
                    updated_at,
                    created_at
                FROM {TBL_COMPANY_STORY_STATE}
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                ORDER BY importance_rank ASC, updated_at DESC, id DESC
                """,
                (company_name, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [_row_to_story_state(row) for row in rows]


def get_company_story_state(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    story_title,
                    story_summary,
                    importance_rank,
                    story_status,
                    priority,
                    confidence,
                    happened_text,
                    happening_text,
                    next_text,
                    timeline_json,
                    future_impact_json,
                    open_questions_json,
                    evidence_json,
                    change_log_json,
                    last_event_at,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    is_active,
                    updated_at,
                    created_at
                FROM {TBL_COMPANY_STORY_STATE}
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (company_name, story_key, provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_story_state(row)


def list_company_story_updates(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    limit: int = 12,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    safe_limit = max(1, min(int(limit), 60))
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    as_of_date,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload,
                    output_json,
                    created_at
                FROM {TBL_COMPANY_STORY_UPDATE}
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (
                    company_name,
                    story_key,
                    provider_name,
                    prompt_style,
                    output_language,
                    safe_limit,
                ),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "company_name": row["company_name"],
            "story_key": row[COL_STORY_KEY],
            "as_of_date": row["as_of_date"].isoformat(),
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "input_payload": row["input_payload"] or "",
            "output_json": row["output_json"] or "",
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def get_latest_company_story_update_date(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> str:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(as_of_date) AS latest_story_date
                FROM {TBL_COMPANY_STORY_UPDATE}
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (company_name, provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    latest = row["latest_story_date"] if row else None
    return latest.isoformat() if latest else ""


def list_company_story_qa(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    limit: int = 12,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    safe_limit = max(1, min(int(limit), 40))
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    question,
                    answer,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload,
                    created_at
                FROM {TBL_COMPANY_STORY_QA}
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (
                    company_name,
                    story_key,
                    provider_name,
                    prompt_style,
                    output_language,
                    safe_limit,
                ),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "company_name": row["company_name"],
            "story_key": row[COL_STORY_KEY],
            "question": row["question"] or "",
            "answer": row["answer"] or "",
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "input_payload": row["input_payload"] or "",
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def refresh_company_story_states(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    window_days: int = 21,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "story_count": 0, "elapsed_sec": 0.0}

    end_date = as_of_date or datetime.now(timezone.utc).date()
    existing = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    clusters = list_company_daily_clusters(
        company_name,
        target_date=end_date,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not clusters:
        return {
            "generated": False,
            "story_count": len(existing),
            "routed_cluster_count": 0,
            "updated_story_count": 0,
            "new_story_count": 0,
            "ignored_cluster_count": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        }
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    routing_prompt = _build_company_story_routing_prompt(
        company_name,
        as_of_date=end_date,
        prompt_style=prompt_style,
        output_language=output_language,
        existing_stories=existing,
        clusters=clusters,
    )
    routing_raw_output = provider.generate_text(prompt=routing_prompt)
    routing_payload = _parse_json_object(routing_raw_output) or {}
    routing_result = _normalize_story_routing_result(
        existing_stories=existing,
        clusters=clusters,
        payload=routing_payload,
    )
    applied = _apply_incremental_story_updates(
        company_name=company_name,
        as_of_date=end_date,
        provider=provider,
        existing_stories=existing,
        routed=routing_result,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    final_stories = applied["stories"]
    if not final_stories:
        return {
            "generated": False,
            "story_count": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        }
    _persist_story_refresh(
        company_name=company_name,
        as_of_date=end_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={
            "routing_prompt": routing_prompt,
            "routing_result": routing_result,
            "daily_clusters": clusters,
            "existing_story_count": len(existing),
            "updated_story_keys": applied["updated_story_keys"],
            "new_story_keys": applied["new_story_keys"],
        },
        raw_output=json.dumps(
            {
                "routing": routing_payload,
                "applied": applied["raw_outputs"],
            },
            ensure_ascii=False,
        ),
        stories=final_stories,
    )
    return {
        "generated": True,
        "story_count": len(final_stories),
        "routed_cluster_count": len(clusters),
        "updated_story_count": len(applied["updated_story_keys"]),
        "new_story_count": len(applied["new_story_keys"]),
        "ignored_cluster_count": len(routing_result["ignored_items"]),
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }


def ask_company_story_question(
    company_name: str,
    *,
    story_key: str,
    question: str,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 90,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    story_key = str(story_key or "").strip()
    question = str(question or "").strip()
    if not company_name or not story_key or not question:
        return None
    story = get_company_story_state(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not story:
        return None
    updates = list_company_story_updates(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=4,
    )
    prompt = _build_company_story_qa_prompt(
        company_name=company_name,
        output_language=output_language,
        story=story,
        recent_updates=updates,
        question=question,
    )
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    answer = provider.generate_text(prompt=prompt)
    row = _insert_story_qa(
        company_name=company_name,
        story_key=story_key,
        question=question,
        answer=answer,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"prompt": prompt, "story": story, "recent_updates": updates},
    )
    return row


def merge_company_story_qa_answer(
    company_name: str,
    *,
    story_key: str,
    qa_id: int,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 90,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    story_key = str(story_key or "").strip()
    if not company_name or not story_key:
        return None
    story = get_company_story_state(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not story:
        return None
    qa_row = _get_company_story_qa_row(
        company_name,
        story_key=story_key,
        qa_id=qa_id,
    )
    if not qa_row:
        return None
    recent_updates = list_company_story_updates(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=4,
    )
    prompt = _build_company_story_qa_merge_prompt(
        company_name=company_name,
        output_language=output_language,
        story=story,
        recent_updates=recent_updates,
        qa_row=qa_row,
    )
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    merged_story = _normalize_incremental_story_item(
        payload,
        fallback_story_key=story_key,
        fallback_story_title=str(story.get("story_title") or story_key),
        fallback_rank=int(story.get("importance_rank") or 999),
    )
    if not merged_story:
        return None
    all_stories = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    merged_stories: List[Dict[str, Any]] = []
    replaced = False
    for item in all_stories:
        if str(item.get("story_key") or "").strip() == story_key:
            merged_stories.append(merged_story)
            replaced = True
        else:
            merged_stories.append(item)
    if not replaced:
        merged_stories.append(merged_story)
    merged_stories = sorted(
        [_normalize_story_record(item) for item in merged_stories if isinstance(item, dict)],
        key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or "")),
    )
    _persist_story_refresh(
        company_name=company_name,
        as_of_date=datetime.now(timezone.utc).date(),
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={
            "merge_source": "story_qa",
            "qa_row": qa_row,
            "story": story,
            "recent_updates": recent_updates,
            "prompt": prompt,
        },
        raw_output=raw_output,
        stories=merged_stories,
    )
    return merged_story


def update_company_story_status(
    company_name: str,
    *,
    story_key: str,
    story_status: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TBL_COMPANY_STORY_STATE}
                SET story_status = %s, updated_at = NOW()
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                """,
                (story_status, company_name, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def update_company_story_priority(
    company_name: str,
    *,
    story_key: str,
    priority: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TBL_COMPANY_STORY_STATE}
                SET priority = %s, updated_at = NOW()
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                """,
                (priority, company_name, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def create_company_story_from_news(
    company_name: str,
    *,
    target_date: date,
    story_title: str,
    news_item: Dict[str, Any],
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    title = str(story_title or news_item.get("news_title") or "").strip()
    if not company_name or not title:
        return None
    existing = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    story_key = _normalize_story_key("", fallback_title=title, fallback_index=len(existing))
    story = _normalize_story_record(
        {
            "story_key": story_key,
            "story_title": title,
            "story_summary": str(news_item.get("summary") or news_item.get("news_title") or "").strip(),
            "importance_rank": len(existing) + 1,
            "story_status": "ongoing",
            "priority": "normal",
            "timeline_items": [
                {
                    "date": target_date.isoformat(),
                    "label": str(news_item.get("news_title") or title).strip(),
                    "summary": str(news_item.get("summary") or "").strip(),
                }
            ],
            "future_and_impact": [],
            "evidence": [
                {
                    "news_title": str(news_item.get("news_title") or title).strip(),
                    "news_date_time": str(news_item.get("news_date_time") or target_date.isoformat()),
                    "news_source_link": str(news_item.get("news_source_link") or "").strip(),
                    "summary": str(news_item.get("summary") or "").strip(),
                }
            ],
            "change_log": ["Created manually from company news."],
        }
    )
    if not story:
        return None
    _persist_story_refresh(
        company_name=company_name,
        as_of_date=target_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"manual_action": "create_story_from_news", "news_item": news_item},
        raw_output=json.dumps({"story": story}, ensure_ascii=False),
        stories=sorted(existing + [story], key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or ""))),
    )
    return story


def attach_news_to_company_story(
    company_name: str,
    *,
    target_date: date,
    story_key: str,
    news_item: Dict[str, Any],
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    company_name = _normalize_company_name(company_name)
    stories = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    updated: List[Dict[str, Any]] = []
    matched = False
    for story in stories:
        if str(story.get("story_key") or "").strip() != str(story_key or "").strip():
            updated.append(story)
            continue
        matched = True
        next_story = dict(story)
        timeline_items = list(next_story.get("timeline_items") or [])
        timeline_items.append(
            {
                "date": target_date.isoformat(),
                "label": str(news_item.get("news_title") or "").strip() or next_story.get("story_title"),
                "summary": str(news_item.get("summary") or "").strip(),
            }
        )
        evidence = list(next_story.get("evidence") or [])
        evidence.append(
            {
                "news_title": str(news_item.get("news_title") or "").strip(),
                "news_date_time": str(news_item.get("news_date_time") or target_date.isoformat()),
                "news_source_link": str(news_item.get("news_source_link") or "").strip(),
                "summary": str(news_item.get("summary") or "").strip(),
            }
        )
        change_log = list(next_story.get("change_log") or [])
        change_log.append("Attached manually from company news.")
        next_story["timeline_items"] = timeline_items
        next_story["evidence"] = evidence
        next_story["change_log"] = change_log
        next_story["story_status"] = "ongoing"
        updated.append(next_story)
    if not matched:
        return False
    _persist_story_refresh(
        company_name=company_name,
        as_of_date=target_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"manual_action": "attach_news_to_story", "story_key": story_key, "news_item": news_item},
        raw_output=json.dumps({"story_key": story_key, "news_item": news_item}, ensure_ascii=False),
        stories=updated,
    )
    return True


def summarize_company_news_item(
    company_name: str,
    *,
    news_id: int,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    analysis_prompt: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    logger.info(
        "Analyze single news start: company=%s news_id=%s model=%s provider=%s prompt=%s",
        company_name,
        news_id,
        model,
        provider_name,
        analysis_prompt,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    company_name,
                    news_date_time,
                    news_title,
                    content,
                    source,
                    source_link
                FROM company_news_raw
                WHERE company_name = %s
                  AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
    if not row:
        logger.info(
            "Analyze single news skipped: company=%s news_id=%s not found",
            company_name,
            news_id,
        )
        return False

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    start_date = row["news_date_time"].date().isoformat()
    end_date = start_date
    analyzed = provider.analyze_news_items(
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
        analysis_prompt=analysis_prompt,
        items=[
            {
                "news_date_time": row["news_date_time"].isoformat(),
                "news_title": row["news_title"],
                "original_content": row["content"],
                "news_source_link": row["source_link"],
                "news_source": row["source"],
            }
        ],
    )
    if not analyzed:
        logger.warning(
            "Analyze single news failed: company=%s news_id=%s empty analysis result",
            company_name,
            news_id,
        )
        return False

    article = _news_item_from_payload(
        company_name,
        analyzed[0],
        end_date=row["news_date_time"].date(),
        analyzed=True,
    )
    _store_articles([article], llm_model=model, output_language=output_language)
    logger.info(
        "Analyze single news finish: company=%s news_id=%s outcome=analyzed",
        company_name,
        news_id,
    )
    return True


def summarize_company_news_day(
    company_name: str,
    *,
    target_date: date,
    limit: int = 5,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    analysis_prompt: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"processed": 0, "analyzed": 0, "dropped": 0, "elapsed_sec": 0.0}
    logger.info(
        "Analyze day start: company=%s date=%s limit=%s model=%s provider=%s prompt=%s",
        company_name,
        target_date.isoformat(),
        limit,
        model,
        provider_name,
        analysis_prompt,
    )

    safe_limit = max(1, min(int(limit), 100))
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    company_name,
                    news_date_time,
                    news_title,
                    content,
                    source,
                    source_link
                FROM company_news_raw
                WHERE company_name = %s
                  AND news_date_time >= %s
                  AND news_date_time < %s
                  AND COALESCE(is_analyzed, FALSE) = FALSE
                ORDER BY news_date_time DESC, id DESC
                LIMIT %s
                """,
                (company_name, start_dt, end_dt, safe_limit),
            )
            rows = cur.fetchall()
    logger.info(
        "Analyze day selected raw items: company=%s date=%s count=%d",
        company_name,
        target_date.isoformat(),
        len(rows),
    )

    if not rows:
        logger.info(
            "Analyze day finish: company=%s date=%s processed=0 analyzed=0 dropped=0 elapsed=%.2fs",
            company_name,
            target_date.isoformat(),
            pytime.perf_counter() - started_at,
        )
        return {
            "processed": 0,
            "analyzed": 0,
            "dropped": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        }

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    analyzed_count = 0
    total_batches = (len(rows) + ANALYZE_DAY_BATCH_SIZE - 1) // ANALYZE_DAY_BATCH_SIZE
    for batch_index, offset in enumerate(
        range(0, len(rows), ANALYZE_DAY_BATCH_SIZE), start=1
    ):
        batch_rows = rows[offset : offset + ANALYZE_DAY_BATCH_SIZE]
        logger.info(
            "Analyze day batch start: company=%s date=%s batch=%d/%d size=%d",
            company_name,
            target_date.isoformat(),
            batch_index,
            total_batches,
            len(batch_rows),
        )
        analyzed_items = provider.analyze_news_items(
            company_name=company_name,
            start_date=target_date.isoformat(),
            end_date=target_date.isoformat(),
            analysis_prompt=analysis_prompt,
            items=[
                {
                    "news_date_time": row["news_date_time"].isoformat(),
                    "news_title": row["news_title"],
                    "original_content": row["content"],
                    "news_source_link": row["source_link"],
                    "news_source": row["source"],
                }
                for row in batch_rows
            ],
        )
        logger.info(
            "Analyze day batch end: company=%s date=%s batch=%d/%d returned=%d",
            company_name,
            target_date.isoformat(),
            batch_index,
            total_batches,
            len(analyzed_items),
        )

        row_by_title: Dict[str, List[Dict[str, Any]]] = {}
        for row in batch_rows:
            key = str(row["news_title"] or "").strip().lower()
            row_by_title.setdefault(key, []).append(row)

        batch_articles: List[NewsArticle] = []
        for item in analyzed_items:
            title_key = str(item.get("news_title") or "").strip().lower()
            matched_row = None
            if title_key and title_key in row_by_title and row_by_title[title_key]:
                matched_row = row_by_title[title_key].pop(0)
            if matched_row is None:
                continue
            batch_articles.append(
                _news_item_from_payload(
                    company_name,
                    item,
                    end_date=target_date,
                    analyzed=True,
                )
            )
        if batch_articles:
            _store_articles(
                batch_articles,
                llm_model=model,
                output_language=output_language,
            )
            analyzed_count += len(batch_articles)

    logger.info(
        "Analyze day finish: company=%s date=%s processed=%d analyzed=%d dropped=%d elapsed=%.2fs",
        company_name,
        target_date.isoformat(),
        len(rows),
        analyzed_count,
        0,
        pytime.perf_counter() - started_at,
    )
    return {
        "processed": len(rows),
        "analyzed": analyzed_count,
        "dropped": 0,
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }


def filter_company_news_item(
    company_name: str,
    *,
    news_id: int,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"filtered": False, "dropped": False, "reason": "invalid company"}

    logger.info(
        "Filter single news start: company=%s news_id=%s model=%s provider=%s",
        company_name,
        news_id,
        model,
        provider_name,
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    company_name,
                    news_date_time,
                    news_title,
                    content,
                    source,
                    source_link
                FROM company_news_raw
                WHERE company_name = %s
                  AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
    if not row:
        logger.info(
            "Filter single news skipped: company=%s news_id=%s not found",
            company_name,
            news_id,
        )
        return {"filtered": False, "dropped": False, "reason": "not found"}

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    decisions = provider.filter_news_items(
        company_name=company_name,
        items=[
            {
                "news_title": row["news_title"],
            }
        ],
    )
    if not decisions:
        logger.warning(
            "Filter single news failed: company=%s news_id=%s empty filter result",
            company_name,
            news_id,
        )
        return {"filtered": False, "dropped": False, "reason": "empty filter result"}

    if not _is_item_relevant(decisions[0]):
        drop_reason = "Filtered by title relevance"
        _delete_raw_news_by_id(
            company_name,
            news_id,
            drop_reason=drop_reason,
            llm_model=model,
            dropped_by="manual_filter",
        )
        logger.info(
            "Filter single news finish: company=%s news_id=%s outcome=dropped reason=%s",
            company_name,
            news_id,
            drop_reason,
        )
        return {"filtered": True, "dropped": True, "reason": drop_reason}

    _mark_raw_news_filtered_by_id(company_name, news_id)
    logger.info(
        "Filter single news finish: company=%s news_id=%s outcome=kept",
        company_name,
        news_id,
    )
    return {"filtered": True, "dropped": False, "reason": ""}


def filter_company_news_day(
    company_name: str,
    *,
    target_date: date,
    limit: int = 5,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"processed": 0, "kept": 0, "dropped": 0, "elapsed_sec": 0.0}

    logger.info(
        "Filter day start: company=%s date=%s limit=%s model=%s provider=%s",
        company_name,
        target_date.isoformat(),
        limit,
        model,
        provider_name,
    )
    safe_limit = max(1, min(int(limit), 100))
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    company_name,
                    news_date_time,
                    news_title,
                    content,
                    source,
                    source_link,
                    COALESCE(is_analyzed, FALSE) AS is_analyzed
                FROM company_news_raw
                WHERE company_name = %s
                  AND news_date_time >= %s
                  AND news_date_time < %s
                  AND COALESCE(is_filtered, FALSE) = FALSE
                ORDER BY news_date_time DESC, id DESC
                LIMIT %s
                """,
                (company_name, start_dt, end_dt, safe_limit),
            )
            rows = cur.fetchall()
    logger.info(
        "Filter day selected items: company=%s date=%s count=%d",
        company_name,
        target_date.isoformat(),
        len(rows),
    )
    if not rows:
        logger.info(
            "Filter day finish: company=%s date=%s processed=0 kept=0 dropped=0 elapsed=%.2fs",
            company_name,
            target_date.isoformat(),
            pytime.perf_counter() - started_at,
        )
        return {
            "processed": 0,
            "kept": 0,
            "dropped": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        }

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    dropped_count = 0
    kept_count = 0
    total_batches = (len(rows) + FILTER_DAY_BATCH_SIZE - 1) // FILTER_DAY_BATCH_SIZE
    for batch_index, offset in enumerate(
        range(0, len(rows), FILTER_DAY_BATCH_SIZE), start=1
    ):
        batch_rows = rows[offset : offset + FILTER_DAY_BATCH_SIZE]
        batch_selected_ids = [int(row["id"]) for row in batch_rows]
        batch_dropped = 0
        logger.info(
            "Filter day batch start: company=%s date=%s batch=%d/%d size=%d",
            company_name,
            target_date.isoformat(),
            batch_index,
            total_batches,
            len(batch_rows),
        )
        decisions = provider.filter_news_items(
            company_name=company_name,
            items=[
                {"news_title": title}
                for title in list(
                    dict.fromkeys(str(row["news_title"] or "").strip() for row in batch_rows)
                )
                if title
            ],
        )
        logger.info(
            "Filter day batch end: company=%s date=%s batch=%d/%d returned=%d",
            company_name,
            target_date.isoformat(),
            batch_index,
            total_batches,
            len(decisions),
        )

        row_by_title: Dict[str, List[Dict[str, Any]]] = {}
        for row in batch_rows:
            key = str(row["news_title"] or "").strip().lower()
            row_by_title.setdefault(key, []).append(row)

        drop_title_keys: set[str] = set()
        for decision in decisions:
            title_key = str(decision.get("news_title") or "").strip().lower()
            if not title_key:
                continue
            if _is_item_relevant(decision):
                continue
            drop_title_keys.add(title_key)

        for title_key in drop_title_keys:
            matched_rows = row_by_title.get(title_key, [])
            for matched_row in matched_rows:
                _delete_raw_news_by_id(
                    company_name,
                    int(matched_row["id"]),
                    drop_reason="Filtered by title relevance",
                    llm_model=model,
                    dropped_by="manual_filter",
                )
                dropped_count += 1
                batch_dropped += 1

        # Persist batch progress immediately so partially finished runs still
        # prevent re-filtering of already-processed kept items.
        _mark_raw_news_filtered_by_ids(company_name, batch_selected_ids)
        batch_kept = max(0, len(batch_rows) - batch_dropped)
        kept_count += batch_kept
        logger.info(
            "Filter day batch progress: company=%s date=%s batch=%d/%d kept=%d dropped=%d",
            company_name,
            target_date.isoformat(),
            batch_index,
            total_batches,
            batch_kept,
            batch_dropped,
        )
    logger.info(
        "Filter day finish: company=%s date=%s processed=%d kept=%d dropped=%d elapsed=%.2fs",
        company_name,
        target_date.isoformat(),
        len(rows),
        kept_count,
        dropped_count,
        pytime.perf_counter() - started_at,
    )
    return {
        "processed": len(rows),
        "kept": kept_count,
        "dropped": dropped_count,
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }


def get_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    company_name,
                    ticker,
                    name,
                    exchange,
                    currency,
                    country,
                    ipo,
                    weburl,
                    logo,
                    finnhub_industry,
                    phone,
                    market_capitalization,
                    share_outstanding,
                    cusip,
                    isin,
                    lei,
                    properties_extension
                FROM company_profile
                WHERE company_name = %s
                """,
                (company_name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            profile = {key: row[key] for key in row.keys()}
            extra = profile.pop("properties_extension", None) or {}
            if isinstance(extra, dict):
                profile.update(extra)
            return profile


def set_company_ticker(company_name: str, ticker: Optional[str]) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return None
    normalized_ticker = _normalize_ticker(ticker)
    existing = get_company_profile(company_name)
    existing_ticker = _normalize_ticker(existing.get("ticker")) if existing else None
    if company_has_fetched_data(company_name) and normalized_ticker != existing_ticker:
        raise ValueError("ticker cannot be changed after company news or story data has been fetched")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_profile (
                    company_name,
                    ticker,
                    fetched_at
                )
                VALUES (%s, %s, NOW())
                ON CONFLICT (company_name)
                DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    fetched_at = NOW()
                """,
                (company_name, normalized_ticker),
            )
        conn.commit()
    return get_company_profile(company_name)


def company_has_fetched_data(company_name: str) -> bool:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    with get_connection() as conn:
        with conn.cursor() as cur:
            checks = [
                "SELECT EXISTS(SELECT 1 FROM company_news_raw WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_NEWS_ANALYZED} WHERE company_name = %s LIMIT 1)",
                "SELECT EXISTS(SELECT 1 FROM company_news_daily_report WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER} WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_STORY_STATE} WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_STORY_UPDATE} WHERE company_name = %s LIMIT 1)",
            ]
            for sql in checks:
                cur.execute(sql, (company_name,))
                row = cur.fetchone()
                if row and bool(row[0]):
                    return True
    return False


def _has_company_raw_for_day(company_name: str, target_date: date) -> bool:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM company_news_raw
                    WHERE company_name = %s
                      AND news_date_time >= %s
                      AND news_date_time < %s
                    LIMIT 1
                )
                """,
                (company_name, start_dt, end_dt),
            )
            row = cur.fetchone()
    return bool(row and row[0])


def _count_company_raw_for_range(company_name: str, start_date: date, end_date: date) -> int:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return 0
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM company_news_raw
                WHERE company_name = %s
                  AND news_date_time >= %s
                  AND news_date_time < %s
                """,
                (company_name, start_dt, end_dt),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _build_fetch_ranges_for_slice(
    company_name: str,
    *,
    slice_start: date,
    slice_end: date,
    today: date,
) -> List[tuple[date, date]]:
    fetch_days: List[date] = []
    current = slice_start
    while current <= slice_end:
        if current >= today or not _has_company_raw_for_day(company_name, current):
            fetch_days.append(current)
        current += timedelta(days=1)
    if not fetch_days:
        return []
    ranges: List[tuple[date, date]] = []
    range_start = fetch_days[0]
    prev = fetch_days[0]
    for day in fetch_days[1:]:
        if day == prev + timedelta(days=1):
            prev = day
            continue
        ranges.append((range_start, prev))
        range_start = day
        prev = day
    ranges.append((range_start, prev))
    return ranges


def ensure_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    existing = get_company_profile(company_name)
    if existing:
        return existing
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        logger.warning("FINNHUB_API_KEY not set; skipping profile fetch for %s", company_name)
        return None
    client = FinnhubClient(api_key)
    logger.info("Resolving ticker via Finnhub symbol lookup for %s", company_name)
    ticker = _resolve_symbol_from_lookup(client.symbol_lookup(company_name), company_name)
    if not ticker:
        fallback_ticker = resolve_company_ticker_fallback(company_name)
        if not fallback_ticker:
            logger.warning("Symbol lookup returned no ticker for %s", company_name)
            return None
        ticker = fallback_ticker
        logger.info(
            "Using manual ticker fallback for %s (ticker=%s)",
            company_name,
            ticker,
        )
    logger.info("Fetching company profile from Finnhub for %s (ticker=%s)", company_name, ticker)
    profile = client.company_profile(ticker)
    if not profile:
        logger.warning("Finnhub profile fetch returned empty for %s (ticker=%s)", company_name, ticker)
        return None
    logger.info("Finnhub profile fetch succeeded for %s", company_name)
    properties_extension = _extract_profile_extension(profile)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_profile (
                    company_name,
                    ticker,
                    name,
                    exchange,
                    currency,
                    country,
                    ipo,
                    weburl,
                    logo,
                    finnhub_industry,
                    phone,
                    market_capitalization,
                    share_outstanding,
                    cusip,
                    isin,
                    lei,
                    properties_extension
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (company_name)
                DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange,
                    currency = EXCLUDED.currency,
                    country = EXCLUDED.country,
                    ipo = EXCLUDED.ipo,
                    weburl = EXCLUDED.weburl,
                    logo = EXCLUDED.logo,
                    finnhub_industry = EXCLUDED.finnhub_industry,
                    phone = EXCLUDED.phone,
                    market_capitalization = EXCLUDED.market_capitalization,
                    share_outstanding = EXCLUDED.share_outstanding,
                    cusip = EXCLUDED.cusip,
                    isin = EXCLUDED.isin,
                    lei = EXCLUDED.lei,
                    properties_extension = EXCLUDED.properties_extension,
                    fetched_at = NOW()
                """,
                (
                    company_name,
                    profile.get("ticker") or profile.get("symbol"),
                    profile.get("name"),
                    profile.get("exchange"),
                    profile.get("currency"),
                    profile.get("country"),
                    profile.get("ipo") or None,
                    profile.get("weburl"),
                    profile.get("logo"),
                    profile.get("finnhubIndustry"),
                    profile.get("phone"),
                    profile.get("marketCapitalization"),
                    profile.get("shareOutstanding"),
                    profile.get("cusip"),
                    profile.get("isin"),
                    profile.get("lei"),
                    json.dumps(properties_extension) if properties_extension else None,
                ),
            )
        conn.commit()
    return profile


def delete_company_news(company_name: str, *, news_id: int) -> None:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT news_title, news_date_time
                FROM company_news_raw
                WHERE company_name = %s AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    DELETE FROM company_news_analyzed
                    WHERE company_name = %s
                      AND news_title = %s
                      AND news_date_time = %s
                    """,
                    (company_name, row["news_title"], row["news_date_time"]),
                )
                cur.execute(
                    "DELETE FROM company_news_raw WHERE company_name = %s AND id = %s",
                    (company_name, news_id),
                )
            else:
                cur.execute(
                    """
                    SELECT news_title, news_date_time
                    FROM company_news_analyzed
                    WHERE company_name = %s AND id = %s
                    """,
                    (company_name, news_id),
                )
                old_row = cur.fetchone()
                if not old_row:
                    return
                cur.execute(
                    "DELETE FROM company_news_analyzed WHERE company_name = %s AND id = %s",
                    (company_name, news_id),
                )
                cur.execute(
                    """
                    SELECT 1
                    FROM company_news_analyzed
                    WHERE company_name = %s
                      AND news_title = %s
                      AND news_date_time = %s
                    LIMIT 1
                    """,
                    (company_name, old_row["news_title"], old_row["news_date_time"]),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        DELETE FROM company_news_raw
                        WHERE company_name = %s
                          AND news_title = %s
                          AND news_date_time = %s
                        """,
                        (company_name, old_row["news_title"], old_row["news_date_time"]),
                    )
        conn.commit()


def refresh_company_news_if_needed(
    company_name: str,
    *,
    source_name: str = DEFAULT_SOURCE,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {
            "fetched_total": 0,
            "filtered_out": 0,
            "kept_after_filter": 0,
            "stored_count": 0,
            "elapsed_sec": 0.0,
        }
    ensure_company_profile(company_name)
    latest = _get_latest_news_date(company_name)
    end_date = datetime.now(timezone.utc).date()
    fallback_start = end_date - _days(7)
    if latest is None:
        start_date = fallback_start
    else:
        start_date = max(latest.date(), fallback_start)

    if start_date > end_date:
        start_date = end_date

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    items, analyzed, fetch_stats = _fetch_news_with_source(
        source_name,
        provider,
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
    )
    stored_count = 0
    if items:
        stored_count = len(items)
        _store_articles(
            _news_items_from_provider(
                company_name,
                items,
                end_date=end_date,
                analyzed=analyzed,
            ),
            llm_model=model,
        )
    return {
        "fetched_total": int(fetch_stats.get("fetched_total", 0)),
        "filtered_out": int(fetch_stats.get("filtered_out", 0)),
        "kept_after_filter": int(fetch_stats.get("kept_after_filter", 0)),
        "stored_count": stored_count,
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }


def refresh_company_news_for_range(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    source_name: str = DEFAULT_SOURCE,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {
            "fetched_total": 0,
            "filtered_out": 0,
            "kept_after_filter": 0,
            "stored_count": 0,
            "elapsed_sec": 0.0,
        }
    ensure_company_profile(company_name)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    items, analyzed, fetch_stats = _fetch_news_with_source(
        source_name,
        provider,
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
    )
    stored_count = 0
    if items:
        stored_count = len(items)
        _store_articles(
            _news_items_from_provider(
                company_name,
                items,
                end_date=end_date,
                analyzed=analyzed,
            ),
            llm_model=model,
        )
    return {
        "fetched_total": int(fetch_stats.get("fetched_total", 0)),
        "filtered_out": int(fetch_stats.get("filtered_out", 0)),
        "kept_after_filter": int(fetch_stats.get("kept_after_filter", 0)),
        "stored_count": stored_count,
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
    }




def _news_item_from_payload(
    company_name: str,
    item: Dict[str, Any],
    *,
    end_date: date,
    analyzed: bool,
) -> NewsArticle:
    news_date_time = _parse_date_time(item.get("news_date_time"), end_date=end_date)
    original_content = _as_text(item.get("original_content"))
    content = _extract_analyzed_content(item)
    if analyzed and not content:
        fallback_summary = item.get("summary") or original_content or ""
        content = {"summary": fallback_summary}
    return NewsArticle(
        company_name=company_name,
        news_date_time=news_date_time,
        news_title=str(item.get("news_title") or "Untitled"),
        original_content=original_content or _as_text(item.get("summary")),
        llm_analyzed_content=json.dumps(content) if analyzed else None,
        news_source_link=_as_text(item.get("news_source_link")),
        news_source=_as_text(item.get("news_source")),
        is_analyzed=analyzed,
    )


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


def _news_items_from_provider(
    company_name: str,
    items: List[Dict[str, Any]],
    *,
    end_date: date,
    analyzed: bool,
) -> List[NewsArticle]:
    return [
        _news_item_from_payload(
            company_name,
            item,
            end_date=end_date,
            analyzed=analyzed,
        )
        for item in items
    ]


def _fetch_news_with_source(
    source_name: str,
    provider,
    *,
    company_name: str,
    start_date: date,
    end_date: date,
) -> tuple[List[Dict[str, Any]], bool, Dict[str, int]]:
    # Single-stage pipeline: ask one analysis call to include keep/drop signal.
    if source_name == "openai":
        items = provider.fetch_news(
            company_name=company_name,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        tagged = _tag_source(items, "openai")
        return tagged, True, {
            "fetched_total": len(tagged),
            "filtered_out": 0,
            "kept_after_filter": len(tagged),
        }
    if source_name == "finnhub":
        ticker = _resolve_company_ticker(company_name) or company_name
        source = get_news_source("finnhub")
        logger.info("Calling Finnhub news: company=%s ticker=%s", company_name, ticker)
        raw_items = source.fetch_news(
            company_name=ticker,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        logger.info("Finnhub raw items: %d for %s", len(raw_items), company_name)
        filtered_items = _filter_finnhub_items_in_batches(
            provider=provider,
            company_name=company_name,
            items=raw_items,
            batch_size=FILTER_DAY_BATCH_SIZE,
        )
        logger.info(
            "Finnhub kept after filter: %d/%d for %s",
            len(filtered_items),
            len(raw_items),
            company_name,
        )
        if not filtered_items:
            return [], False, {
                "fetched_total": len(raw_items),
                "filtered_out": len(raw_items),
                "kept_after_filter": 0,
            }

        if len(filtered_items) > FINNHUB_AUTO_ANALYZE_LIMIT:
            logger.info(
                "Skipping auto-analysis for %s: %d filtered items > limit %d",
                company_name,
                len(filtered_items),
                FINNHUB_AUTO_ANALYZE_LIMIT,
            )
            tagged = _tag_source(filtered_items, "finnhub")
            return tagged, False, {
                "fetched_total": len(raw_items),
                "filtered_out": len(raw_items) - len(filtered_items),
                "kept_after_filter": len(filtered_items),
            }
        batch_size = 5
        analyzed_items: List[Dict[str, Any]] = []
        batches: List[List[Dict[str, Any]]] = [
            filtered_items[offset : offset + batch_size]
            for offset in range(0, len(filtered_items), batch_size)
        ]
        for batch_index, batch in enumerate(batches, start=1):
            logger.info(
                "Finnhub analyze batch start %d/%d (%d items) for %s",
                batch_index,
                len(batches),
                len(batch),
                company_name,
            )
            batch_result = provider.analyze_news_items(
                company_name=company_name,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                items=batch,
            )
            logger.info(
                "Finnhub analyze batch end %d/%d (%d items) for %s",
                batch_index,
                len(batches),
                len(batch_result),
                company_name,
            )
            analyzed_items.extend(batch_result)
        logger.info("Finnhub analyzed items: %d for %s", len(analyzed_items), company_name)
        tagged = _tag_source(analyzed_items, "finnhub")
        return tagged, True, {
            "fetched_total": len(raw_items),
            "filtered_out": len(raw_items) - len(filtered_items),
            "kept_after_filter": len(filtered_items),
        }
    raise ValueError(f"Unknown news source: {source_name}")


def _filter_finnhub_items_in_batches(
    *,
    provider,
    company_name: str,
    items: List[Dict[str, Any]],
    batch_size: int,
) -> List[Dict[str, Any]]:
    if not items:
        return []
    kept_items: List[Dict[str, Any]] = []
    total_batches = (len(items) + batch_size - 1) // batch_size
    for batch_index, offset in enumerate(range(0, len(items), batch_size), start=1):
        batch = items[offset : offset + batch_size]
        unique_titles = [
            {"news_title": title}
            for title in list(
                dict.fromkeys(str(item.get("news_title") or "").strip() for item in batch)
            )
            if title
        ]
        logger.info(
            "Finnhub filter batch start %d/%d (%d titles) for %s",
            batch_index,
            total_batches,
            len(unique_titles),
            company_name,
        )
        decisions = provider.filter_news_items(
            company_name=company_name,
            items=unique_titles,
        )
        drop_titles: set[str] = set()
        for decision in decisions:
            title_key = str(decision.get("news_title") or "").strip().lower()
            if not title_key:
                continue
            if _is_item_relevant(decision):
                continue
            drop_titles.add(title_key)
        batch_kept = [
            item
            for item in batch
            if str(item.get("news_title") or "").strip().lower() not in drop_titles
        ]
        kept_items.extend(batch_kept)
        logger.info(
            "Finnhub filter batch end %d/%d kept=%d dropped=%d for %s",
            batch_index,
            total_batches,
            len(batch_kept),
            len(batch) - len(batch_kept),
            company_name,
        )
    return kept_items


def _filter_company_news_range_raw(
    *,
    company_name: str,
    start_date: date,
    end_date: date,
    provider,
    llm_model: str,
) -> int:
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, news_title, news_date_time
                FROM company_news_raw
                WHERE company_name = %s
                  AND news_date_time >= %s
                  AND news_date_time < %s
                  AND COALESCE(is_filtered, FALSE) = FALSE
                ORDER BY news_date_time ASC, id ASC
                """,
                (company_name, start_dt, end_dt),
            )
            rows = cur.fetchall()
    if not rows:
        return 0
    title_to_rows: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        title = str(row["news_title"] or "").strip()
        if not title:
            continue
        title_to_rows.setdefault(title.lower(), []).append(row)
    unique_titles = [
        {"news_title": bucket[0]["news_title"]}
        for bucket in title_to_rows.values()
        if bucket and bucket[0].get("news_title")
    ]
    kept_ids: List[int] = []
    for offset in range(0, len(unique_titles), FILTER_DAY_BATCH_SIZE):
        batch = unique_titles[offset : offset + FILTER_DAY_BATCH_SIZE]
        decisions = provider.filter_news_items(company_name=company_name, items=batch)
        decision_map = {
            str(item.get("news_title") or "").strip().lower(): item
            for item in decisions
            if str(item.get("news_title") or "").strip()
        }
        for title_key, bucket in title_to_rows.items():
            if title_key not in {str(item.get("news_title") or "").strip().lower() for item in batch}:
                continue
            decision = decision_map.get(title_key) or {"keep_for_company": True}
            if _is_item_relevant(decision):
                kept_ids.extend(int(row["id"]) for row in bucket)
                continue
            for row in bucket:
                _delete_news_by_signature(
                    company_name,
                    row["news_title"],
                    row["news_date_time"],
                    archive=True,
                    drop_reason=_extract_drop_reason(decision),
                    llm_model=llm_model,
                    dropped_by="story_warmup_filter",
                )
    _mark_raw_news_filtered_by_ids(company_name, kept_ids)
    return len(kept_ids)


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


def _delete_raw_news_by_id(
    company_name: str,
    news_id: int,
    *,
    archive: bool = True,
    drop_reason: Optional[str] = None,
    llm_model: Optional[str] = None,
    dropped_by: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT news_title, news_date_time
                FROM company_news_raw
                WHERE company_name = %s
                  AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
            if not row:
                return
            _delete_news_by_signature_with_cursor(
                cur,
                company_name,
                row["news_title"],
                row["news_date_time"],
                archive=archive,
                drop_reason=drop_reason,
                llm_model=llm_model,
                dropped_by=dropped_by,
            )
        conn.commit()


def _mark_raw_news_filtered_by_id(company_name: str, news_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE company_news_raw
                SET is_filtered = TRUE
                WHERE company_name = %s
                  AND id = %s
                """,
                (company_name, news_id),
            )
        conn.commit()


def _mark_raw_news_filtered_by_ids(company_name: str, news_ids: List[int]) -> None:
    if not news_ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            for news_id in news_ids:
                cur.execute(
                    """
                    UPDATE company_news_raw
                    SET is_filtered = TRUE
                    WHERE company_name = %s
                      AND id = %s
                    """,
                    (company_name, int(news_id)),
                )
        conn.commit()


def _delete_news_by_signature(
    company_name: str,
    news_title: str,
    news_date_time: datetime,
    *,
    archive: bool = False,
    drop_reason: Optional[str] = None,
    llm_model: Optional[str] = None,
    dropped_by: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            _delete_news_by_signature_with_cursor(
                cur,
                company_name,
                news_title,
                news_date_time,
                archive=archive,
                drop_reason=drop_reason,
                llm_model=llm_model,
                dropped_by=dropped_by,
            )
        conn.commit()


def _delete_news_by_signature_with_cursor(
    cur,
    company_name: str,
    news_title: str,
    news_date_time: datetime,
    *,
    archive: bool = False,
    drop_reason: Optional[str] = None,
    llm_model: Optional[str] = None,
    dropped_by: Optional[str] = None,
) -> None:
    if archive:
        _archive_dropped_news_with_cursor(
            cur,
            company_name,
            news_title,
            news_date_time,
            drop_reason=drop_reason,
            llm_model=llm_model,
            dropped_by=dropped_by,
        )
    cur.execute(
        """
        DELETE FROM company_news_analyzed
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
        """,
        (company_name, news_title, news_date_time),
    )
    cur.execute(
        """
        DELETE FROM company_news_raw
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
        """,
        (company_name, news_title, news_date_time),
    )


def _archive_dropped_news_with_cursor(
    cur,
    company_name: str,
    news_title: str,
    news_date_time: datetime,
    *,
    drop_reason: Optional[str],
    llm_model: Optional[str],
    dropped_by: Optional[str],
) -> None:
    # Archive a full snapshot (raw + latest analyzed, when available) before deletion.
    cur.execute(
        """
        SELECT
            r.id AS raw_news_id,
            r.company_name,
            r.news_date_time,
            r.news_title,
            r.content AS raw_content,
            r.source AS raw_source,
            r.source_link AS raw_source_link,
            COALESCE(r.is_analyzed, FALSE) AS raw_is_analyzed,
            a.content AS analyzed_content,
            a.source AS analyzed_source,
            a.source_link AS analyzed_source_link,
            a.llm_model AS analyzed_llm_model
        FROM company_news_raw AS r
        LEFT JOIN LATERAL (
            SELECT
                aa.content,
                aa.source,
                aa.source_link,
                aa.llm_model
            FROM company_news_analyzed AS aa
            WHERE aa.company_name = r.company_name
              AND aa.news_title = r.news_title
              AND aa.news_date_time = r.news_date_time
            ORDER BY
                CASE WHEN %s IS NOT NULL AND aa.llm_model = %s THEN 0 ELSE 1 END,
                aa.id DESC
            LIMIT 1
        ) AS a ON TRUE
        WHERE r.company_name = %s
          AND r.news_title = %s
          AND r.news_date_time = %s
        LIMIT 1
        """,
        (llm_model, llm_model, company_name, news_title, news_date_time),
    )
    row = cur.fetchone()
    if not row:
        return
    cur.execute(
        """
        INSERT INTO company_news_dropped (
            company_name,
            raw_news_id,
            news_date_time,
            news_title,
            raw_content,
            raw_source,
            raw_source_link,
            raw_is_analyzed,
            analyzed_content,
            analyzed_source,
            analyzed_source_link,
            analyzed_llm_model,
            drop_reason,
            dropped_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            row["company_name"],
            row["raw_news_id"],
            row["news_date_time"],
            row["news_title"],
            row["raw_content"],
            row["raw_source"],
            row["raw_source_link"],
            bool(row["raw_is_analyzed"]),
            row["analyzed_content"],
            row["analyzed_source"],
            row["analyzed_source_link"],
            row["analyzed_llm_model"],
            _as_text(drop_reason),
            _as_text(dropped_by),
        ),
    )


def _extract_drop_reason(item: Dict[str, Any]) -> Optional[str]:
    for key in ("drop_reason", "reason", "filter_reason"):
        value = _as_text(item.get(key))
        if value:
            return value
    return None


def _tag_source(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    for item in items:
        item["news_source"] = source
    return items


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


def _get_latest_news_date(company_name: str) -> Optional[datetime]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT news_date_time
                FROM company_news_raw
                WHERE company_name = %s
                ORDER BY news_date_time DESC
                LIMIT 1
                """,
                (company_name,),
            )
            row = cur.fetchone()
            return row["news_date_time"] if row else None


def _store_articles(
    articles: Iterable[NewsArticle],
    *,
    llm_model: str,
    output_language: str = "en",
) -> None:
    _ensure_news_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            for article in articles:
                cur.execute(
                    """
                    INSERT INTO company_news_raw (
                        company_name,
                        news_date_time,
                        news_title,
                        content,
                        source,
                        source_link,
                        is_analyzed,
                        is_filtered
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_name, news_title, news_date_time)
                    DO UPDATE SET
                        content = COALESCE(EXCLUDED.content, company_news_raw.content),
                        source = COALESCE(EXCLUDED.source, company_news_raw.source),
                        source_link = COALESCE(EXCLUDED.source_link, company_news_raw.source_link),
                        is_analyzed = company_news_raw.is_analyzed OR EXCLUDED.is_analyzed,
                        is_filtered = company_news_raw.is_filtered OR EXCLUDED.is_filtered
                    """,
                    (
                        article.company_name,
                        article.news_date_time,
                        article.news_title,
                        article.original_content,
                        article.news_source,
                        article.news_source_link,
                        bool(article.is_analyzed),
                        False,
                    ),
                )
                if not article.llm_analyzed_content:
                    continue
                if _exists_analyzed_article(
                    cur,
                    article,
                    llm_model=llm_model,
                    output_language=output_language,
                ):
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_NEWS_ANALYZED} (
                        company_name,
                        news_date_time,
                        news_title,
                        content,
                        source,
                        source_link,
                        llm_model,
                        {COL_OUTPUT_LANGUAGE}
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        article.company_name,
                        article.news_date_time,
                        article.news_title,
                        article.llm_analyzed_content,
                        article.news_source,
                        article.news_source_link,
                        llm_model,
                        output_language,
                    ),
                )
                cur.execute(
                    """
                    UPDATE company_news_raw
                    SET is_analyzed = TRUE
                    WHERE company_name = %s
                      AND news_title = %s
                      AND news_date_time = %s
                    """,
                    (article.company_name, article.news_title, article.news_date_time),
                )
        conn.commit()


def _exists_raw_article(cur, article: NewsArticle) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM company_news_raw
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
        """,
        (article.company_name, article.news_title, article.news_date_time),
    )
    return cur.fetchone() is not None


def _exists_analyzed_article(
    cur,
    article: NewsArticle,
    *,
    llm_model: str,
    output_language: str,
) -> bool:
    cur.execute(
        f"""
        SELECT 1
        FROM {TBL_COMPANY_NEWS_ANALYZED}
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
          AND llm_model = %s
          AND {COL_OUTPUT_LANGUAGE} = %s
        """,
        (
            article.company_name,
            article.news_title,
            article.news_date_time,
            llm_model,
            output_language,
        ),
    )
    return cur.fetchone() is not None


def _store_weekly_report(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    report_payload: Optional[Dict[str, Any]],
) -> None:
    if not report_payload:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_report (company_name, beginning_date, end_date, content)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (company_name, beginning_date, end_date)
                DO UPDATE SET content = EXCLUDED.content, created_at = NOW()
                """,
                (company_name, start_date, end_date, json.dumps(report_payload)),
            )
        conn.commit()


def _upsert_company_daily_report(
    *,
    company_name: str,
    report_date: date,
    provider: str,
    model: str,
    prompt_style: str,
    input_payload: Dict[str, Any],
    output_text: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM company_news_daily_report
                WHERE company_name = %s
                  AND report_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (company_name, report_date, provider, prompt_style),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE company_news_daily_report
                    SET model = %s,
                        input_payload = %s,
                        output_text = %s,
                        created_at = NOW()
                    WHERE id = %s
                    """,
                    (model, json.dumps(input_payload), output_text, existing["id"]),
                )
                cur.execute(
                    """
                    DELETE FROM company_news_daily_report
                    WHERE company_name = %s
                      AND report_date = %s
                      AND provider = %s
                      AND prompt_style = %s
                      AND id <> %s
                    """,
                    (company_name, report_date, provider, prompt_style, existing["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO company_news_daily_report (
                        company_name,
                        report_date,
                        provider,
                        model,
                        prompt_style,
                        input_payload,
                        output_text
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        company_name,
                        report_date,
                        provider,
                        model,
                        prompt_style,
                        json.dumps(input_payload),
                        output_text,
                    ),
                )
        conn.commit()


def _upsert_company_status_snapshot(
    *,
    company_name: str,
    as_of_date: date,
    window_start_date: date,
    window_end_date: date,
    provider: str,
    model: str,
    prompt_style: str,
    input_payload: Dict[str, Any],
    output_json: Dict[str, Any],
    output_text: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_status_snapshot (
                    company_name,
                    as_of_date,
                    window_start_date,
                    window_end_date,
                    provider,
                    model,
                    prompt_style,
                    input_payload,
                    output_json,
                    output_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    company_name,
                    as_of_date,
                    window_start_date,
                    window_end_date,
                    provider,
                    model,
                    prompt_style,
                    json.dumps(input_payload),
                    json.dumps(output_json, ensure_ascii=False),
                    output_text,
                ),
            )
        conn.commit()


def _insert_company_price_intelligence_run(
    *,
    company_name: str,
    as_of_date: date,
    provider: str,
    model: str,
    output_language: str,
    context_window_days: int,
    focus_window_days: int,
    input_payload: Dict[str, Any],
    output_json: Dict[str, Any],
    output_text: str,
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_PRICE_INTELLIGENCE_RUN} (
                    company_name,
                    as_of_date,
                    provider,
                    model,
                    {COL_OUTPUT_LANGUAGE},
                    context_window_days,
                    focus_window_days,
                    input_payload,
                    output_json,
                    output_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    company_name,
                    as_of_date,
                    provider,
                    model,
                    output_language,
                    int(context_window_days),
                    int(focus_window_days),
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(output_json, ensure_ascii=False),
                    output_text,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return int(row["id"])


def _persist_story_refresh(
    *,
    company_name: str,
    as_of_date: date,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
    raw_output: str,
    stories: List[Dict[str, Any]],
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            active_keys: List[str] = []
            for item in stories:
                story_key = str(item["story_key"]).strip()
                active_keys.append(story_key)
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_STORY_STATE} (
                        company_name,
                        {COL_STORY_KEY},
                        story_title,
                        story_summary,
                        importance_rank,
                        story_status,
                        priority,
                        confidence,
                        happened_text,
                        happening_text,
                        next_text,
                        timeline_json,
                        future_impact_json,
                        open_questions_json,
                        evidence_json,
                        change_log_json,
                        last_event_at,
                        provider,
                        model,
                        prompt_style,
                        {COL_OUTPUT_LANGUAGE},
                        is_active,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW(), %s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (company_name, {COL_STORY_KEY}, provider, prompt_style, {COL_OUTPUT_LANGUAGE})
                    DO UPDATE SET
                        story_title = EXCLUDED.story_title,
                        story_summary = EXCLUDED.story_summary,
                        importance_rank = EXCLUDED.importance_rank,
                        story_status = EXCLUDED.story_status,
                        priority = EXCLUDED.priority,
                        confidence = EXCLUDED.confidence,
                        happened_text = EXCLUDED.happened_text,
                        happening_text = EXCLUDED.happening_text,
                        next_text = EXCLUDED.next_text,
                        timeline_json = EXCLUDED.timeline_json,
                        future_impact_json = EXCLUDED.future_impact_json,
                        open_questions_json = EXCLUDED.open_questions_json,
                        evidence_json = EXCLUDED.evidence_json,
                        change_log_json = EXCLUDED.change_log_json,
                        last_event_at = NOW(),
                        model = EXCLUDED.model,
                        is_active = TRUE,
                        updated_at = NOW()
                    """,
                    (
                        company_name,
                        story_key,
                        item["story_title"],
                        item.get("story_summary") or "",
                        int(item["importance_rank"]),
                        item["story_status"],
                        item.get("priority") or "normal",
                        float(item["confidence"]),
                        item["happened_text"],
                        item["happening_text"],
                        item["next_text"],
                        json.dumps(item.get("timeline_items") or [], ensure_ascii=False),
                        json.dumps(item.get("future_and_impact") or [], ensure_ascii=False),
                        json.dumps(item.get("open_questions") or [], ensure_ascii=False),
                        json.dumps(item.get("evidence") or [], ensure_ascii=False),
                        json.dumps(item.get("change_log") or [], ensure_ascii=False),
                        provider_name,
                        model,
                        prompt_style,
                        output_language,
                    ),
                )
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_STORY_UPDATE} (
                        company_name,
                        {COL_STORY_KEY},
                        as_of_date,
                        provider,
                        model,
                        prompt_style,
                        {COL_OUTPUT_LANGUAGE},
                        input_payload,
                        output_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        company_name,
                        story_key,
                        as_of_date,
                        provider_name,
                        model,
                        prompt_style,
                        output_language,
                        json.dumps(input_payload, ensure_ascii=False),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )

            if active_keys:
                cur.execute(
                    f"""
                    UPDATE {TBL_COMPANY_STORY_STATE}
                    SET is_active = FALSE,
                        updated_at = NOW()
                    WHERE company_name = %s
                      AND provider = %s
                      AND prompt_style = %s
                      AND {COL_OUTPUT_LANGUAGE} = %s
                      AND {COL_STORY_KEY} <> ALL(%s)
                    """,
                    (
                        company_name,
                        provider_name,
                        prompt_style,
                        output_language,
                        active_keys,
                    ),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {TBL_COMPANY_STORY_STATE}
                    SET is_active = FALSE,
                        updated_at = NOW()
                    WHERE company_name = %s
                      AND provider = %s
                      AND prompt_style = %s
                      AND {COL_OUTPUT_LANGUAGE} = %s
                    """,
                    (company_name, provider_name, prompt_style, output_language),
                )
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_STORY_UPDATE} (
                    company_name,
                    {COL_STORY_KEY},
                    as_of_date,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload,
                    output_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    company_name,
                    "__refresh__",
                    as_of_date,
                    provider_name,
                    model,
                    prompt_style,
                    output_language,
                    json.dumps(input_payload, ensure_ascii=False),
                    raw_output,
                ),
            )
        conn.commit()


def _insert_story_qa(
    *,
    company_name: str,
    story_key: str,
    question: str,
    answer: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_STORY_QA} (
                    company_name,
                    {COL_STORY_KEY},
                    question,
                    answer,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    question,
                    answer,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload,
                    created_at
                """,
                (
                    company_name,
                    story_key,
                    question,
                    answer,
                    provider_name,
                    model,
                    prompt_style,
                    output_language,
                    json.dumps(input_payload, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "story_key": row[COL_STORY_KEY],
        "question": row["question"] or "",
        "answer": row["answer"] or "",
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "input_payload": row["input_payload"] or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_company_story_qa_row(
    company_name: str,
    *,
    story_key: str,
    qa_id: int,
) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    company_name,
                    {COL_STORY_KEY},
                    question,
                    answer,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    input_payload,
                    created_at
                FROM {TBL_COMPANY_STORY_QA}
                WHERE company_name = %s
                  AND {COL_STORY_KEY} = %s
                  AND id = %s
                LIMIT 1
                """,
                (company_name, story_key, qa_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "story_key": row[COL_STORY_KEY],
        "question": row["question"] or "",
        "answer": row["answer"] or "",
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "input_payload": row["input_payload"] or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _build_company_daily_report_input_items(
    company_name: str,
    *,
    target_date: date,
    llm_model: str = DEFAULT_MODEL,
) -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(
        company_name,
        start_date=target_date,
        end_date=target_date,
        llm_model=llm_model,
    )
    items: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, datetime]] = set()
    for article in articles:
        key = (article.news_title, article.news_date_time)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        content = _decode_llm_content(article.llm_analyzed_content, article.original_content)
        items.append(
            {
                "news_date_time": article.news_date_time.isoformat(),
                "news_title": article.news_title,
                "news_source": article.news_source,
                "news_source_link": article.news_source_link,
                "original_content": article.original_content,
                "analyzed_content": content if article.llm_analyzed_content else None,
                "is_analyzed": bool(article.is_analyzed),
            }
        )
    return items




def _build_weekly_report_input_items(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    llm_model: str,
    provider_name: str,
) -> List[Dict[str, Any]]:
    all_daily_reports = get_company_daily_reports_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style="simple",
    )
    daily_reports = all_daily_reports[:PRICE_ANALYSIS_REPORT_LIMIT]
    if not daily_reports:
        return []
    items: List[Dict[str, Any]] = []
    for report in sorted(daily_reports, key=lambda x: x["report_date"]):
        items.append(
            {
                "news_title": f"Daily report for {company_name}",
                "news_date_time": report["report_date"],
                "news_source": "company_daily_report",
                "news_source_link": None,
                "summary": report["output_text"],
                "facts": [],
                "viewpoint": [],
                "reasoning": [],
                "uncertainties": [],
                "short_term_impact": [],
                "long_term_impact": [],
                "priced_in": [],
                "insider_signals": [],
                "trends": [],
                "sentiment": [],
            }
        )
    return items


def _build_monthly_report_input_items(
    company_name: str,
    *,
    month_start: date,
    month_end: date,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current_day = month_start
    while current_day <= month_end:
        if current_day.weekday() == 4:
            week_start = current_day - timedelta(days=6)
            report = get_news_report(
                company_name,
                beginning_date=week_start,
                end_date=current_day,
            )
            if report:
                items.append(
                    {
                        "week_start": week_start.isoformat(),
                        "week_end": current_day.isoformat(),
                        "summary": _render_period_report_as_text(report),
                        "report": report,
                    }
                )
        current_day += timedelta(days=1)
    return items


def _render_period_report_as_text(report: Dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return ""
    parts: List[str] = []
    for field, _ in ANALYSIS_FIELDS:
        values = report.get(field)
        if not isinstance(values, list) or not values:
            continue
        bullets = [str(item).strip() for item in values if str(item).strip()]
        if not bullets:
            continue
        parts.append(f"{field}: " + " | ".join(bullets))
    return "\n".join(parts)


def _normalize_structured_period_report(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    for field, _ in ANALYSIS_FIELDS:
        raw_items = payload.get(field)
        if not isinstance(raw_items, list):
            normalized[field] = []
            continue
        normalized[field] = [str(item).strip() for item in raw_items if str(item).strip()]
    return normalized


def _build_company_monthly_report_prompt(
    company_name: str,
    *,
    month_start: date,
    month_end: date,
    weekly_reports: List[Dict[str, Any]],
    output_language: str,
) -> str:
    section_lines = "\n".join(f"- {field}" for field, _ in ANALYSIS_FIELDS)
    return (
        f"You are compiling a monthly report for {company_name} covering {month_start.isoformat()} to {month_end.isoformat()}.\n"
        "Use only the provided weekly reports as inputs.\n"
        "Synthesize the month coherently, remove repetition across weeks, and preserve the most important developments.\n"
        f"{_build_output_language_line(output_language)}"
        "Return a JSON object where each section below is present, and each value is an array of concise bullet points:\n"
        f"{section_lines}\n"
        "Weekly reports JSON:\n"
        f"{json.dumps(weekly_reports, ensure_ascii=False, indent=2)}\n"
    )


def _build_company_price_intelligence_input(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    provider_name: str,
    output_language: str,
) -> Dict[str, Any]:
    price_context = _build_company_status_price_context(company_name, start_date=start_date, end_date=end_date)
    input_coverage = {
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "window_days": int((end_date - start_date).days) + 1,
        "price_point_count": int(price_context.get("point_count") or 0),
        "recent_point_count": len(price_context.get("recent_points") or []),
        "move_analysis_count": len(price_context.get("move_analyses") or []),
        "input_item_count": int(price_context.get("point_count") or 0),
    }
    return {
        "price_context": price_context,
        "input_coverage": input_coverage,
        "output_language": output_language,
    }


def _build_company_quick_price_intelligence_input(
    company_name: str,
    *,
    context_start: date,
    focus_start: date,
    end_date: date,
    provider_name: str,
    output_language: str,
) -> Dict[str, Any]:
    all_daily_reports = get_company_daily_reports_for_range(
        company_name,
        start_date=context_start,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style="simple",
    )
    daily_reports = all_daily_reports[:PRICE_ANALYSIS_REPORT_LIMIT]
    daily_report_dates = {
        str(item.get("report_date") or "").strip()
        for item in daily_reports
        if str(item.get("report_date") or "").strip()
    }
    raw_news_fallback = _build_company_status_raw_news_fallback(
        company_name,
        start_date=focus_start,
        end_date=end_date,
        covered_dates=daily_report_dates,
    )[:PRICE_ANALYSIS_RAW_FALLBACK_LIMIT]
    price_context = _build_company_status_price_context(company_name, start_date=context_start, end_date=end_date)
    focus_price_context = _build_company_status_price_context(company_name, start_date=focus_start, end_date=end_date)
    technical_focus_points = (focus_price_context.get("recent_points") or [])[-10:]
    market_stories = _build_company_status_market_story_context(limit=6)
    market_daily_summaries = _build_company_status_market_daily_summary_context(
        start_date=focus_start,
        end_date=end_date,
    )[:PRICE_ANALYSIS_MARKET_SUMMARY_LIMIT]
    latest_price = price_context.get("latest_close")
    coverage = {
        "context_window_start": context_start.isoformat(),
        "focus_window_start": focus_start.isoformat(),
        "window_end": end_date.isoformat(),
        "daily_report_count": len(daily_reports),
        "raw_news_fallback_count": len(raw_news_fallback),
        "market_story_count": len(market_stories),
        "market_summary_count": len(market_daily_summaries),
        "price_point_count": int(price_context.get("point_count") or 0),
        "input_item_count": len(daily_reports) + len(raw_news_fallback) + len(market_stories) + len(market_daily_summaries) + len(technical_focus_points),
    }
    return {
        "daily_reports": daily_reports,
        "raw_news_fallback": raw_news_fallback,
        "price_context": price_context,
        "focus_price_context": focus_price_context,
        "technical_focus_points": technical_focus_points,
        "market_stories": market_stories,
        "market_daily_summaries": market_daily_summaries,
        "latest_price": latest_price,
        "input_coverage": coverage,
        "output_language": output_language,
    }


def _build_company_status_input_coverage(
    *,
    daily_reports: List[Dict[str, Any]],
    raw_news_fallback: List[Dict[str, Any]],
    start_date: date,
    end_date: date,
    market_daily_summaries: List[Dict[str, Any]],
    price_context: Dict[str, Any],
) -> Dict[str, Any]:
    report_dates = {
        str(item.get("report_date") or "").strip()
        for item in daily_reports
        if str(item.get("report_date") or "").strip()
    }
    total_days = max(1, (end_date - start_date).days + 1)
    return {
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "window_days": total_days,
        "daily_report_count": len(daily_reports),
        "daily_report_coverage_days": len(report_dates),
        "raw_news_fallback_count": len(raw_news_fallback),
        "market_summary_count": len(market_daily_summaries),
        "price_point_count": int(price_context.get("point_count") or 0),
    }


def _build_company_status_raw_news_fallback(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    covered_dates: set[str],
) -> List[Dict[str, Any]]:
    fallback: List[Dict[str, Any]] = []
    for article in get_company_news_for_range(company_name, start_date=start_date, end_date=end_date)[:80]:
        article_date = article.news_date_time.date().isoformat()
        if article_date in covered_dates:
            continue
        fallback.append(
            {
                "news_date_time": article.news_date_time.isoformat(),
                "news_title": article.news_title,
                "news_source": article.news_source,
                "news_source_link": article.news_source_link,
                "summary": _decode_llm_content(article.llm_analyzed_content, article.original_content).get("summary"),
            }
        )
    return fallback


def _build_company_status_price_context(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, trade_date, open, high, low, close, adj_close, volume
                FROM company_price_daily
                WHERE company_name = %s
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY trade_date ASC
                """,
                (company_name, start_date, end_date),
            )
            rows = cur.fetchall()
    if not rows:
        return {}
    closes = [float(row["close"] if row["close"] is not None else row["adj_close"]) for row in rows if row["close"] is not None or row["adj_close"] is not None]
    if not closes:
        return {}
    latest_close = closes[-1]
    first_close = closes[0]
    highs = [float(row["high"]) for row in rows if row["high"] is not None]
    lows = [float(row["low"]) for row in rows if row["low"] is not None]
    volumes = [int(row["volume"]) for row in rows if row["volume"] is not None]

    def _pct_change(points_back: int) -> Optional[float]:
        if len(closes) <= points_back:
            return None
        base = closes[-(points_back + 1)]
        if base in (None, 0):
            return None
        return round(((latest_close - base) / base) * 100.0, 2)

    returns = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        curr = closes[idx]
        if prev:
            returns.append((curr - prev) / prev)
    volatility = round((math.sqrt(sum(r * r for r in returns) / len(returns)) * 100.0), 2) if returns else None
    window_high = max(highs) if highs else max(closes)
    window_low = min(lows) if lows else min(closes)
    recent_20 = closes[-20:]
    recent_50 = closes[-50:]
    recent_200 = closes[-200:]
    avg_volume_20 = round(sum(volumes[-20:]) / len(volumes[-20:])) if volumes[-20:] else None

    move_analyses = _build_company_status_price_move_context(company_name, ticker=str(rows[-1]["ticker"] or "").strip().upper())
    return {
        "ticker": str(rows[-1]["ticker"] or "").strip().upper(),
        "point_count": len(rows),
        "window_start": rows[0]["trade_date"].isoformat(),
        "window_end": rows[-1]["trade_date"].isoformat(),
        "latest_close": round(latest_close, 4),
        "window_high": round(window_high, 4) if window_high is not None else None,
        "window_low": round(window_low, 4) if window_low is not None else None,
        "window_change_pct": round(((latest_close - first_close) / first_close) * 100.0, 2) if first_close else None,
        "return_5d_pct": _pct_change(5),
        "return_20d_pct": _pct_change(20),
        "return_60d_pct": _pct_change(60),
        "distance_to_window_high_pct": round(((latest_close - window_high) / window_high) * 100.0, 2) if window_high else None,
        "distance_to_window_low_pct": round(((latest_close - window_low) / window_low) * 100.0, 2) if window_low else None,
        "ma_20": round(sum(recent_20) / len(recent_20), 4) if recent_20 else None,
        "ma_50": round(sum(recent_50) / len(recent_50), 4) if recent_50 else None,
        "ma_200": round(sum(recent_200) / len(recent_200), 4) if recent_200 else None,
        "realized_volatility_pct": volatility,
        "latest_volume": volumes[-1] if volumes else None,
        "avg_volume_20": avg_volume_20,
        "recent_points": [
            {
                "trade_date": row["trade_date"].isoformat(),
                "close": float(row["close"] if row["close"] is not None else row["adj_close"]) if row["close"] is not None or row["adj_close"] is not None else None,
                "high": float(row["high"]) if row["high"] is not None else None,
                "low": float(row["low"]) if row["low"] is not None else None,
                "volume": int(row["volume"]) if row["volume"] is not None else None,
            }
            for row in rows[-10:]
        ],
        "move_analyses": move_analyses,
    }


def _build_company_status_price_move_context(company_name: str, *, ticker: str) -> List[Dict[str, Any]]:
    if not ticker:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {COL_RANGE_KEY}, {COL_POINT_DATE_TIME}, output_text, updated_at
                FROM {TBL_COMPANY_PRICE_MOVE_ANALYSIS}
                WHERE company_name = %s
                  AND ticker = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 6
                """,
                (company_name, ticker),
            )
            rows = cur.fetchall()
    return [
        {
            "range_key": row[COL_RANGE_KEY],
            "point_date_time": row[COL_POINT_DATE_TIME].isoformat() if row[COL_POINT_DATE_TIME] else None,
            "output_text": row["output_text"] or "",
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


def _build_company_status_market_story_context(*, limit: int = 6) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT story_title, story_summary, priority, importance_rank, updated_at
                FROM market_story_state
                WHERE is_active = TRUE
                ORDER BY importance_rank ASC, updated_at DESC
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            rows = cur.fetchall()
    return [
        {
            "story_title": row["story_title"],
            "story_summary": row["story_summary"] or "",
            "priority": row["priority"] or "normal",
            "importance_rank": int(row["importance_rank"] or 999),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


def _build_company_status_market_daily_summary_context(
    *,
    start_date: date,
    end_date: date,
) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary_date, output_text, provider, model, prompt_style, created_at
                FROM market_news_daily_summary
                WHERE summary_date >= %s
                  AND summary_date <= %s
                ORDER BY summary_date DESC, created_at DESC
                LIMIT 10
                """,
                (start_date, end_date),
            )
            rows = cur.fetchall()
    return [
        {
            "summary_date": row["summary_date"].isoformat(),
            "output_text": row["output_text"] or "",
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]


def _build_company_status_macro_context(*, as_of_date: date) -> Dict[str, Any]:
    recent_events: List[Dict[str, Any]] = []
    upcoming_events: List[Dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_name, event_date_time, category, importance, impact_summary, country, event_code
                FROM market_macro_event
                WHERE event_date_time >= %s
                  AND event_date_time < %s
                ORDER BY event_date_time ASC
                LIMIT 12
                """,
                (
                    datetime.combine(as_of_date - timedelta(days=7), time.min, tzinfo=timezone.utc),
                    datetime.combine(as_of_date + timedelta(days=14), time.min, tzinfo=timezone.utc),
                ),
            )
            rows = cur.fetchall()
    for row in rows:
        entry = {
            "event_name": row["event_name"],
            "event_date_time": row["event_date_time"].isoformat() if row["event_date_time"] else None,
            "category": row["category"] or "",
            "importance": row["importance"] or "",
            "impact_summary": row["impact_summary"] or "",
            "country": row["country"] or "",
            "event_code": row["event_code"] or "",
        }
        if row["event_date_time"] and row["event_date_time"].date() < as_of_date:
            recent_events.append(entry)
        else:
            upcoming_events.append(entry)

    market_snapshot = _build_company_status_market_snapshot_context(as_of_date=as_of_date)
    return {
        "recent_macro_events": recent_events[:6],
        "upcoming_macro_events": upcoming_events[:6],
        "market_price_snapshot": market_snapshot,
    }


def _build_company_status_market_snapshot_context(*, as_of_date: date) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {COL_PAYLOAD}
                FROM {TBL_MARKET_PRICE_DAILY_SNAPSHOT}
                WHERE {COL_SNAPSHOT_DATE} <= %s
                ORDER BY {COL_SNAPSHOT_DATE} DESC
                LIMIT 1
                """,
                (as_of_date,),
            )
            row = cur.fetchone()
    if not row or not isinstance(row[COL_PAYLOAD], str):
        return {}
    try:
        payload = json.loads(row[COL_PAYLOAD])
    except json.JSONDecodeError:
        return {}
    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, list):
        return {}
    return {
        "snapshot_date": payload.get("date"),
        "price_date": payload.get("price_date"),
        "sections": sections[:6],
    }






def _normalize_company_quick_price_intelligence_payload(
    payload: Dict[str, Any],
    *,
    as_of_date: date,
    current_price: Any,
    previous_run: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    def _to_text(value: Any) -> str:
        return str(value or "").strip()

    def _to_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = _to_text(value)
        return [text] if text else []

    def _to_number(value: Any, fallback: Optional[float] = None) -> Optional[float]:
        try:
            if value is None or value == "":
                return fallback
            return round(float(value), 4)
        except Exception:
            return fallback

    def _normalize_zone(value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        low = _to_number(data.get("low"), _to_number(current_price))
        mid = _to_number(data.get("mid"), low)
        high = _to_number(data.get("high"), mid)
        return {
            "low": low,
            "mid": mid,
            "high": high,
            "basis": _to_text(data.get("basis")),
        }

    def _normalize_method(value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        return {
            "summary": _to_text(data.get("summary")),
            "fair_price_read": _to_text(data.get("fair_price_read")),
            "signals": _to_list(data.get("signals")),
            "risks": _to_list(data.get("risks")),
        }

    normalized = {
        "as_of_date": as_of_date.isoformat(),
        "current_price": _to_number(payload.get("current_price"), _to_number(current_price)),
        "fair_price_zone": _normalize_zone(payload.get("fair_price_zone")),
        "price_position": payload.get("price_position") if isinstance(payload.get("price_position"), dict) else {
            "label": "near_fair",
            "explanation": "",
        },
        "bottom_line": _to_text(payload.get("bottom_line")),
        "technical_view": _normalize_method(payload.get("technical_view")),
        "fundamental_market_view": _normalize_method(payload.get("fundamental_market_view")),
        "synthesis_view": {
            "summary": _to_text((payload.get("synthesis_view") or {}).get("summary") if isinstance(payload.get("synthesis_view"), dict) else ""),
            "dominant_method": _to_text((payload.get("synthesis_view") or {}).get("dominant_method") if isinstance(payload.get("synthesis_view"), dict) else ""),
            "triggers": _to_list((payload.get("synthesis_view") or {}).get("triggers") if isinstance(payload.get("synthesis_view"), dict) else []),
            "invalidations": _to_list((payload.get("synthesis_view") or {}).get("invalidations") if isinstance(payload.get("synthesis_view"), dict) else []),
        },
    }
    normalized["output_markdown"] = _render_company_quick_price_intelligence_markdown(normalized)
    return normalized


def _render_company_quick_price_intelligence_markdown(payload: Dict[str, Any]) -> str:
    def _bullet(items: List[str]) -> str:
        rows = [f"- {item}" for item in items if str(item).strip()]
        return "\n".join(rows) if rows else "- —"

    zone = payload.get("fair_price_zone") or {}
    position = payload.get("price_position") or {}
    synthesis = payload.get("synthesis_view") or {}
    return (
        "## Price Intelligence\n"
        f"- Current Price: {payload.get('current_price') or '—'}\n"
        f"- Fair Price Zone: {zone.get('low') or '—'} / {zone.get('mid') or '—'} / {zone.get('high') or '—'}\n"
        f"- Price Position: {position.get('label') or '—'} · {position.get('explanation') or '—'}\n"
        f"- Bottom Line: {payload.get('bottom_line') or '—'}\n"
        "\n### Technical View\n"
        f"- Summary: {(payload.get('technical_view') or {}).get('summary') or '—'}\n"
        f"- Fair Price Read: {(payload.get('technical_view') or {}).get('fair_price_read') or '—'}\n"
        f"- Signals:\n{_bullet((payload.get('technical_view') or {}).get('signals') or [])}\n"
        f"- Risks:\n{_bullet((payload.get('technical_view') or {}).get('risks') or [])}\n"
        "\n### Fundamental / Market View\n"
        f"- Summary: {(payload.get('fundamental_market_view') or {}).get('summary') or '—'}\n"
        f"- Fair Price Read: {(payload.get('fundamental_market_view') or {}).get('fair_price_read') or '—'}\n"
        f"- Signals:\n{_bullet((payload.get('fundamental_market_view') or {}).get('signals') or [])}\n"
        f"- Risks:\n{_bullet((payload.get('fundamental_market_view') or {}).get('risks') or [])}\n"
        "\n### Synthesis\n"
        f"- Summary: {synthesis.get('summary') or '—'}\n"
        f"- Dominant Method: {synthesis.get('dominant_method') or '—'}\n"
        f"- Triggers:\n{_bullet(synthesis.get('triggers') or [])}\n"
        f"- Invalidations:\n{_bullet(synthesis.get('invalidations') or [])}\n"
    )


def _normalize_company_status_payload(payload: Dict[str, Any], *, as_of_date: date) -> Dict[str, Any]:
    def _to_text(value: Any) -> str:
        return str(value or "").strip()

    def _to_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    def _normalize_horizon(name: str, value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        confidence = data.get("confidence")
        try:
            confidence_value = max(0.0, min(float(confidence), 1.0))
        except Exception:
            confidence_value = 0.5
        return {
            "horizon": name,
            "confidence": round(confidence_value, 2),
            "price_judgment": _to_text(data.get("price_judgment")),
            "rationale": _to_list(data.get("rationale")),
            "watch_signals": _to_list(data.get("watch_signals")),
            "invalidations": _to_list(data.get("invalidations")),
        }

    normalized = {
        "as_of_date": as_of_date.isoformat(),
        "company_summary": _to_text(payload.get("company_summary") or payload.get("technical_summary")),
        "technical_summary": _to_text(payload.get("technical_summary")),
        "dominant_personality": payload.get("dominant_personality") if isinstance(payload.get("dominant_personality"), dict) else {
            "label": "",
            "dominant_horizon": "balanced",
            "why": "",
        },
        "price_position_summary": _to_text(payload.get("price_position_summary")),
        "market_regime_context": _to_text(payload.get("market_regime_context")),
        "decision_brief": payload.get("decision_brief") if isinstance(payload.get("decision_brief"), dict) else {},
        "research_memo": payload.get("research_memo") if isinstance(payload.get("research_memo"), dict) else {},
        "trader_view": payload.get("trader_view") if isinstance(payload.get("trader_view"), dict) else {},
        "volume_participation": _to_text(payload.get("volume_participation")),
        "volatility_range_context": _to_text(payload.get("volatility_range_context")),
        "short_horizon_view": _normalize_horizon("short", payload.get("short_horizon_view")),
        "medium_horizon_view": _normalize_horizon("medium", payload.get("medium_horizon_view")),
        "long_horizon_view": _normalize_horizon("long", payload.get("long_horizon_view")),
        "signals_to_watch": _to_list(payload.get("signals_to_watch")),
        "risk_map": _to_list(payload.get("risk_map")),
        "uncertainty_map": _to_list(payload.get("uncertainty_map")),
        "trading_style_fit": _to_list(payload.get("trading_style_fit")),
        "supporting_reasoning": _to_list(payload.get("supporting_reasoning")),
    }
    markdown = _to_text(payload.get("output_markdown"))
    if not markdown:
        markdown = _render_company_status_markdown(normalized)
    normalized["output_markdown"] = markdown
    return normalized


def _render_company_status_markdown(payload: Dict[str, Any]) -> str:
    def _bullet_block(items: List[str]) -> str:
        rows = [f"- {item}" for item in items if str(item).strip()]
        return "\n".join(rows) if rows else "- —"

    def _render_horizon(section: Dict[str, Any]) -> str:
        return (
            f"- Confidence: {section.get('confidence', 0.5)}\n"
            f"- Price Judgment: {section.get('price_judgment') or '—'}\n"
            f"- Rationale:\n{_bullet_block(section.get('rationale') or [])}\n"
            f"- Watch Signals:\n{_bullet_block(section.get('watch_signals') or [])}\n"
            f"- Invalidations:\n{_bullet_block(section.get('invalidations') or [])}"
        )

    personality = payload.get("dominant_personality") if isinstance(payload.get("dominant_personality"), dict) else {}
    return (
        "## Technical Summary\n"
        f"- Summary: {payload.get('technical_summary') or payload.get('company_summary') or '—'}\n"
        f"- Price Position: {payload.get('price_position_summary') or '—'}\n"
        f"- Dominant Personality: {personality.get('label') or '—'}\n"
        f"- Dominant Horizon: {personality.get('dominant_horizon') or 'balanced'}\n"
        f"- Why Dominant: {personality.get('why') or '—'}\n"
        "\n## Volume And Participation\n"
        f"- {payload.get('volume_participation') or '—'}\n"
        "\n## Volatility And Range\n"
        f"- {payload.get('volatility_range_context') or '—'}\n"
        "\n### Short Horizon\n"
        f"{_render_horizon(payload.get('short_horizon_view') or {})}\n"
        "\n### Medium Horizon\n"
        f"{_render_horizon(payload.get('medium_horizon_view') or {})}\n"
        "\n### Long Horizon\n"
        f"{_render_horizon(payload.get('long_horizon_view') or {})}\n"
        f"\n## Risk Map\n{_bullet_block(payload.get('risk_map') or [])}\n"
        f"\n## Uncertainty Map\n{_bullet_block(payload.get('uncertainty_map') or [])}\n"
    )


def _build_company_story_warmup_input_items(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    llm_model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        llm_model=llm_model,
        output_language=output_language,
    )
    items: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, datetime]] = set()
    for article in sorted(articles, key=lambda item: item.news_date_time):
        article_key = (article.news_title, article.news_date_time)
        if article_key in seen_keys:
            continue
        seen_keys.add(article_key)
        content = _decode_llm_content(
            article.llm_analyzed_content,
            article.original_content,
        )
        items.append(
            {
                "news_date_time": article.news_date_time.isoformat(),
                "news_title": article.news_title,
                "news_source": article.news_source,
                "news_source_link": article.news_source_link,
                "summary": content.get("summary") or article.original_content or "",
            }
        )
    return items






def _normalize_story_warmup_groups(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    ongoing_raw = payload.get("ongoing_stories")
    finished_raw = payload.get("finished_stories")
    if not isinstance(ongoing_raw, list):
        ongoing_raw = []
    if not isinstance(finished_raw, list):
        finished_raw = []

    def _normalize_group(items: List[Dict[str, Any]], *, story_status: str) -> List[Dict[str, Any]]:
        normalized_items: List[Dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            title = _as_text(item.get("story_title") or item.get("title"))
            if not title:
                continue
            rank_raw = item.get("importance_rank")
            try:
                rank = int(rank_raw)
            except (TypeError, ValueError):
                rank = index + 1
            past = item.get("past") if isinstance(item.get("past"), list) else [item.get("past")] if item.get("past") else []
            now = item.get("now") if isinstance(item.get("now"), list) else [item.get("now")] if item.get("now") else []
            nxt = item.get("next") if isinstance(item.get("next"), list) else [item.get("next")] if item.get("next") else []
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            story_key = _normalize_story_key(item.get("story_key"), fallback_title=title, fallback_index=index)
            normalized_items.append(
                {
                    "story_key": story_key,
                    "story_title": title,
                    "importance_rank": max(1, rank),
                    "story_status": story_status,
                    "confidence": 0.5,
                    "happened_text": _format_story_section_bullets(past),
                    "happening_text": _format_story_section_bullets(now),
                    "next_text": _format_story_section_bullets(nxt),
                    "open_questions": [],
                    "evidence": evidence,
                    "change_log": [],
                }
            )
        return normalized_items

    ongoing = _normalize_group(ongoing_raw, story_status="stable")
    finished = _normalize_group(finished_raw, story_status="resolved")
    return {"ongoing_stories": ongoing, "finished_stories": finished}


def _format_story_section_bullets(items: List[Any]) -> str:
    cleaned: List[str] = []
    for item in items:
        text = _as_text(item)
        if text:
            cleaned.append(text)
    if not cleaned:
        return ""
    return "\n".join(f"- {item}" for item in cleaned)


def _generate_company_story_warmup_story_map(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=0.2,
        timeout_sec=240,
    )
    items = _build_company_story_cluster_input_items(
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    prompt = _build_company_story_warmup_cluster_prompt(
        company_name,
        start_date=start_date,
        end_date=end_date,
        output_language=output_language,
        items=items,
    )
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    combined = [
        item
        for item in (_normalize_story_record(row) for row in (payload.get("stories") if isinstance(payload.get("stories"), list) else []))
        if item
    ]
    _persist_story_refresh(
        company_name=company_name,
        as_of_date=end_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={
            "warmup_window_start": start_date.isoformat(),
            "warmup_window_end": end_date.isoformat(),
            "cluster_count": len(items),
            "clusters": items,
        },
        raw_output=json.dumps(payload, ensure_ascii=False),
        stories=combined,
    )
    return {
        "ongoing_story_count": len([s for s in combined if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]),
        "finished_story_count": len([s for s in combined if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]),
        "raw_fetched_count": len(items),
        "raw_stored_count": len(items),
        "filtered_kept_count": len(items),
    }




# Build a compact daily delta payload so incremental story update works on today's
# filtered raw news instead of rebuilding the whole story map from scratch.
def _build_company_story_incremental_news_items(
    company_name: str,
    *,
    target_date: date,
    llm_model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(
        company_name,
        start_date=target_date,
        end_date=target_date,
        llm_model=llm_model,
        output_language=output_language,
    )
    items: List[Dict[str, Any]] = []
    for article in sorted(articles, key=lambda item: (item.news_date_time, item.id or 0)):
        decoded = _decode_llm_content(article.llm_analyzed_content, article.original_content)
        items.append(
            {
                "news_id": int(article.id or 0),
                "news_date_time": article.news_date_time.isoformat(),
                "news_title": article.news_title,
                "news_source": article.news_source,
                "news_source_link": article.news_source_link,
                "summary": decoded.get("summary") or article.original_content or "",
            }
        )
    return items






def _normalize_company_cluster_rows(
    *,
    company_name: str,
    target_date: date,
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = payload.get("clusters")
    if not isinstance(rows, list):
        rows = []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        title = str(item.get("cluster_title") or "").strip()
        summary = str(item.get("cluster_summary") or "").strip()
        if not title:
            continue
        cluster_key = _normalize_story_key(item.get("cluster_key"), fallback_title=title, fallback_index=index)
        if cluster_key in seen:
            continue
        seen.add(cluster_key)
        source_news = item.get("source_news") if isinstance(item.get("source_news"), list) else []
        normalized.append(
            {
                "company_name": company_name,
                "cluster_date": target_date,
                "cluster_key": cluster_key,
                "cluster_title": title,
                "cluster_summary": summary or title,
                "source_news": source_news,
            }
        )
    return normalized


def _replace_company_daily_clusters(
    *,
    company_name: str,
    target_date: date,
    clusters: List[Dict[str, Any]],
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                WHERE company_name = %s
                  AND cluster_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (company_name, target_date, provider_name, prompt_style, output_language),
            )
            for item in clusters:
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                        (company_name, cluster_date, cluster_key, cluster_title, cluster_summary, source_news_json,
                         provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                    """,
                    (
                        company_name,
                        item["cluster_date"],
                        item["cluster_key"],
                        item["cluster_title"],
                        item["cluster_summary"],
                        json.dumps(item.get("source_news") or [], ensure_ascii=False),
                        provider_name,
                        model,
                        prompt_style,
                        output_language,
                        json.dumps(input_payload, ensure_ascii=False),
                    ),
                )
        conn.commit()


def _build_company_story_cluster_input_items(
    *,
    company_name: str,
    start_date: date,
    end_date: date,
    provider_name: str,
    prompt_style: str,
    output_language: str,
) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cluster_date, cluster_key, cluster_title, cluster_summary, source_news_json
                FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                WHERE company_name = %s
                  AND cluster_date >= %s
                  AND cluster_date <= %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY cluster_date ASC, updated_at ASC, id ASC
                """,
                (company_name, start_date, end_date, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [
        {
            "cluster_date": row["cluster_date"].isoformat(),
            "cluster_key": row["cluster_key"],
            "cluster_title": row["cluster_title"],
            "cluster_summary": row["cluster_summary"] or "",
            "source_news": row["source_news_json"] or [],
        }
        for row in rows
    ]






def _normalize_story_routing_result(
    *,
    existing_stories: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    existing_by_key = {
        str(item.get("story_key") or "").strip(): item
        for item in existing_stories
        if str(item.get("story_key") or "").strip()
    }
    clusters_by_key = {
        str(item.get("cluster_key") or "").strip(): item
        for item in clusters
        if str(item.get("cluster_key") or "").strip()
    }
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
    assigned_keys: set[str] = set()
    existing_groups: Dict[str, List[Dict[str, Any]]] = {}
    new_groups: Dict[str, Dict[str, Any]] = {}
    ignored_items: List[Dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        try:
            cluster_key = str(item.get("cluster_key") or "").strip()
        except (TypeError, ValueError):
            continue
        if not cluster_key or cluster_key in assigned_keys or cluster_key not in clusters_by_key:
            continue
        assigned_keys.add(cluster_key)
        action = str(item.get("action") or "").strip().lower()
        cluster = clusters_by_key[cluster_key]
        if action == "existing_story":
            story_key = str(item.get("story_key") or "").strip()
            if story_key and story_key in existing_by_key:
                existing_groups.setdefault(story_key, []).append(cluster)
                continue
        if action == "new_story":
            new_title = _as_text(item.get("new_story_title")) or cluster.get("cluster_title") or f"Story {cluster_key}"
            new_key = _normalize_story_key("", fallback_title=new_title, fallback_index=len(new_groups))
            bucket = new_groups.setdefault(
                new_key, {"story_key": new_key, "story_title": new_title, "clusters": []},
            )
            bucket["clusters"].append(cluster)
            continue
        ignored_items.append(
            {
                "cluster_key": cluster_key,
                "reason": _as_text(item.get("reason")) or "ignore",
                "cluster_title": cluster.get("cluster_title") or "",
            }
        )
    for cluster_key, cluster in clusters_by_key.items():
        if cluster_key in assigned_keys:
            continue
        new_title = cluster.get("cluster_title") or f"Story {cluster_key}"
        new_key = _normalize_story_key("", fallback_title=new_title, fallback_index=len(new_groups))
        bucket = new_groups.setdefault(
            new_key, {"story_key": new_key, "story_title": new_title, "clusters": []},
        )
        bucket["clusters"].append(cluster)
    return {
        "existing_groups": existing_groups,
        "new_groups": list(new_groups.values()),
        "ignored_items": ignored_items,
    }






def _normalize_incremental_story_item(
    payload: Dict[str, Any],
    *,
    fallback_story_key: str,
    fallback_story_title: str,
    fallback_rank: int,
) -> Optional[Dict[str, Any]]:
    story = payload.get("story")
    if not isinstance(story, dict):
        return None
    normalized = _normalize_story_record(
        {
            **story,
            "story_key": story.get("story_key") or fallback_story_key,
            "story_title": story.get("story_title") or fallback_story_title,
            "importance_rank": story.get("importance_rank") or fallback_rank,
            "confidence": story.get("confidence", 0.5),
            "priority": story.get("priority") or "normal",
        }
    )
    return normalized


def _apply_incremental_story_updates(
    *,
    company_name: str,
    as_of_date: date,
    provider,
    existing_stories: List[Dict[str, Any]],
    routed: Dict[str, Any],
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    del prompt_style
    existing_by_key = {
        str(item.get("story_key") or "").strip(): item
        for item in existing_stories
        if str(item.get("story_key") or "").strip()
    }
    final_stories: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    updated_story_keys: List[str] = []
    new_story_keys: List[str] = []

    for story_key, story in existing_by_key.items():
        clusters = routed["existing_groups"].get(story_key) or []
        if not clusters:
            final_stories.append(story)
            continue
        prompt = _build_incremental_existing_story_prompt(
            company_name,
            as_of_date=as_of_date,
            output_language=output_language,
            story=story,
            clusters=clusters,
        )
        raw_output = provider.generate_text(prompt=prompt)
        payload = _parse_json_object(raw_output) or {}
        normalized = _normalize_incremental_story_item(
            payload,
            fallback_story_key=story_key,
            fallback_story_title=str(story.get("story_title") or story_key),
            fallback_rank=int(story.get("importance_rank") or 999),
        ) or story
        final_stories.append(normalized)
        updated_story_keys.append(story_key)
        raw_outputs.append(
            {
                "type": "existing_story",
                "story_key": story_key,
                "prompt": prompt,
                "raw_output": raw_output,
                "cluster_keys": [str(item.get("cluster_key") or "").strip() for item in clusters],
            }
        )

    for index, bucket in enumerate(routed["new_groups"]):
        story_key = str(bucket.get("story_key") or "").strip()
        story_title = str(bucket.get("story_title") or "").strip() or f"Story {index + 1}"
        clusters = bucket.get("clusters") if isinstance(bucket.get("clusters"), list) else []
        if not clusters:
            continue
        prompt = _build_incremental_new_story_prompt(
            company_name,
            as_of_date=as_of_date,
            output_language=output_language,
            story_key=story_key,
            story_title=story_title,
            clusters=clusters,
        )
        raw_output = provider.generate_text(prompt=prompt)
        payload = _parse_json_object(raw_output) or {}
        normalized = _normalize_incremental_story_item(
            payload,
            fallback_story_key=story_key,
            fallback_story_title=story_title,
            fallback_rank=len(final_stories) + 1,
        )
        if not normalized:
            continue
        final_stories.append(normalized)
        new_story_keys.append(normalized["story_key"])
        raw_outputs.append(
            {
                "type": "new_story",
                "story_key": normalized["story_key"],
                "prompt": prompt,
                "raw_output": raw_output,
                "cluster_keys": [str(item.get("cluster_key") or "").strip() for item in clusters],
            }
        )

    final_stories = sorted(
        [_normalize_story_record(item) for item in final_stories if isinstance(item, dict)],
        key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or "")),
    )
    return {
        "stories": final_stories,
        "raw_outputs": raw_outputs,
        "updated_story_keys": updated_story_keys,
        "new_story_keys": new_story_keys,
    }








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


def _story_warmup_key(
    company_name: str,
    *,
    provider_name: str,
    prompt_style: str,
    output_language: str,
) -> str:
    return "||".join(
        [
            _normalize_company_name(company_name),
            str(provider_name or DEFAULT_PROVIDER).strip(),
            str(prompt_style or "simple").strip(),
            str(output_language or "zh-CN").strip(),
        ]
    )


def _build_story_warmup_slices(
    *,
    end_date: date,
    warmup_days: int,
    slice_days: int,
) -> List[tuple[date, date]]:
    total_days = max(1, int(warmup_days))
    step = max(1, int(slice_days))
    start_date = end_date - timedelta(days=total_days - 1)
    slices: List[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        slice_end = min(end_date, cursor + timedelta(days=step - 1))
        slices.append((cursor, slice_end))
        cursor = slice_end + timedelta(days=1)
    return slices


def _ensure_story_warmup_thread(
    company_name: str,
    *,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    warmup_days: int,
    slice_days: int,
) -> None:
    key = _story_warmup_key(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    with _WARMUP_THREADS_LOCK:
        existing = _WARMUP_THREADS.get(key)
        if existing and existing.is_alive():
            return
        thread = threading.Thread(
            target=_run_company_story_warmup_job,
            kwargs={
                "company_name": company_name,
                "provider_name": provider_name,
                "model": model,
                "prompt_style": prompt_style,
                "output_language": output_language,
                "warmup_days": warmup_days,
                "slice_days": slice_days,
            },
            daemon=True,
            name=f"story-warmup-{company_name}",
        )
        _WARMUP_THREADS[key] = thread
        thread.start()


def _resolve_company_ticker(company_name: str) -> Optional[str]:
    profile = get_company_profile(company_name)
    if not profile:
        profile = ensure_company_profile(company_name)
    if not profile:
        return None
    for key in ("ticker", "symbol"):
        value = profile.get(key)
        if value:
            return str(value).strip()
    return None


def _upsert_story_warmup_state(
    company_name: str,
    *,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    _ensure_news_schema()
    defaults = {
        "job_state": "not_started",
        "current_stage": "idle",
        "window_days": DEFAULT_STORY_WARMUP_DAYS,
        "slice_days": DEFAULT_STORY_WARMUP_SLICE_DAYS,
        "window_start_date": None,
        "window_end_date": None,
        "total_slices": 0,
        "completed_slices": 0,
        "current_slice_start_date": None,
        "current_slice_end_date": None,
        "last_completed_slice_end_date": None,
        "analysis_started": False,
        "analysis_completed": False,
        "raw_fetched_count": 0,
        "raw_stored_count": 0,
        "filtered_kept_count": 0,
        "ongoing_story_count": 0,
        "finished_story_count": 0,
        "retry_count": 0,
        "last_retry_at": None,
        "last_error": "",
        "failed_stage": "",
        "started_at": None,
        "completed_at": None,
    }
    defaults.update(updates)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_STORY_WARMUP_STATE} (
                    company_name,
                    provider,
                    model,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    job_state,
                    current_stage,
                    window_days,
                    slice_days,
                    window_start_date,
                    window_end_date,
                    total_slices,
                    completed_slices,
                    current_slice_start_date,
                    current_slice_end_date,
                    last_completed_slice_end_date,
                    analysis_started,
                    analysis_completed,
                    raw_fetched_count,
                    raw_stored_count,
                    filtered_kept_count,
                    ongoing_story_count,
                    finished_story_count,
                    retry_count,
                    last_retry_at,
                    last_error,
                    failed_stage,
                    started_at,
                    completed_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), %s, NOW()
                )
                ON CONFLICT (company_name, provider, prompt_style, {COL_OUTPUT_LANGUAGE})
                DO UPDATE SET
                    model = EXCLUDED.model,
                    job_state = EXCLUDED.job_state,
                    current_stage = EXCLUDED.current_stage,
                    window_days = EXCLUDED.window_days,
                    slice_days = EXCLUDED.slice_days,
                    window_start_date = EXCLUDED.window_start_date,
                    window_end_date = EXCLUDED.window_end_date,
                    total_slices = EXCLUDED.total_slices,
                    completed_slices = EXCLUDED.completed_slices,
                    current_slice_start_date = EXCLUDED.current_slice_start_date,
                    current_slice_end_date = EXCLUDED.current_slice_end_date,
                    last_completed_slice_end_date = EXCLUDED.last_completed_slice_end_date,
                    analysis_started = EXCLUDED.analysis_started,
                    analysis_completed = EXCLUDED.analysis_completed,
                    raw_fetched_count = EXCLUDED.raw_fetched_count,
                    raw_stored_count = EXCLUDED.raw_stored_count,
                    filtered_kept_count = EXCLUDED.filtered_kept_count,
                    ongoing_story_count = EXCLUDED.ongoing_story_count,
                    finished_story_count = EXCLUDED.finished_story_count,
                    retry_count = EXCLUDED.retry_count,
                    last_retry_at = EXCLUDED.last_retry_at,
                    last_error = EXCLUDED.last_error,
                    failed_stage = EXCLUDED.failed_stage,
                    started_at = COALESCE({TBL_COMPANY_STORY_WARMUP_STATE}.started_at, EXCLUDED.started_at),
                    completed_at = EXCLUDED.completed_at,
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    company_name,
                    provider_name,
                    model,
                    prompt_style,
                    output_language,
                    defaults["job_state"],
                    defaults["current_stage"],
                    int(defaults["window_days"]),
                    int(defaults["slice_days"]),
                    defaults["window_start_date"],
                    defaults["window_end_date"],
                    int(defaults["total_slices"]),
                    int(defaults["completed_slices"]),
                    defaults["current_slice_start_date"],
                    defaults["current_slice_end_date"],
                    defaults["last_completed_slice_end_date"],
                    bool(defaults["analysis_started"]),
                    bool(defaults["analysis_completed"]),
                    int(defaults["raw_fetched_count"]),
                    int(defaults["raw_stored_count"]),
                    int(defaults["filtered_kept_count"]),
                    int(defaults["ongoing_story_count"]),
                    int(defaults["finished_story_count"]),
                    int(defaults["retry_count"]),
                    defaults["last_retry_at"],
                    defaults["last_error"],
                    defaults["failed_stage"],
                    defaults["started_at"],
                    defaults["completed_at"],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_story_warmup_state(row)


def _run_company_story_warmup_job(
    *,
    company_name: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    warmup_days: int,
    slice_days: int,
) -> None:
    key = _story_warmup_key(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    try:
        try:
            _run_company_story_warmup_job_inner(
                company_name=company_name,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
                warmup_days=warmup_days,
                slice_days=slice_days,
            )
        except Exception as exc:
            logger.exception("Story warm-up job failed: company=%s", company_name)
            _upsert_story_warmup_state(
                _normalize_company_name(company_name),
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
                updates={
                    "job_state": "failed",
                    "current_stage": "fetching_raw",
                    "window_days": warmup_days,
                    "slice_days": slice_days,
                    "last_error": str(exc),
                    "failed_stage": "fetching_raw",
                    "analysis_started": False,
                    "analysis_completed": False,
                },
            )
    finally:
        with _WARMUP_THREADS_LOCK:
            _WARMUP_THREADS.pop(key, None)


def _run_company_story_warmup_job_inner(
    *,
    company_name: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    warmup_days: int,
    slice_days: int,
) -> None:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    end_date = datetime.now(timezone.utc).date()
    safe_warmup_days = max(1, int(warmup_days))
    safe_slice_days = 1
    start_date = end_date - timedelta(days=safe_warmup_days - 1)
    run_days = [start_date + timedelta(days=index) for index in range(safe_warmup_days)]
    state = get_company_story_warmup_state(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    _upsert_story_warmup_state(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        updates={
            "job_state": "running",
            "current_stage": "fetching_raw",
            "window_days": safe_warmup_days,
            "slice_days": safe_slice_days,
            "window_start_date": start_date,
            "window_end_date": end_date,
            "total_slices": len(run_days),
            "started_at": datetime.now(timezone.utc),
            "retry_count": int(state.get("retry_count") or 0),
            "raw_fetched_count": int(state.get("raw_fetched_count") or 0),
            "raw_stored_count": int(state.get("raw_stored_count") or 0),
            "filtered_kept_count": int(state.get("filtered_kept_count") or 0),
            "ongoing_story_count": 0,
            "finished_story_count": 0,
            "analysis_started": True,
            "analysis_completed": False,
            "completed_slices": int(state.get("completed_slices") or 0),
            "last_completed_slice_end_date": _parse_iso_date(state.get("last_completed_slice_end_date")),
            "last_error": "",
            "failed_stage": "",
            "completed_at": None,
        },
    )
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=0.2,
        timeout_sec=180,
    )
    last_completed_slice_end = _parse_iso_date(state.get("last_completed_slice_end_date"))
    fetched_total = int(state.get("raw_fetched_count") or 0)
    raw_stored_count = int(state.get("raw_stored_count") or 0)
    filtered_kept_count = int(state.get("filtered_kept_count") or 0)
    completed_slices = int(state.get("completed_slices") or 0)
    finnhub_source = get_news_source("finnhub")
    ticker: Optional[str] = None

    for current_day in run_days:
        if last_completed_slice_end and current_day <= last_completed_slice_end:
            continue
        retries = 0
        while True:
            fetch_ranges = _build_fetch_ranges_for_slice(
                company_name,
                slice_start=current_day,
                slice_end=current_day,
                today=end_date,
            )
            if fetch_ranges and not ticker:
                ticker = _resolve_company_ticker(company_name)
            if fetch_ranges and not ticker:
                _upsert_story_warmup_state(
                    company_name,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                    updates={
                        "job_state": "failed",
                        "current_stage": "fetching_raw",
                        "window_days": safe_warmup_days,
                        "slice_days": safe_slice_days,
                        "window_start_date": start_date,
                        "window_end_date": end_date,
                        "total_slices": len(run_days),
                        "completed_slices": completed_slices,
                        "current_slice_start_date": current_day,
                        "current_slice_end_date": current_day,
                        "analysis_started": True,
                        "analysis_completed": False,
                        "raw_fetched_count": fetched_total,
                        "raw_stored_count": raw_stored_count,
                        "filtered_kept_count": filtered_kept_count,
                        "last_error": "No valid ticker available for company warm-up.",
                        "failed_stage": "fetching_raw",
                        "completed_at": datetime.now(timezone.utc),
                    },
                )
                logger.warning("Company warm-up aborted: company=%s no valid ticker", company_name)
                return
            _upsert_story_warmup_state(
                company_name,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
                updates={
                    "job_state": "running",
                    "current_stage": "fetching_raw",
                    "window_days": safe_warmup_days,
                    "slice_days": safe_slice_days,
                    "window_start_date": start_date,
                    "window_end_date": end_date,
                    "total_slices": len(run_days),
                    "completed_slices": completed_slices,
                    "current_slice_start_date": current_day,
                    "current_slice_end_date": current_day,
                    "last_completed_slice_end_date": last_completed_slice_end,
                    "raw_fetched_count": fetched_total,
                    "raw_stored_count": raw_stored_count,
                    "filtered_kept_count": filtered_kept_count,
                    "retry_count": retries,
                    "last_error": "",
                    "failed_stage": "",
                    "analysis_started": True,
                    "analysis_completed": False,
                },
            )
            try:
                for fetch_start, fetch_end in fetch_ranges:
                    raw_items = finnhub_source.fetch_news(
                        company_name=ticker,
                        start_date=fetch_start.isoformat(),
                        end_date=fetch_end.isoformat(),
                    )
                    fetched_total += len(raw_items)
                    raw_articles = _news_items_from_provider(
                        company_name,
                        _tag_source(raw_items, "finnhub"),
                        end_date=fetch_end,
                        analyzed=False,
                    )
                    _store_articles(
                        raw_articles,
                        llm_model=model,
                        output_language=output_language,
                    )
                    raw_stored_count += len(raw_articles)

                kept_count = _filter_company_news_range_raw(
                    company_name=company_name,
                    start_date=current_day,
                    end_date=current_day,
                    provider=provider,
                    llm_model=model,
                )
                filtered_kept_count += kept_count

                _upsert_story_warmup_state(
                    company_name,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                    updates={
                        "job_state": "running",
                        "current_stage": "building_reports",
                        "window_days": safe_warmup_days,
                        "slice_days": safe_slice_days,
                        "window_start_date": start_date,
                        "window_end_date": end_date,
                        "total_slices": len(run_days),
                        "completed_slices": completed_slices,
                        "current_slice_start_date": current_day,
                        "current_slice_end_date": current_day,
                        "last_completed_slice_end_date": last_completed_slice_end,
                        "raw_fetched_count": fetched_total,
                        "raw_stored_count": raw_stored_count,
                        "filtered_kept_count": filtered_kept_count,
                        "retry_count": 0,
                        "analysis_started": True,
                        "analysis_completed": False,
                    },
                )

                generate_company_daily_report(
                    company_name,
                    target_date=current_day,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                )
                refresh_company_daily_clusters(
                    company_name,
                    target_date=current_day,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                )
                if current_day.weekday() == 4:
                    generate_weekly_report(
                        company_name,
                        start_date=current_day - timedelta(days=6),
                        end_date=current_day,
                        output_language=output_language,
                        provider_name=provider_name,
                        model=model,
                    )

                completed_slices += 1
                last_completed_slice_end = current_day
                _upsert_story_warmup_state(
                    company_name,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                    updates={
                        "job_state": "running",
                        "current_stage": "building_reports",
                        "window_days": safe_warmup_days,
                        "slice_days": safe_slice_days,
                        "window_start_date": start_date,
                        "window_end_date": end_date,
                        "total_slices": len(run_days),
                        "completed_slices": completed_slices,
                        "current_slice_start_date": None,
                        "current_slice_end_date": None,
                        "last_completed_slice_end_date": last_completed_slice_end,
                        "raw_fetched_count": fetched_total,
                        "raw_stored_count": raw_stored_count,
                        "filtered_kept_count": filtered_kept_count,
                        "retry_count": 0,
                        "analysis_started": True,
                        "analysis_completed": False,
                    },
                )
                break
            except Exception as exc:
                retries += 1
                is_rate_limit = "429" in str(exc) or "rate limit" in str(exc).lower()
                _upsert_story_warmup_state(
                    company_name,
                    provider_name=provider_name,
                    model=model,
                    prompt_style=prompt_style,
                    output_language=output_language,
                    updates={
                        "job_state": "partial" if retries >= DEFAULT_STORY_WARMUP_MAX_RETRIES else "running",
                        "current_stage": "fetching_raw",
                        "window_days": safe_warmup_days,
                        "slice_days": safe_slice_days,
                        "window_start_date": start_date,
                        "window_end_date": end_date,
                        "total_slices": len(run_days),
                        "completed_slices": completed_slices,
                        "current_slice_start_date": current_day,
                        "current_slice_end_date": current_day,
                        "last_completed_slice_end_date": last_completed_slice_end,
                        "raw_fetched_count": fetched_total,
                        "raw_stored_count": raw_stored_count,
                        "filtered_kept_count": filtered_kept_count,
                        "retry_count": retries,
                        "last_retry_at": datetime.now(timezone.utc),
                        "last_error": str(exc),
                        "failed_stage": "fetching_raw",
                        "analysis_started": True,
                        "analysis_completed": False,
                    },
                )
                if retries >= DEFAULT_STORY_WARMUP_MAX_RETRIES:
                    if is_rate_limit:
                        _upsert_story_warmup_state(
                            company_name,
                            provider_name=provider_name,
                            model=model,
                            prompt_style=prompt_style,
                            output_language=output_language,
                            updates={
                                "job_state": "failed",
                                "current_stage": "fetching_raw",
                                "window_days": safe_warmup_days,
                                "slice_days": safe_slice_days,
                                "window_start_date": start_date,
                                "window_end_date": end_date,
                                "total_slices": len(run_days),
                                "completed_slices": completed_slices,
                                "current_slice_start_date": current_day,
                                "current_slice_end_date": current_day,
                                "last_completed_slice_end_date": last_completed_slice_end,
                                "raw_fetched_count": fetched_total,
                                "raw_stored_count": raw_stored_count,
                                "filtered_kept_count": filtered_kept_count,
                                "retry_count": retries,
                                "last_retry_at": datetime.now(timezone.utc),
                                "last_error": f"Warm-up stopped after repeated rate limiting: {exc}",
                                "failed_stage": "fetching_raw",
                                "analysis_started": True,
                                "analysis_completed": False,
                                "completed_at": datetime.now(timezone.utc),
                            },
                        )
                        return
                    raise
                if is_rate_limit:
                    pytime.sleep(DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC)
                    continue
                raise

    if _count_company_raw_for_range(company_name, start_date, end_date) <= 0:
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "failed",
                "current_stage": "fetching_raw",
                "window_days": safe_warmup_days,
                "slice_days": safe_slice_days,
                "window_start_date": start_date,
                "window_end_date": end_date,
                "total_slices": len(run_days),
                "completed_slices": completed_slices,
                "current_slice_start_date": None,
                "current_slice_end_date": None,
                "last_completed_slice_end_date": last_completed_slice_end,
                "analysis_started": True,
                "analysis_completed": False,
                "raw_fetched_count": fetched_total,
                "raw_stored_count": raw_stored_count,
                "filtered_kept_count": filtered_kept_count,
                "last_error": "Warm-up fetched zero news items. Check the company ticker and rebuild warm-up.",
                "failed_stage": "fetching_raw",
                "completed_at": datetime.now(timezone.utc),
            },
        )
        logger.warning("Company warm-up failed: company=%s fetched zero raw news", company_name)
        return

    _upsert_story_warmup_state(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        updates={
            "job_state": "completed",
            "current_stage": "done",
            "window_days": safe_warmup_days,
            "slice_days": safe_slice_days,
            "window_start_date": start_date,
            "window_end_date": end_date,
            "total_slices": len(run_days),
            "completed_slices": len(run_days),
            "current_slice_start_date": None,
            "current_slice_end_date": None,
            "last_completed_slice_end_date": end_date,
            "analysis_started": True,
            "analysis_completed": True,
            "raw_fetched_count": fetched_total,
            "raw_stored_count": raw_stored_count,
            "filtered_kept_count": filtered_kept_count,
            "ongoing_story_count": 0,
            "finished_story_count": 0,
            "last_error": "",
            "failed_stage": "",
            "completed_at": datetime.now(timezone.utc),
        },
    )


def _extract_profile_extension(profile: Dict[str, Any]) -> Dict[str, Any]:
    known = {
        "ticker",
        "symbol",
        "name",
        "exchange",
        "currency",
        "country",
        "ipo",
        "weburl",
        "logo",
        "finnhubIndustry",
        "phone",
        "marketCapitalization",
        "shareOutstanding",
        "cusip",
        "isin",
        "lei",
    }
    return {key: value for key, value in profile.items() if key not in known}


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




def _days(count: int) -> timedelta:
    return timedelta(days=count)
