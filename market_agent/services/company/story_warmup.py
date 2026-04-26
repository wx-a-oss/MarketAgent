"""Warmup lifecycle functions."""

from __future__ import annotations

import json
import logging
import threading
import time as pytime
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.llms.news import get_news_provider
from market_agent.news_sources import get_news_source
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
    TBL_COMPANY_STORY_WARMUP_STATE,
)
from market_agent.services.company._constants import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_STORY_WARMUP_DAYS,
    DEFAULT_STORY_WARMUP_MAX_RETRIES,
    DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC,
    DEFAULT_STORY_WARMUP_SLICE_DAYS,
    DEFAULT_STORY_WARMUP_STALE_MINUTES,
)
from market_agent.services.company._helpers import (
    _as_text,
    _decode_llm_content,
    _ensure_news_schema,
    _format_story_section_bullets,
    _normalize_company_name,
    _normalize_story_key,
    _normalize_story_record,
    _parse_iso_date,
    _parse_json_object,
    _parse_story_warmup_state_datetime,
    _row_to_story_warmup_state,
    _tag_source,
)
from market_agent.services.company.prompts import (
    _build_company_story_warmup_cluster_prompt,
    _build_company_story_warmup_consolidation_prompt,
    _build_company_story_warmup_prompt,
)
from market_agent.services.company.profiles import (
    _build_fetch_ranges_for_slice,
    _count_company_raw_for_range,
    _resolve_company_ticker,
    get_company_profile,
)
from market_agent.services.company.news_crud import (
    _filter_company_news_range_raw,
    _news_items_from_provider,
    _store_articles,
    get_company_news_for_range,
)
from market_agent.services.company.reports import (
    _build_company_story_cluster_input_items,
    generate_company_daily_report,
    generate_weekly_report,
    refresh_company_daily_clusters,
)
from market_agent.services.company.stories import (
    _persist_story_refresh,
    list_company_story_states,
)

logger = logging.getLogger("uvicorn.error")

