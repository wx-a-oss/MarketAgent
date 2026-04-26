"""Market story state, warmup, and incremental routing helpers."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from market_agent.analysis.company.news.db import ensure_database_schema, get_connection
from market_agent.analysis.company.news.service import (
    _build_output_language_line,
    _build_company_story_warmup_consolidation_prompt,
    _normalize_story_warmup_groups,
    _parse_json_object,
)
from market_agent.llms.news.registry import get_news_provider
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    TBL_MARKET_NEWS_DAILY_CLUSTER,
    TBL_MARKET_NEWS_RAW,
    TBL_MARKET_STORY_EVENT,
    TBL_MARKET_STORY_STATE,
    TBL_MARKET_STORY_UPDATE,
    TBL_MARKET_STORY_WARMUP_STATE,
)

from market_agent.workflows.market_news import (
    DEFAULT_MARKET_PROVIDER,
    DEFAULT_MARKET_MODEL,
    _current_app_date,
    _has_market_raw_for_day,
    _get_market_raw_coverage,
    _upsert_market_news_raw,
    refresh_market_news_for_range,
    generate_market_daily_report,
    list_market_raw_news,
)

DEFAULT_MARKET_STORY_WARMUP_DAYS = 14
DEFAULT_MARKET_STORY_WARMUP_SLICE_DAYS = 10
MARKET_STORY_PROMPT_JSON_LIMIT = max(
    10000, int(os.getenv("MARKET_STORY_PROMPT_JSON_LIMIT", "30000").strip() or "30000")
)
MARKET_STORY_CHUNK_SIZE = max(
    5, int(os.getenv("MARKET_STORY_CHUNK_SIZE", "15").strip() or "15")
)
MARKET_STORY_HEADLINE_MAX_CHARS = 240
MARKET_STORY_SUMMARY_MAX_CHARS = 800

logger = logging.getLogger("uvicorn.error")


# Reference to the re-export shim so that monkeypatches on market_updates
# (which is what tests use) are visible to code in this sub-module.
def _shim():
    return sys.modules.get('market_agent.workflows.market_updates') or sys.modules[__name__]


def get_market_story_overview(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    ensure_database_schema()
    warmup = get_market_story_warmup_state()
    latest_story_date = _get_latest_market_story_date(
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    stories = list_market_story_states(
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    ongoing = [
        story for story in stories
        if str(story.get("story_status") or "").strip().lower() not in {"resolved", "finished", "closed"}
    ]
    finished = [
        story for story in stories
        if str(story.get("story_status") or "").strip().lower() in {"resolved", "finished", "closed"}
    ]
    return {
        "warmup": warmup,
        "latest_story_date": latest_story_date,
        "stories": stories,
        "ongoing_stories": ongoing,
        "finished_stories": finished,
    }


def get_market_story_warmup_state() -> Dict[str, Any]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_MARKET_STORY_WARMUP_STATE}
                WHERE job_key = 'global'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if not row:
        return {
            "job_key": "global",
            "job_state": "not_started",
            "current_stage": "idle",
            "raw_fetched_count": 0,
            "raw_stored_count": 0,
            "filtered_kept_count": 0,
            "ongoing_story_count": 0,
            "finished_story_count": 0,
        }
    return {
        "job_key": row["job_key"],
        "job_state": row["job_state"],
        "current_stage": row["current_stage"],
        "warmup_window_start": row["warmup_window_start"].isoformat() if row["warmup_window_start"] else None,
        "warmup_window_end": row["warmup_window_end"].isoformat() if row["warmup_window_end"] else None,
        "raw_fetched_count": int(row["raw_fetched_count"] or 0),
        "raw_stored_count": int(row["raw_stored_count"] or 0),
        "filtered_kept_count": int(row["filtered_kept_count"] or 0),
        "ongoing_story_count": int(row["ongoing_story_count"] or 0),
        "finished_story_count": int(row["finished_story_count"] or 0),
        "retry_count": int(row["retry_count"] or 0),
        "last_error": row["last_error"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def start_market_story_warmup(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = DEFAULT_MARKET_STORY_WARMUP_DAYS,
    slice_days: int = DEFAULT_MARKET_STORY_WARMUP_SLICE_DAYS,
) -> Dict[str, Any]:
    state = _shim().get_market_story_warmup_state()
    if state.get("job_state") == "completed":
        logger.info("Market story warmup skipped: already completed.")
        return state
    target_date = _shim()._current_app_date()
    start_date = target_date - timedelta(days=max(1, int(warmup_days)) - 1)
    logger.info(
        "Market story warmup started: window=%s..%s provider=%s model=%s prompt=%s language=%s slice_days=%s",
        start_date.isoformat(),
        target_date.isoformat(),
        provider_name,
        model,
        prompt_style,
        output_language,
        max(1, int(slice_days)),
    )
    _shim()._upsert_market_story_warmup_state(
        job_state="running",
        current_stage="fetching_raw",
        warmup_window_start=start_date,
        warmup_window_end=target_date,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        last_error=None,
    )
    existing_stats = _shim()._get_market_raw_coverage(start_date=start_date, end_date=target_date)
    raw_count = int(existing_stats["item_count"])
    stored_count = int(existing_stats["item_count"])
    missing_dates = existing_stats["missing_dates"]
    logger.info(
        "Market story warmup raw coverage: window=%s..%s stored_items=%s covered_days=%s missing_days=%s",
        start_date.isoformat(),
        target_date.isoformat(),
        raw_count,
        int(existing_stats["covered_day_count"]),
        len(missing_dates),
    )
    if missing_dates:
        slice_size = max(1, int(slice_days))
        current = start_date
        while current <= target_date:
            slice_end = min(current + timedelta(days=slice_size - 1), target_date)
            if any(current <= missing_date <= slice_end for missing_date in missing_dates):
                logger.info(
                    "Market story warmup fetching raw slice: %s..%s",
                    current.isoformat(),
                    slice_end.isoformat(),
                )
                fetched = _shim().refresh_market_news_for_range(start_date=current, end_date=slice_end)
                raw_count += int(fetched.get("fetched_total", 0))
                stored_count = int(_shim()._get_market_raw_coverage(start_date=start_date, end_date=target_date)["item_count"])
                logger.info(
                    "Market story warmup fetched raw slice: %s..%s fetched=%s stored_window_total=%s",
                    current.isoformat(),
                    slice_end.isoformat(),
                    int(fetched.get("fetched_total", 0)),
                    stored_count,
                )
            _shim()._upsert_market_story_warmup_state(
                job_state="running",
                current_stage="fetching_raw",
                warmup_window_start=start_date,
                warmup_window_end=target_date,
                raw_fetched_count=raw_count,
                raw_stored_count=stored_count,
                filtered_kept_count=stored_count,
            )
            current = slice_end + timedelta(days=1)
    else:
        logger.info(
            "Market story warmup reusing stored raw news for full window: %s..%s",
            start_date.isoformat(),
            target_date.isoformat(),
        )
        _shim()._upsert_market_story_warmup_state(
            job_state="running",
            current_stage="fetching_raw",
            warmup_window_start=start_date,
            warmup_window_end=target_date,
            raw_fetched_count=raw_count,
            raw_stored_count=stored_count,
            filtered_kept_count=stored_count,
        )
    _shim()._upsert_market_story_warmup_state(
        job_state="running",
        current_stage="building_clusters",
        warmup_window_start=start_date,
        warmup_window_end=target_date,
        raw_fetched_count=raw_count,
        raw_stored_count=stored_count,
        filtered_kept_count=stored_count,
    )
    current = start_date
    cluster_total = 0
    while current <= target_date:
        _shim().generate_market_daily_report(
            target_date=current,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        cluster_stats = _shim().refresh_market_daily_clusters(
            target_date=current,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        cluster_total += int(cluster_stats.get("cluster_count", 0))
        current += timedelta(days=1)
    _shim()._upsert_market_story_warmup_state(
        job_state="running",
        current_stage="analyzing_stories",
        warmup_window_start=start_date,
        warmup_window_end=target_date,
        raw_fetched_count=raw_count,
        raw_stored_count=stored_count,
        filtered_kept_count=stored_count,
    )
    result = _shim()._generate_market_story_map(
        start_date=start_date,
        end_date=target_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    logger.info(
        "Market story warmup completed: window=%s..%s ongoing=%s finished=%s items=%s",
        start_date.isoformat(),
        target_date.isoformat(),
        int(result.get("ongoing_story_count", 0)),
        int(result.get("finished_story_count", 0)),
        int(result.get("cluster_count", 0)),
    )
    _shim()._upsert_market_story_warmup_state(
        job_state="completed",
        current_stage="done",
        warmup_window_start=start_date,
        warmup_window_end=target_date,
        raw_fetched_count=raw_count,
        raw_stored_count=stored_count,
        filtered_kept_count=stored_count,
        ongoing_story_count=int(result.get("ongoing_story_count", 0)),
        finished_story_count=int(result.get("finished_story_count", 0)),
        completed_at=datetime.now(timezone.utc),
        last_error=None,
    )
    return _shim().get_market_story_warmup_state()


def list_market_story_states(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_MARKET_STORY_STATE}
                WHERE provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                ORDER BY importance_rank ASC, updated_at DESC, id DESC
                """,
                (provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [_row_to_market_story_state(row) for row in rows]


def refresh_market_story_states(
    *,
    as_of_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    from market_agent.workflows.market_clusters import list_market_daily_clusters

    existing = list_market_story_states(
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    clusters = list_market_daily_clusters(
        target_date=as_of_date,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not clusters:
        return {
            "generated": False,
            "routed_cluster_count": 0,
            "updated_story_count": 0,
            "new_story_count": 0,
            "ongoing_story_count": len([s for s in existing if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]),
            "finished_story_count": len([s for s in existing if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]),
            "input_item_count": 0,
            "prompt_char_count": 0,
            "output_char_count": 0,
        }
    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=240)
    routing_prompt = _build_market_story_routing_prompt(
        as_of_date=as_of_date,
        output_language=output_language,
        existing_stories=existing,
        clusters=clusters,
    )
    routing_payload = _parse_json_object(provider.generate_text(prompt=routing_prompt)) or {}
    routed = _normalize_market_story_routing_result(
        existing_stories=existing,
        clusters=clusters,
        payload=routing_payload,
    )
    applied = _apply_market_story_actions(
        as_of_date=as_of_date,
        provider=provider,
        existing_stories=existing,
        routed=routed,
        output_language=output_language,
    )
    _persist_market_story_refresh(
        as_of_date=as_of_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"routing_prompt": routing_prompt, "routing_result": routed, "clusters": clusters},
        raw_output=json.dumps({"routing": routing_payload, "applied": applied["raw_outputs"]}, ensure_ascii=False),
        stories=applied["stories"],
    )
    return {
        "generated": True,
        "routed_cluster_count": len(clusters),
        "updated_story_count": len(applied["updated_story_keys"]),
        "new_story_count": len(applied["new_story_keys"]),
        "ongoing_story_count": len([s for s in applied["stories"] if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]),
        "finished_story_count": len([s for s in applied["stories"] if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]),
        "input_item_count": len(clusters),
        "prompt_char_count": len(routing_prompt),
        "output_char_count": len(json.dumps({"routing": routing_payload, "applied": applied["raw_outputs"]}, ensure_ascii=False)),
    }


def refresh_market_story_backlog(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT cluster_date
                FROM {TBL_MARKET_NEWS_DAILY_CLUSTER}
                WHERE provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY cluster_date ASC
                """,
                (provider_name, prompt_style, output_language),
            )
            cluster_dates = [row["cluster_date"] for row in cur.fetchall() if row["cluster_date"]]
            cur.execute(
                f"""
                SELECT MAX(as_of_date) AS last_applied_date
                FROM {TBL_MARKET_STORY_UPDATE}
                WHERE provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    last_applied = row["last_applied_date"] if row else None
    backlog_dates = [item for item in cluster_dates if last_applied is None or item > last_applied]
    if not backlog_dates:
        return {
            "generated": False,
            "no_op": True,
            "first_backlog_date": last_applied.isoformat() if last_applied else "",
            "last_backlog_date": last_applied.isoformat() if last_applied else "",
            "backlog_day_count": 0,
            "routed_cluster_count": 0,
            "updated_story_count": 0,
            "new_story_count": 0,
            "input_item_count": 0,
            "prompt_char_count": 0,
            "output_char_count": 0,
        }
    aggregate = {
        "generated": True,
        "no_op": False,
        "first_backlog_date": backlog_dates[0].isoformat(),
        "last_backlog_date": backlog_dates[-1].isoformat(),
        "backlog_day_count": len(backlog_dates),
        "routed_cluster_count": 0,
        "updated_story_count": 0,
        "new_story_count": 0,
        "input_item_count": 0,
        "prompt_char_count": 0,
        "output_char_count": 0,
    }
    for target_date in backlog_dates:
        stats = refresh_market_story_states(
            as_of_date=target_date,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        aggregate["routed_cluster_count"] += int(stats.get("routed_cluster_count", 0))
        aggregate["updated_story_count"] += int(stats.get("updated_story_count", 0))
        aggregate["new_story_count"] += int(stats.get("new_story_count", 0))
        aggregate["input_item_count"] += int(stats.get("input_item_count", 0))
        aggregate["prompt_char_count"] += int(stats.get("prompt_char_count", 0))
        aggregate["output_char_count"] += int(stats.get("output_char_count", 0))
    return aggregate


def update_market_story_status(
    *,
    story_key: str,
    story_status: str,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TBL_MARKET_STORY_STATE}
                SET story_status = %s, updated_at = NOW()
                WHERE story_key = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                """,
                (story_status, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def update_market_story_priority(
    *,
    story_key: str,
    priority: str,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TBL_MARKET_STORY_STATE}
                SET priority = %s, updated_at = NOW()
                WHERE story_key = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                  AND is_active = TRUE
                """,
                (priority, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def create_market_story_from_news(
    *,
    target_date: date,
    story_title: str,
    news_item: Dict[str, Any],
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    title = str(story_title or news_item.get("headline") or "").strip()
    if not title:
        return None
    existing = list_market_story_states(
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    story_key = _normalize_market_story_key("", fallback_title=title, fallback_index=len(existing))
    story = _normalize_market_story_record(
        {
            "story_key": story_key,
            "story_title": title,
            "story_summary": str(news_item.get("summary") or news_item.get("headline") or "").strip(),
            "importance_rank": len(existing) + 1,
            "story_status": "ongoing",
            "priority": "normal",
            "timeline_items": [
                {
                    "date": target_date.isoformat(),
                    "label": str(news_item.get("headline") or title).strip(),
                    "summary": str(news_item.get("summary") or "").strip(),
                }
            ],
            "future_and_impact": [],
            "evidence": [
                {
                    "news_title": str(news_item.get("headline") or title).strip(),
                    "news_date_time": str(news_item.get("datetime_text") or target_date.isoformat()),
                    "news_source_link": str(news_item.get("url") or "").strip(),
                    "summary": str(news_item.get("summary") or "").strip(),
                }
            ],
            "change_log": ["Created manually from market news."],
        }
    )
    if not story:
        return None
    _persist_market_story_refresh(
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


def attach_news_to_market_story(
    *,
    target_date: date,
    story_key: str,
    news_item: Dict[str, Any],
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> bool:
    stories = list_market_story_states(
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
                "label": str(news_item.get("headline") or "").strip() or next_story.get("story_title"),
                "summary": str(news_item.get("summary") or "").strip(),
            }
        )
        evidence = list(next_story.get("evidence") or [])
        evidence.append(
            {
                "news_title": str(news_item.get("headline") or "").strip(),
                "news_date_time": str(news_item.get("datetime_text") or target_date.isoformat()),
                "news_source_link": str(news_item.get("url") or "").strip(),
                "summary": str(news_item.get("summary") or "").strip(),
            }
        )
        change_log = list(next_story.get("change_log") or [])
        change_log.append("Attached manually from market news.")
        next_story["timeline_items"] = timeline_items
        next_story["evidence"] = evidence
        next_story["change_log"] = change_log
        next_story["story_status"] = "ongoing"
        updated.append(next_story)
    if not matched:
        return False
    _persist_market_story_refresh(
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


def _get_latest_market_story_date(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> str:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(as_of_date) AS latest_story_date
                FROM {TBL_MARKET_STORY_UPDATE}
                WHERE provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    latest = row["latest_story_date"] if row else None
    return latest.isoformat() if latest else ""


def _generate_market_story_map(
    *,
    start_date: date,
    end_date: date,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    from market_agent.workflows.market_clusters import _build_market_story_cluster_input_items

    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=240)
    items = _build_market_story_cluster_input_items(
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    logger.info(
        "Market story map generation started: window=%s..%s clusters=%s provider=%s model=%s prompt=%s language=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        len(items),
        provider_name,
        model,
        prompt_style,
        output_language,
    )
    prompt = _build_market_story_prompt(
        start_date=start_date,
        end_date=end_date,
        output_language=output_language,
        items=items,
    )
    payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    grouped = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    normalized = [
        item
        for item in (_normalize_market_story_record(row) for row in grouped if isinstance(row, dict))
        if item
    ]
    _persist_market_story_refresh(
        as_of_date=end_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"clusters": items, "window_start": start_date.isoformat(), "window_end": end_date.isoformat(), "mode": "warmup"},
        raw_output=json.dumps(payload, ensure_ascii=False),
        stories=normalized,
    )
    logger.info(
        "Market story map generation completed: window=%s..%s ongoing=%s finished=%s active=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        len([s for s in normalized if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]),
        len([s for s in normalized if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]),
        len(normalized),
    )
    return {
        "ongoing_story_count": len([s for s in normalized if str(s.get("story_status") or "").lower() not in {"finished", "resolved", "closed"}]),
        "finished_story_count": len([s for s in normalized if str(s.get("story_status") or "").lower() in {"finished", "resolved", "closed"}]),
        "cluster_count": len(items),
    }


def _build_market_story_input_items(*, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT news_date, news_date_time, headline, source, source_tag, news_url, summary
                FROM {TBL_MARKET_NEWS_RAW}
                WHERE news_date >= %s
                  AND news_date <= %s
                ORDER BY COALESCE(news_date_time, (news_date::timestamp)) ASC, id ASC
                """,
                (start_date, end_date),
            )
            rows = cur.fetchall()
    return [
        {
            "news_date_time": row["news_date_time"].isoformat() if row["news_date_time"] else datetime.combine(row["news_date"], datetime.min.time()).isoformat(),
            "news_title": _truncate_market_story_text(row["headline"], MARKET_STORY_HEADLINE_MAX_CHARS),
            "news_source": row["source"],
            "news_source_link": row["news_url"],
            "summary": _truncate_market_story_text(row["summary"] or "", MARKET_STORY_SUMMARY_MAX_CHARS),
            "source_tag": row["source_tag"] or "",
        }
        for row in rows
    ]


def _build_market_story_prompt(*, start_date: date, end_date: date, output_language: str, items: List[Dict[str, Any]]) -> str:
    language_line = _build_output_language_line(output_language)
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        f"You are building the initial market story map from daily market clusters between {start_date.isoformat()} and {end_date.isoformat()}.\n"
        "Find the distinct market storylines across the period.\n"
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
        '      "timeline_items": [{"date": "2026-03-10", "label": "event", "summary": "..." }],\n'
        '      "future_and_impact": [{"scenario": "...", "probability": "low|medium|high", "impact": "..."}],\n'
        '      "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '      "change_log": ["..."]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Daily market clusters JSON:\n{items_json}\n"
    )


def _generate_market_story_payload(
    *,
    provider: Any,
    provider_name: str,
    model: str,
    start_date: date,
    end_date: date,
    output_language: str,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    items = list(items)
    logger.info(
        "Market story payload preparation: items=%s prompt_json_chars=%s chunk_limit=%s chunk_size=%s",
        len(items),
        len(json.dumps(items, ensure_ascii=False)),
        MARKET_STORY_PROMPT_JSON_LIMIT,
        MARKET_STORY_CHUNK_SIZE,
    )
    prompt = _build_market_story_prompt(
        start_date=start_date,
        end_date=end_date,
        output_language=output_language,
        items=items,
    )
    payload: Dict[str, Any]
    if len(json.dumps(items, ensure_ascii=False)) <= MARKET_STORY_PROMPT_JSON_LIMIT:
        logger.info("Market story payload mode=single_request items=%s", len(items))
        raw_output = provider.generate_text(prompt=prompt)
        payload = _parse_json_object(raw_output) or {}
    else:
        chunk_results: List[Dict[str, Any]] = []
        chunk_count = (len(items) + MARKET_STORY_CHUNK_SIZE - 1) // MARKET_STORY_CHUNK_SIZE
        logger.info("Market story payload mode=chunked items=%s chunk_count=%s", len(items), chunk_count)
        for chunk_index, offset in enumerate(range(0, len(items), MARKET_STORY_CHUNK_SIZE), start=1):
            chunk = items[offset : offset + MARKET_STORY_CHUNK_SIZE]
            logger.info(
                "Market story chunk %s/%s: items=%s range=%s..%s",
                chunk_index,
                chunk_count,
                len(chunk),
                offset,
                offset + len(chunk) - 1,
            )
            chunk_prompt = _build_market_story_prompt(
                start_date=start_date,
                end_date=end_date,
                output_language=output_language,
                items=chunk,
            )
            chunk_output = provider.generate_text(prompt=chunk_prompt)
            chunk_results.append(_parse_json_object(chunk_output) or {})
        logger.info("Market story consolidation started: chunk_count=%s", len(chunk_results))
        merge_prompt = _build_company_story_warmup_consolidation_prompt(
            "the market",
            start_date=start_date,
            end_date=end_date,
            output_language=output_language,
            chunk_results=chunk_results,
        )
        raw_output = provider.generate_text(prompt=merge_prompt)
        payload = _parse_json_object(raw_output) or {}
        logger.info("Market story consolidation completed: chunk_count=%s", len(chunk_results))
    return payload


def _truncate_market_story_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _upsert_market_story_warmup_state(**kwargs: Any) -> None:
    state = get_market_story_warmup_state()
    values = {
        "job_state": kwargs.get("job_state", state.get("job_state", "not_started")),
        "current_stage": kwargs.get("current_stage", state.get("current_stage", "idle")),
        "warmup_window_start": kwargs.get("warmup_window_start"),
        "warmup_window_end": kwargs.get("warmup_window_end"),
        "raw_fetched_count": int(kwargs.get("raw_fetched_count", state.get("raw_fetched_count", 0))),
        "raw_stored_count": int(kwargs.get("raw_stored_count", state.get("raw_stored_count", 0))),
        "filtered_kept_count": int(kwargs.get("filtered_kept_count", state.get("filtered_kept_count", 0))),
        "ongoing_story_count": int(kwargs.get("ongoing_story_count", state.get("ongoing_story_count", 0))),
        "finished_story_count": int(kwargs.get("finished_story_count", state.get("finished_story_count", 0))),
        "retry_count": int(kwargs.get("retry_count", state.get("retry_count", 0))),
        "last_error": kwargs.get("last_error", state.get("last_error")),
        "started_at": kwargs.get("started_at", state.get("started_at")),
        "completed_at": kwargs.get("completed_at", state.get("completed_at")),
    }
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_STORY_WARMUP_STATE}
                    (job_key, job_state, current_stage, warmup_window_start, warmup_window_end,
                     raw_fetched_count, raw_stored_count, filtered_kept_count,
                     ongoing_story_count, finished_story_count, retry_count,
                     last_error, started_at, completed_at, updated_at)
                VALUES
                    ('global', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (job_key)
                DO UPDATE SET
                    job_state = EXCLUDED.job_state,
                    current_stage = EXCLUDED.current_stage,
                    warmup_window_start = EXCLUDED.warmup_window_start,
                    warmup_window_end = EXCLUDED.warmup_window_end,
                    raw_fetched_count = EXCLUDED.raw_fetched_count,
                    raw_stored_count = EXCLUDED.raw_stored_count,
                    filtered_kept_count = EXCLUDED.filtered_kept_count,
                    ongoing_story_count = EXCLUDED.ongoing_story_count,
                    finished_story_count = EXCLUDED.finished_story_count,
                    retry_count = EXCLUDED.retry_count,
                    last_error = EXCLUDED.last_error,
                    started_at = COALESCE({TBL_MARKET_STORY_WARMUP_STATE}.started_at, EXCLUDED.started_at),
                    completed_at = EXCLUDED.completed_at,
                    updated_at = NOW()
                """,
                (
                    values["job_state"],
                    values["current_stage"],
                    values["warmup_window_start"],
                    values["warmup_window_end"],
                    values["raw_fetched_count"],
                    values["raw_stored_count"],
                    values["filtered_kept_count"],
                    values["ongoing_story_count"],
                    values["finished_story_count"],
                    values["retry_count"],
                    values["last_error"],
                    values["started_at"],
                    values["completed_at"],
                ),
            )
        conn.commit()


def _upsert_market_story_state_batch(
    *,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    stories: List[Dict[str, Any]],
) -> None:
    with _shim().get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TBL_MARKET_STORY_STATE}
                WHERE provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s AND is_active = FALSE
                """,
                (provider_name, prompt_style, output_language),
            )
            cur.execute(
                f"""
                UPDATE {TBL_MARKET_STORY_STATE}
                SET is_active = FALSE, updated_at = NOW()
                WHERE provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s AND is_active = TRUE
                """,
                (provider_name, prompt_style, output_language),
            )
            for item in stories:
                cur.execute(
                    f"""
                    INSERT INTO {TBL_MARKET_STORY_STATE}
                        (story_key, story_title, importance_rank, story_status, confidence,
                         story_summary, priority, happened_text, happening_text, next_text,
                         timeline_json, future_impact_json, evidence_json, change_log_json,
                         provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, is_active,
                         last_event_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                            %s, %s, %s, %s, TRUE, NOW(), NOW(), NOW())
                    ON CONFLICT (story_key, provider, prompt_style, output_language, is_active)
                    DO UPDATE SET
                        story_title = EXCLUDED.story_title,
                        importance_rank = EXCLUDED.importance_rank,
                        story_status = EXCLUDED.story_status,
                        confidence = EXCLUDED.confidence,
                        story_summary = EXCLUDED.story_summary,
                        priority = EXCLUDED.priority,
                        happened_text = EXCLUDED.happened_text,
                        happening_text = EXCLUDED.happening_text,
                        next_text = EXCLUDED.next_text,
                        timeline_json = EXCLUDED.timeline_json,
                        future_impact_json = EXCLUDED.future_impact_json,
                        evidence_json = EXCLUDED.evidence_json,
                        change_log_json = EXCLUDED.change_log_json,
                        model = EXCLUDED.model,
                        updated_at = NOW(),
                        last_event_at = NOW()
                    """,
                    (
                        item["story_key"],
                        item["story_title"],
                        item["importance_rank"],
                        item["story_status"],
                        item.get("confidence", 0.5),
                        item.get("story_summary", ""),
                        item.get("priority", "normal"),
                        item.get("happened_text", ""),
                        item.get("happening_text", ""),
                        item.get("next_text", ""),
                        json.dumps(item.get("timeline_items") or [], ensure_ascii=False),
                        json.dumps(item.get("future_and_impact") or [], ensure_ascii=False),
                        json.dumps(item.get("evidence") or [], ensure_ascii=False),
                        json.dumps(item.get("change_log") or [], ensure_ascii=False),
                        provider_name,
                        model,
                        prompt_style,
                        output_language,
                    ),
                )
        conn.commit()


def _insert_market_story_update(
    *,
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
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_STORY_UPDATE}
                    (as_of_date, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                     input_payload, raw_output, stories_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, NOW())
                """,
                (
                    as_of_date,
                    provider_name,
                    model,
                    prompt_style,
                    output_language,
                    json.dumps(input_payload, ensure_ascii=False),
                    raw_output,
                    json.dumps(stories, ensure_ascii=False),
                ),
            )
        conn.commit()


def _persist_market_story_refresh(
    *,
    as_of_date: date,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
    raw_output: str,
    stories: List[Dict[str, Any]],
) -> None:
    _upsert_market_story_state_batch(
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        stories=stories,
    )
    _insert_market_story_update(
        as_of_date=as_of_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload=input_payload,
        raw_output=raw_output,
        stories=stories,
    )
    _replace_market_story_events(stories)


def _replace_market_story_events(stories: List[Dict[str, Any]]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TBL_MARKET_STORY_EVENT}")
            for story in stories:
                for evidence in story.get("evidence") or []:
                    title = str(evidence.get("news_title") or story["story_title"]).strip()
                    if not title:
                        continue
                    event_date = None
                    raw_dt = evidence.get("news_date_time")
                    if raw_dt:
                        try:
                            event_date = datetime.fromisoformat(str(raw_dt))
                        except ValueError:
                            event_date = None
                    cur.execute(
                        f"""
                        INSERT INTO {TBL_MARKET_STORY_EVENT}
                            (story_key, event_date, event_type, event_title, event_summary, evidence_json, created_at)
                        VALUES (%s, %s, 'evidence', %s, %s, %s::jsonb, NOW())
                        """,
                        (
                            story["story_key"],
                            event_date,
                            title,
                            str(evidence.get("summary") or "").strip() or None,
                            json.dumps([evidence], ensure_ascii=False),
                        ),
                    )
        conn.commit()


def _normalize_market_story_key(value: Any, *, fallback_title: str = "", fallback_index: int = 0) -> str:
    text = str(value or "").strip().lower()
    if not text:
        text = str(fallback_title or "").strip().lower()
    text = "".join(ch if ch.isalnum() else "-" for ch in text)
    text = "-".join(part for part in text.split("-") if part)
    if not text:
        text = f"market-story-{fallback_index + 1}"
    return text[:96]


def _normalize_market_story_record(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = str(item.get("story_title") or "").strip()
    if not title:
        return None
    try:
        rank = int(item.get("importance_rank") or 999)
    except (TypeError, ValueError):
        rank = 999
    try:
        confidence = float(item.get("confidence") or 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(confidence, 1.0))
    timeline_items = item.get("timeline_items") if isinstance(item.get("timeline_items"), list) else []
    future_items = item.get("future_and_impact") if isinstance(item.get("future_and_impact"), list) else []
    return {
        "story_key": _normalize_market_story_key(item.get("story_key"), fallback_title=title, fallback_index=rank),
        "story_title": title,
        "story_summary": str(item.get("story_summary") or "").strip(),
        "importance_rank": rank,
        "story_status": str(item.get("story_status") or "ongoing").strip().lower(),
        "priority": str(item.get("priority") or "normal").strip().lower() or "normal",
        "confidence": confidence,
        "timeline_items": [entry for entry in timeline_items if isinstance(entry, dict)],
        "future_and_impact": [entry for entry in future_items if isinstance(entry, dict)],
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "change_log": item.get("change_log") if isinstance(item.get("change_log"), list) else [],
        "happened_text": str(item.get("happened_text") or "").strip(),
        "happening_text": str(item.get("happening_text") or "").strip(),
        "next_text": str(item.get("next_text") or "").strip(),
    }


def _build_market_story_context(stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "story_key": item.get("story_key"),
            "story_title": item.get("story_title"),
            "story_summary": item.get("story_summary") or "",
            "priority": item.get("priority") or "normal",
            "story_status": item.get("story_status") or "ongoing",
        }
        for item in stories
        if isinstance(item, dict)
    ]


def _build_market_story_routing_prompt(
    *,
    as_of_date: date,
    output_language: str,
    existing_stories: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
) -> str:
    payload_json = json.dumps(
        {"existing_stories": _build_market_story_context(existing_stories), "daily_clusters": clusters},
        ensure_ascii=False,
        indent=2,
    )
    language_line = _build_output_language_line(output_language)
    return (
        f"Route market daily clusters into the live market story map as of {as_of_date.isoformat()}.\n"
        "Assign each cluster to exactly one of: existing_story, new_story, ignore.\n"
        "Use only best-fit assignment. Keep story boundaries clean.\n"
        "High priority stories should be matched carefully.\n"
        "Return JSON only.\n"
        f"{language_line}"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "cluster_key": "cluster-key",\n'
        '      "action": "existing_story|new_story|ignore",\n'
        '      "story_key": "existing story key",\n'
        '      "new_story_title": "title only if new_story",\n'
        '      "reason": "brief note"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _normalize_market_story_routing_result(
    *,
    existing_stories: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    existing_by_key = {str(item.get("story_key") or "").strip(): item for item in existing_stories if str(item.get("story_key") or "").strip()}
    clusters_by_key = {str(item.get("cluster_key") or "").strip(): item for item in clusters if str(item.get("cluster_key") or "").strip()}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    assigned: set[str] = set()
    existing_groups: Dict[str, List[Dict[str, Any]]] = {}
    new_groups: Dict[str, Dict[str, Any]] = {}
    ignored: List[Dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        cluster_key = str(item.get("cluster_key") or "").strip()
        if not cluster_key or cluster_key in assigned or cluster_key not in clusters_by_key:
            continue
        assigned.add(cluster_key)
        cluster = clusters_by_key[cluster_key]
        action = str(item.get("action") or "").strip().lower()
        if action == "existing_story":
            story_key = str(item.get("story_key") or "").strip()
            if story_key in existing_by_key:
                existing_groups.setdefault(story_key, []).append(cluster)
                continue
        if action == "new_story":
            title = str(item.get("new_story_title") or cluster.get("cluster_title") or "").strip() or cluster_key
            new_key = _normalize_market_story_key("", fallback_title=title, fallback_index=len(new_groups))
            bucket = new_groups.setdefault(new_key, {"story_key": new_key, "story_title": title, "clusters": []})
            bucket["clusters"].append(cluster)
            continue
        ignored.append({"cluster_key": cluster_key, "reason": str(item.get("reason") or "ignore").strip() or "ignore"})
    for cluster_key, cluster in clusters_by_key.items():
        if cluster_key in assigned:
            continue
        title = str(cluster.get("cluster_title") or "").strip() or cluster_key
        new_key = _normalize_market_story_key("", fallback_title=title, fallback_index=len(new_groups))
        bucket = new_groups.setdefault(new_key, {"story_key": new_key, "story_title": title, "clusters": []})
        bucket["clusters"].append(cluster)
    return {"existing_groups": existing_groups, "new_groups": list(new_groups.values()), "ignored_items": ignored}


def _build_market_existing_story_prompt(
    *,
    as_of_date: date,
    output_language: str,
    story: Dict[str, Any],
    clusters: List[Dict[str, Any]],
) -> str:
    payload_json = json.dumps({"existing_story": story, "daily_clusters": clusters}, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Update one existing market story as of {as_of_date.isoformat()}.\n"
        "Keep the same story_key. Update summary, timeline_items, and future_and_impact.\n"
        "Timeline items must be ordered chronologically.\n"
        "Future and impact must be short scenario objects with probability and impact.\n"
        "Return JSON only as {\"story\": {...}}.\n"
        f"{language_line}"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _build_market_new_story_prompt(
    *,
    as_of_date: date,
    output_language: str,
    story_key: str,
    story_title: str,
    clusters: List[Dict[str, Any]],
) -> str:
    payload_json = json.dumps({"story_key": story_key, "story_title": story_title, "daily_clusters": clusters}, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Create one new market story as of {as_of_date.isoformat()} from the assigned daily clusters.\n"
        "Build a compact summary, an ordered timeline_items list, and future_and_impact scenarios.\n"
        "Return JSON only as {\"story\": {...}}.\n"
        f"{language_line}"
        f"Inputs JSON:\n{payload_json}\n"
    )


def _normalize_market_incremental_story_item(
    payload: Dict[str, Any],
    *,
    fallback_story_key: str,
    fallback_story_title: str,
    fallback_rank: int,
    fallback_priority: str = "normal",
) -> Optional[Dict[str, Any]]:
    story = payload.get("story")
    if not isinstance(story, dict):
        return None
    return _normalize_market_story_record(
        {
            **story,
            "story_key": story.get("story_key") or fallback_story_key,
            "story_title": story.get("story_title") or fallback_story_title,
            "importance_rank": story.get("importance_rank") or fallback_rank,
            "priority": story.get("priority") or fallback_priority,
        }
    )


def _apply_market_story_actions(
    *,
    as_of_date: date,
    provider: Any,
    existing_stories: List[Dict[str, Any]],
    routed: Dict[str, Any],
    output_language: str,
) -> Dict[str, Any]:
    existing_by_key = {str(item.get("story_key") or "").strip(): item for item in existing_stories if str(item.get("story_key") or "").strip()}
    final_stories: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    updated_keys: List[str] = []
    new_keys: List[str] = []
    for story_key, story in existing_by_key.items():
        clusters = routed["existing_groups"].get(story_key) or []
        if not clusters:
            final_stories.append(story)
            continue
        prompt = _build_market_existing_story_prompt(
            as_of_date=as_of_date,
            output_language=output_language,
            story=story,
            clusters=clusters,
        )
        raw_output = provider.generate_text(prompt=prompt)
        normalized = _normalize_market_incremental_story_item(
            _parse_json_object(raw_output) or {},
            fallback_story_key=story_key,
            fallback_story_title=str(story.get("story_title") or story_key),
            fallback_rank=int(story.get("importance_rank") or 999),
            fallback_priority=str(story.get("priority") or "normal"),
        ) or story
        final_stories.append(normalized)
        updated_keys.append(story_key)
        raw_outputs.append({"type": "existing_story", "story_key": story_key, "raw_output": raw_output})
    for index, bucket in enumerate(routed["new_groups"]):
        clusters = bucket.get("clusters") if isinstance(bucket.get("clusters"), list) else []
        if not clusters:
            continue
        story_key = str(bucket.get("story_key") or "").strip()
        story_title = str(bucket.get("story_title") or "").strip() or story_key
        prompt = _build_market_new_story_prompt(
            as_of_date=as_of_date,
            output_language=output_language,
            story_key=story_key,
            story_title=story_title,
            clusters=clusters,
        )
        raw_output = provider.generate_text(prompt=prompt)
        normalized = _normalize_market_incremental_story_item(
            _parse_json_object(raw_output) or {},
            fallback_story_key=story_key,
            fallback_story_title=story_title,
            fallback_rank=len(final_stories) + index + 1,
        )
        if normalized:
            final_stories.append(normalized)
            new_keys.append(normalized["story_key"])
            raw_outputs.append({"type": "new_story", "story_key": normalized["story_key"], "raw_output": raw_output})
    final_stories = sorted(
        [item for item in (_normalize_market_story_record(row) for row in final_stories) if item],
        key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or "")),
    )
    return {"stories": final_stories, "raw_outputs": raw_outputs, "updated_story_keys": updated_keys, "new_story_keys": new_keys}


def _row_to_market_story_state(row: Dict[str, Any]) -> Dict[str, Any]:
    def _safe_json(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []
    return {
        "id": int(row["id"]),
        "story_key": row["story_key"],
        "story_title": row["story_title"],
        "story_summary": row.get("story_summary") or "",
        "importance_rank": int(row["importance_rank"] or 999),
        "story_status": row["story_status"],
        "priority": row.get("priority") or "normal",
        "confidence": float(row["confidence"] or 0.5),
        "happened_text": row["happened_text"] or "",
        "happening_text": row["happening_text"] or "",
        "next_text": row["next_text"] or "",
        "timeline_items": _safe_json(row.get("timeline_json")),
        "future_and_impact": _safe_json(row.get("future_impact_json")),
        "evidence": _safe_json(row["evidence_json"]),
        "change_log": _safe_json(row["change_log_json"]),
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