_WARMUP_THREADS: Dict[str, threading.Thread] = {}
_WARMUP_THREADS_LOCK = threading.Lock()


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
                f"SELECT * FROM {TBL_COMPANY_STORY_WARMUP_STATE} WHERE company_name = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s LIMIT 1",
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
    state = get_company_story_warmup_state(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
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
        heartbeat = _parse_story_warmup_state_datetime(current_state.get("updated_at") or current_state.get("started_at"))
        if not heartbeat:
            return "Warm-up state is missing heartbeat timestamps."
        stale_sec = DEFAULT_STORY_WARMUP_STALE_MINUTES * 60
        age_sec = max(0.0, (datetime.now(timezone.utc) - heartbeat).total_seconds())
        if age_sec >= stale_sec:
            return f"Warm-up state is stale: no update for {round(age_sec / 60.0, 1)} minutes."
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
        return get_company_story_warmup_state(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    state = get_company_story_warmup_state(normalized, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    invalid_reason = _get_company_story_warmup_invalid_reason(normalized, state=state)
    if state.get("job_state") == "completed" and invalid_reason is None:
        return state
    if invalid_reason and str(state.get("job_state") or "").strip().lower() in {"running", "analyzing", "partial"}:
        _upsert_story_warmup_state(
            normalized, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language,
            updates={
                "job_state": "failed", "current_stage": "idle",
                "window_days": max(1, int(state.get("window_days") or warmup_days)),
                "slice_days": max(1, int(state.get("slice_days") or slice_days)),
                "analysis_started": bool(state.get("analysis_started")), "analysis_completed": False,
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
    _ensure_story_warmup_thread(normalized, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, warmup_days=warmup_days, slice_days=slice_days)
    return get_company_story_warmup_state(normalized, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)


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
        return get_company_story_warmup_state(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TBL_COMPANY_STORY_STATE} WHERE company_name = %s", (normalized,))
            cur.execute(f"DELETE FROM {TBL_COMPANY_STORY_UPDATE} WHERE company_name = %s", (normalized,))
            cur.execute(
                f"UPDATE {TBL_COMPANY_STORY_WARMUP_STATE} SET job_state = 'not_started', current_stage = 'idle', total_slices = 0, completed_slices = 0, current_slice_start_date = NULL, current_slice_end_date = NULL, last_completed_slice_end_date = NULL, analysis_started = FALSE, analysis_completed = FALSE, raw_fetched_count = 0, raw_stored_count = 0, filtered_kept_count = 0, ongoing_story_count = 0, finished_story_count = 0, retry_count = 0, last_retry_at = NULL, last_error = '', failed_stage = '', started_at = NULL, completed_at = NULL, updated_at = NOW() WHERE company_name = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s",
                (normalized, provider_name, prompt_style, output_language),
            )
        conn.commit()
    return ensure_company_story_warmup_started(normalized, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, warmup_days=warmup_days, slice_days=slice_days)


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
            normalized_items.append({"story_key": story_key, "story_title": title, "importance_rank": max(1, rank), "story_status": story_status, "confidence": 0.5, "happened_text": _format_story_section_bullets(past), "happening_text": _format_story_section_bullets(now), "next_text": _format_story_section_bullets(nxt), "open_questions": [], "evidence": evidence, "change_log": []})
        return normalized_items

    ongoing = _normalize_group(ongoing_raw, story_status="stable")
    finished = _normalize_group(finished_raw, story_status="resolved")
    return {"ongoing_stories": ongoing, "finished_stories": finished}


def _upsert_story_warmup_state(company_name: str, *, provider_name: str, model: str, prompt_style: str, output_language: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_news_schema()
    defaults = {
        "job_state": "not_started", "current_stage": "idle", "window_days": DEFAULT_STORY_WARMUP_DAYS, "slice_days": DEFAULT_STORY_WARMUP_SLICE_DAYS,
        "window_start_date": None, "window_end_date": None, "total_slices": 0, "completed_slices": 0,
        "current_slice_start_date": None, "current_slice_end_date": None, "last_completed_slice_end_date": None,
        "analysis_started": False, "analysis_completed": False, "raw_fetched_count": 0, "raw_stored_count": 0, "filtered_kept_count": 0,
        "ongoing_story_count": 0, "finished_story_count": 0, "retry_count": 0, "last_retry_at": None, "last_error": "", "failed_stage": "",
        "started_at": None, "completed_at": None,
    }
    defaults.update(updates)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_STORY_WARMUP_STATE} (
                    company_name, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                    job_state, current_stage, window_days, slice_days,
                    window_start_date, window_end_date, total_slices, completed_slices,
                    current_slice_start_date, current_slice_end_date, last_completed_slice_end_date,
                    analysis_started, analysis_completed, raw_fetched_count, raw_stored_count, filtered_kept_count,
                    ongoing_story_count, finished_story_count, retry_count, last_retry_at, last_error, failed_stage,
                    started_at, completed_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), %s, NOW())
                ON CONFLICT (company_name, provider, prompt_style, {COL_OUTPUT_LANGUAGE})
                DO UPDATE SET
                    model = EXCLUDED.model, job_state = EXCLUDED.job_state, current_stage = EXCLUDED.current_stage,
                    window_days = EXCLUDED.window_days, slice_days = EXCLUDED.slice_days,
                    window_start_date = EXCLUDED.window_start_date, window_end_date = EXCLUDED.window_end_date,
                    total_slices = EXCLUDED.total_slices, completed_slices = EXCLUDED.completed_slices,
                    current_slice_start_date = EXCLUDED.current_slice_start_date, current_slice_end_date = EXCLUDED.current_slice_end_date,
                    last_completed_slice_end_date = EXCLUDED.last_completed_slice_end_date,
                    analysis_started = EXCLUDED.analysis_started, analysis_completed = EXCLUDED.analysis_completed,
                    raw_fetched_count = EXCLUDED.raw_fetched_count, raw_stored_count = EXCLUDED.raw_stored_count, filtered_kept_count = EXCLUDED.filtered_kept_count,
                    ongoing_story_count = EXCLUDED.ongoing_story_count, finished_story_count = EXCLUDED.finished_story_count,
                    retry_count = EXCLUDED.retry_count, last_retry_at = EXCLUDED.last_retry_at, last_error = EXCLUDED.last_error, failed_stage = EXCLUDED.failed_stage,
                    started_at = COALESCE({TBL_COMPANY_STORY_WARMUP_STATE}.started_at, EXCLUDED.started_at),
                    completed_at = EXCLUDED.completed_at, updated_at = NOW()
                RETURNING *
                """,
                (company_name, provider_name, model, prompt_style, output_language, defaults["job_state"], defaults["current_stage"], int(defaults["window_days"]), int(defaults["slice_days"]), defaults["window_start_date"], defaults["window_end_date"], int(defaults["total_slices"]), int(defaults["completed_slices"]), defaults["current_slice_start_date"], defaults["current_slice_end_date"], defaults["last_completed_slice_end_date"], bool(defaults["analysis_started"]), bool(defaults["analysis_completed"]), int(defaults["raw_fetched_count"]), int(defaults["raw_stored_count"]), int(defaults["filtered_kept_count"]), int(defaults["ongoing_story_count"]), int(defaults["finished_story_count"]), int(defaults["retry_count"]), defaults["last_retry_at"], defaults["last_error"], defaults["failed_stage"], defaults["started_at"], defaults["completed_at"]),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_story_warmup_state(row)


def _story_warmup_key(company_name: str, *, provider_name: str, prompt_style: str, output_language: str) -> str:
    return "||".join([_normalize_company_name(company_name), str(provider_name or DEFAULT_PROVIDER).strip(), str(prompt_style or "simple").strip(), str(output_language or "zh-CN").strip()])


def _build_story_warmup_slices(*, end_date: date, warmup_days: int, slice_days: int) -> List[tuple[date, date]]:
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


def _ensure_story_warmup_thread(company_name: str, *, provider_name: str, model: str, prompt_style: str, output_language: str, warmup_days: int, slice_days: int) -> None:
    key = _story_warmup_key(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    with _WARMUP_THREADS_LOCK:
        existing = _WARMUP_THREADS.get(key)
        if existing and existing.is_alive():
            return
        thread = threading.Thread(target=_run_company_story_warmup_job, kwargs={"company_name": company_name, "provider_name": provider_name, "model": model, "prompt_style": prompt_style, "output_language": output_language, "warmup_days": warmup_days, "slice_days": slice_days}, daemon=True, name=f"story-warmup-{company_name}")
        _WARMUP_THREADS[key] = thread
        thread.start()


def _build_company_story_warmup_input_items(company_name: str, *, start_date: date, end_date: date, llm_model: str = DEFAULT_MODEL, output_language: str = "zh-CN") -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(company_name, start_date=start_date, end_date=end_date, llm_model=llm_model, output_language=output_language)
    items: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, datetime]] = set()
    for article in sorted(articles, key=lambda item: item.news_date_time):
        article_key = (article.news_title, article.news_date_time)
        if article_key in seen_keys:
            continue
        seen_keys.add(article_key)
        content = _decode_llm_content(article.llm_analyzed_content, article.original_content)
        items.append({"news_date_time": article.news_date_time.isoformat(), "news_title": article.news_title, "news_source": article.news_source, "news_source_link": article.news_source_link, "summary": content.get("summary") or article.original_content or ""})
    return items


def _generate_company_story_warmup_story_map(company_name: str, *, start_date: date, end_date: date, provider_name: str, model: str, prompt_style: str, output_language: str) -> Dict[str, Any]:
    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=240)
    items = _build_company_story_cluster_input_items(company_name=company_name, start_date=start_date, end_date=end_date, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    prompt = _build_company_story_warmup_cluster_prompt(company_name, start_date=start_date, end_date=end_date, output_language=output_language, items=items)
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    combined = [item for item in (_normalize_story_record(row) for row in (payload.get("stories") if isinstance(payload.get("stories"), list) else [])) if item]
    _persist_story_refresh(company_name=company_name, as_of_date=end_date, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"warmup_window_start": start_date.isoformat(), "warmup_window_end": end_date.isoformat(), "cluster_count": len(items), "clusters": items}, raw_output=json.dumps(payload, ensure_ascii=False), stories=combined)
    return {"ongoing_story_count": len([s for s in combined if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]), "finished_story_count": len([s for s in combined if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]), "raw_fetched_count": len(items), "raw_stored_count": len(items), "filtered_kept_count": len(items)}


def _run_company_story_warmup_job(*, company_name: str, provider_name: str, model: str, prompt_style: str, output_language: str, warmup_days: int, slice_days: int) -> None:
    key = _story_warmup_key(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    try:
        try:
            _run_company_story_warmup_job_inner(company_name=company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, warmup_days=warmup_days, slice_days=slice_days)
        except Exception as exc:
            logger.exception("Story warm-up job failed: company=%s", company_name)
            _upsert_story_warmup_state(_normalize_company_name(company_name), provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "failed", "current_stage": "fetching_raw", "window_days": warmup_days, "slice_days": slice_days, "last_error": str(exc), "failed_stage": "fetching_raw", "analysis_started": False, "analysis_completed": False})
    finally:
        with _WARMUP_THREADS_LOCK:
            _WARMUP_THREADS.pop(key, None)


def _run_company_story_warmup_job_inner(*, company_name: str, provider_name: str, model: str, prompt_style: str, output_language: str, warmup_days: int, slice_days: int) -> None:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    end_date = datetime.now(timezone.utc).date()
    safe_warmup_days = max(1, int(warmup_days))
    safe_slice_days = 1
    start_date = end_date - timedelta(days=safe_warmup_days - 1)
    run_days = [start_date + timedelta(days=index) for index in range(safe_warmup_days)]
    state = get_company_story_warmup_state(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "running", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "started_at": datetime.now(timezone.utc), "retry_count": int(state.get("retry_count") or 0), "raw_fetched_count": int(state.get("raw_fetched_count") or 0), "raw_stored_count": int(state.get("raw_stored_count") or 0), "filtered_kept_count": int(state.get("filtered_kept_count") or 0), "ongoing_story_count": 0, "finished_story_count": 0, "analysis_started": True, "analysis_completed": False, "completed_slices": int(state.get("completed_slices") or 0), "last_completed_slice_end_date": _parse_iso_date(state.get("last_completed_slice_end_date")), "last_error": "", "failed_stage": "", "completed_at": None})
    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=180)
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
            current_operation = "fetching_raw"
            fetch_ranges = _build_fetch_ranges_for_slice(company_name, slice_start=current_day, slice_end=current_day, today=end_date)
            if fetch_ranges and not ticker:
                ticker = _resolve_company_ticker(company_name)
            if fetch_ranges and not ticker:
                _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "failed", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "analysis_started": True, "analysis_completed": False, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "last_error": "No valid ticker available for company warm-up.", "failed_stage": "fetching_raw", "completed_at": datetime.now(timezone.utc)})
                logger.warning("Company warm-up aborted: company=%s no valid ticker", company_name)
                return
            _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "running", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": retries, "last_error": "", "failed_stage": "", "analysis_started": True, "analysis_completed": False})
            try:
                current_operation = "fetching_raw"
                for fetch_start, fetch_end in fetch_ranges:
                    raw_items = finnhub_source.fetch_news(company_name=ticker, start_date=fetch_start.isoformat(), end_date=fetch_end.isoformat())
                    fetched_total += len(raw_items)
                    raw_articles = _news_items_from_provider(company_name, _tag_source(raw_items, "finnhub"), end_date=fetch_end, analyzed=False)
                    _store_articles(raw_articles, llm_model=model, output_language=output_language)
                    raw_stored_count += len(raw_articles)
                current_operation = "filtering_news"
                kept_count = _filter_company_news_range_raw(company_name=company_name, start_date=current_day, end_date=current_day, provider=provider, llm_model=model)
                filtered_kept_count += kept_count
                _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "running", "current_stage": "building_reports", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": 0, "analysis_started": True, "analysis_completed": False})
                current_operation = "generating_daily_report"
                generate_company_daily_report(company_name, target_date=current_day, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language)
                current_operation = "refreshing_daily_clusters"
                refresh_company_daily_clusters(company_name, target_date=current_day, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language)
                if current_day.weekday() == 4:
                    current_operation = "generating_weekly_report"
                    generate_weekly_report(company_name, start_date=current_day - timedelta(days=6), end_date=current_day, output_language=output_language, provider_name=provider_name, model=model)
                completed_slices += 1
                last_completed_slice_end = current_day
                _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "running", "current_stage": "building_reports", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": None, "current_slice_end_date": None, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": 0, "analysis_started": True, "analysis_completed": False})
                break
            except Exception as exc:
                if current_operation != "fetching_raw":
                    _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "failed", "current_stage": current_operation, "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": 0, "last_error": str(exc), "failed_stage": current_operation, "analysis_started": True, "analysis_completed": False, "completed_at": datetime.now(timezone.utc)})
                    logger.exception("Company warm-up stopped without retry after paid/analysis stage failed: company=%s day=%s stage=%s", company_name, current_day.isoformat(), current_operation)
                    return
                retries += 1
                is_rate_limit = "429" in str(exc) or "rate limit" in str(exc).lower()
                _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "partial" if retries >= DEFAULT_STORY_WARMUP_MAX_RETRIES else "running", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": retries, "last_retry_at": datetime.now(timezone.utc), "last_error": str(exc), "failed_stage": "fetching_raw", "analysis_started": True, "analysis_completed": False})
                if retries >= DEFAULT_STORY_WARMUP_MAX_RETRIES:
                    if is_rate_limit:
                        _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "failed", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": current_day, "current_slice_end_date": current_day, "last_completed_slice_end_date": last_completed_slice_end, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "retry_count": retries, "last_retry_at": datetime.now(timezone.utc), "last_error": f"Warm-up stopped after repeated rate limiting: {exc}", "failed_stage": "fetching_raw", "analysis_started": True, "analysis_completed": False, "completed_at": datetime.now(timezone.utc)})
                        return
                    raise
                if is_rate_limit:
                    pytime.sleep(DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC)
                    continue
                raise

    if _count_company_raw_for_range(company_name, start_date, end_date) <= 0:
        _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "failed", "current_stage": "fetching_raw", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": completed_slices, "current_slice_start_date": None, "current_slice_end_date": None, "last_completed_slice_end_date": last_completed_slice_end, "analysis_started": True, "analysis_completed": False, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "last_error": "Warm-up fetched zero news items. Check the company ticker and rebuild warm-up.", "failed_stage": "fetching_raw", "completed_at": datetime.now(timezone.utc)})
        logger.warning("Company warm-up failed: company=%s fetched zero raw news", company_name)
        return

    _upsert_story_warmup_state(company_name, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, updates={"job_state": "completed", "current_stage": "done", "window_days": safe_warmup_days, "slice_days": safe_slice_days, "window_start_date": start_date, "window_end_date": end_date, "total_slices": len(run_days), "completed_slices": len(run_days), "current_slice_start_date": None, "current_slice_end_date": None, "last_completed_slice_end_date": end_date, "analysis_started": True, "analysis_completed": True, "raw_fetched_count": fetched_total, "raw_stored_count": raw_stored_count, "filtered_kept_count": filtered_kept_count, "ongoing_story_count": 0, "finished_story_count": 0, "last_error": "", "failed_stage": "", "completed_at": datetime.now(timezone.utc)})
