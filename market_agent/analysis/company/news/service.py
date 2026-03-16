"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
import os
import re
import logging
import threading
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.config.models import DEFAULT_OPENAI_MODEL
from market_agent.llms.news import get_news_provider
from market_agent.analysis.company.news.db import ensure_database_schema, get_connection
from market_agent.analysis.company.news.datamodels import NewsArticle
from market_agent.analysis.company.ticker_fallbacks import resolve_company_ticker_fallback
from market_agent.datasources.finnhub import FinnhubClient
from market_agent.news_sources import get_news_source
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_STORY_KEY,
    TBL_COMPANY_NEWS_ANALYZED,
    TBL_COMPANY_NEWS_DAILY_CLUSTER,
    TBL_COMPANY_STORY_QA,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
    TBL_COMPANY_STORY_WARMUP_STATE,
)

DEFAULT_MODEL = DEFAULT_OPENAI_MODEL
DEFAULT_PROVIDER = "openai"
DEFAULT_SOURCE = "openai"
FINNHUB_AUTO_ANALYZE_LIMIT = 10
ANALYZE_DAY_BATCH_SIZE = 3
FILTER_DAY_BATCH_SIZE = 10
DEFAULT_STORY_WARMUP_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_DAYS", "10").strip() or "10")
)
DEFAULT_STORY_WARMUP_SLICE_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_SLICE_DAYS", "10").strip() or "10")
)
DEFAULT_STORY_WARMUP_MAX_RETRIES = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_MAX_RETRIES", "3").strip() or "3")
)
DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_RETRY_DELAY_SEC", "60").strip() or "60")
)
STORY_WARMUP_PROMPT_JSON_LIMIT = max(
    12000, int(os.getenv("COMPANY_STORY_WARMUP_PROMPT_JSON_LIMIT", "45000").strip() or "45000")
)
STORY_WARMUP_CHUNK_SIZE = max(
    5, int(os.getenv("COMPANY_STORY_WARMUP_CHUNK_SIZE", "25").strip() or "25")
)
COMPANY_DAILY_CLUSTER_MIN = 3
COMPANY_DAILY_CLUSTER_MAX = 8

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
                """
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "company_name": row["company_name"],
                        "ticker": _normalize_ticker(row.get("ticker")),
                    }
                )
            return rows


def add_company_to_watchlist(company_name: str) -> None:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_watchlist (company_name)
                VALUES (%s)
                ON CONFLICT (company_name) DO NOTHING
                """,
                (normalized,),
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
    if state.get("job_state") == "completed":
        return state
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
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    as_of_date,
                    window_start_date,
                    window_end_date,
                    provider,
                    model,
                    prompt_style,
                    input_payload,
                    output_text,
                    created_at
                FROM company_status_snapshot
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (company_name, provider_name, prompt_style),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "as_of_date": row["as_of_date"].isoformat(),
        "window_start_date": row["window_start_date"].isoformat(),
        "window_end_date": row["window_end_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "input_payload": row["input_payload"],
        "output_text": row["output_text"],
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


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
        return {"generated": False, "daily_report_count": 0, "weekly_report_count": 0, "elapsed_sec": 0.0}

    end_date = as_of_date or datetime.now(timezone.utc).date()
    safe_window_days = max(7, min(int(window_days), 90))
    start_date = end_date - timedelta(days=safe_window_days - 1)
    status_input = _build_company_status_input(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
    )
    if not status_input["daily_reports"] and not status_input["weekly_reports"] and not status_input["raw_news"]:
        return {
            "generated": False,
            "daily_report_count": 0,
            "weekly_report_count": 0,
            "raw_news_count": 0,
            "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
        }

    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_status_prompt(
        company_name,
        as_of_date=end_date,
        prompt_style=prompt_style,
        status_input=status_input,
        output_language=output_language,
    )
    output_text = provider.generate_text(prompt=prompt)
    _upsert_company_status_snapshot(
        company_name=company_name,
        as_of_date=end_date,
        window_start_date=start_date,
        window_end_date=end_date,
        provider=provider_name,
        model=model,
        prompt_style=prompt_style,
        input_payload={"prompt": prompt, **status_input},
        output_text=output_text,
    )
    return {
        "generated": True,
        "daily_report_count": len(status_input["daily_reports"]),
        "weekly_report_count": len(status_input["weekly_reports"]),
        "raw_news_count": len(status_input["raw_news"]),
        "elapsed_sec": round(pytime.perf_counter() - started_at, 2),
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
    output_text: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM company_status_snapshot
                WHERE company_name = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (company_name, provider, prompt_style),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE company_status_snapshot
                    SET as_of_date = %s,
                        window_start_date = %s,
                        window_end_date = %s,
                        model = %s,
                        input_payload = %s,
                        output_text = %s,
                        created_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        as_of_date,
                        window_start_date,
                        window_end_date,
                        model,
                        json.dumps(input_payload),
                        output_text,
                        existing["id"],
                    ),
                )
                cur.execute(
                    """
                    DELETE FROM company_status_snapshot
                    WHERE company_name = %s
                      AND provider = %s
                      AND prompt_style = %s
                      AND id <> %s
                    """,
                    (company_name, provider, prompt_style, existing["id"]),
                )
            else:
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
                        output_text
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        output_text,
                    ),
                )
        conn.commit()


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


def _build_company_daily_report_prompt(
    company_name: str,
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    prompt_style: str,
    output_language: str = "zh-CN",
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Please summarize all {company_name} news for {target_date.isoformat()}.\n"
        "Goal: help me quickly understand what happened to the company today, why it matters, and what to watch next.\n"
        "Requirements:\n"
        "- Ignore duplicate or near-duplicate news items.\n"
        "- Keep all material points and do not omit important company-related information.\n"
        "- Ignore points not related to this company or its market/investor outlook.\n"
        "- Rank information by importance to this company (most important first).\n"
        "- Try to open links first for fuller context. If inaccessible, use available content and best available information.\n"
        "- Use a clear layered structure that is easy to read.\n"
        "- Start with a short top summary.\n"
        "- Then list the important news items in importance order.\n"
        "- For each important news item, include exactly two bullet labels: Facts and Impact.\n"
        "- Do not add a separate watch or follow-up subsection for each item.\n"
        "- End with one final section for what investors should watch next.\n"
        "- In that final section, include concise bullet points on upcoming catalysts, risks, confirmations, or developments that may matter next.\n"
        f"{language_line}"
        f"News items JSON:\n{items_json}\n"
    )


def _build_weekly_report_input_items(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    llm_model: str,
    provider_name: str,
) -> List[Dict[str, Any]]:
    daily_reports = get_company_daily_reports_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style="simple",
    )
    if daily_reports:
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

    articles = get_company_news_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        llm_model=llm_model,
    )
    if not articles:
        return []
    items: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, datetime]] = set()
    for article in articles:
        article_key = (article.news_title, article.news_date_time)
        if article_key in seen_keys:
            continue
        seen_keys.add(article_key)
        content = _decode_llm_content(
            article.llm_analyzed_content,
            article.original_content,
        )
        content["news_title"] = article.news_title
        content["news_date_time"] = article.news_date_time.isoformat()
        content["original_content"] = article.original_content
        items.append(content)
    return items


def _build_company_status_input(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    provider_name: str,
) -> Dict[str, Any]:
    daily_reports = get_company_daily_reports_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
        prompt_style="simple",
    )

    weekly_reports: List[Dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT beginning_date, end_date, content
                FROM news_report
                WHERE company_name = %s
                  AND end_date >= %s
                  AND beginning_date <= %s
                ORDER BY end_date DESC, beginning_date DESC
                LIMIT 8
                """,
                (company_name, start_date, end_date),
            )
            rows = cur.fetchall()
    for row in rows:
        content = row["content"]
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            parsed = {"summary": content}
        weekly_reports.append(
            {
                "beginning_date": row["beginning_date"].isoformat(),
                "end_date": row["end_date"].isoformat(),
                "report": parsed,
            }
        )

    raw_news: List[Dict[str, Any]] = []
    if not daily_reports:
        for article in get_company_news_for_range(
            company_name,
            start_date=start_date,
            end_date=end_date,
        )[:60]:
            raw_news.append(
                {
                    "news_date_time": article.news_date_time.isoformat(),
                    "news_title": article.news_title,
                    "news_source": article.news_source,
                    "news_source_link": article.news_source_link,
                    "summary": _decode_llm_content(
                        article.llm_analyzed_content,
                        article.original_content,
                    ).get("summary"),
                }
            )

    price_context = _build_company_status_price_context(company_name, start_date=start_date, end_date=end_date)
    market_stories = _build_company_status_market_story_context(limit=5)

    return {
        "daily_reports": daily_reports,
        "weekly_reports": weekly_reports,
        "raw_news": raw_news,
        "price_context": price_context,
        "market_stories": market_stories,
    }


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
                SELECT ticker, trade_date, close_price, volume
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
    closes = [float(row["close_price"]) for row in rows if row["close_price"] is not None]
    latest = rows[-1]
    first_close = closes[0] if closes else None
    last_close = closes[-1] if closes else None
    pct_change = None
    if first_close not in (None, 0) and last_close is not None:
        pct_change = ((last_close - first_close) / first_close) * 100.0
    return {
        "ticker": rows[-1]["ticker"],
        "point_count": len(rows),
        "window_start": rows[0]["trade_date"].isoformat(),
        "window_end": rows[-1]["trade_date"].isoformat(),
        "latest_close": last_close,
        "window_high": max(closes) if closes else None,
        "window_low": min(closes) if closes else None,
        "window_change_pct": round(pct_change, 2) if pct_change is not None else None,
        "recent_points": [
            {
                "trade_date": row["trade_date"].isoformat(),
                "close_price": float(row["close_price"]) if row["close_price"] is not None else None,
                "volume": int(row["volume"]) if row["volume"] is not None else None,
            }
            for row in rows[-10:]
        ],
    }


def _build_company_status_market_story_context(*, limit: int = 5) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT story_title, happened_text, happening_text, next_text, importance_rank, updated_at
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
            "past": row["happened_text"] or "",
            "now": row["happening_text"] or "",
            "next": row["next_text"] or "",
            "importance_rank": int(row["importance_rank"] or 999),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


def _build_company_status_prompt(
    company_name: str,
    *,
    as_of_date: date,
    prompt_style: str,
    status_input: Dict[str, Any],
    output_language: str = "zh-CN",
) -> str:
    normalized_prompt = str(prompt_style or "simple").strip().lower()
    payload_json = json.dumps(status_input, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    if normalized_prompt == "structured":
        return (
            f"You are building a rolling company status snapshot for {company_name} as of {as_of_date.isoformat()}.\n"
            "Use the provided daily reports and weekly reports as the primary source, and raw news only as fallback context.\n"
            "Also use the price context and broader market stories to judge positioning and plausible future paths.\n"
            "Goals:\n"
            "- Help me quickly catch up on what happened, what is happening now, and what may happen next.\n"
            "- Explain where the current price seems to sit in context: stretched, compressed, stable, volatile, risky, or relatively steady.\n"
            "- Identify plausible next paths, what may trigger them, and how likely they look.\n"
            "- Merge duplicates and repeated coverage.\n"
            "- Preserve all material company-related developments.\n"
            "- Rank storylines by importance to this company.\n"
            "- Use layered structure and clear bullet points.\n"
            f"{language_line}"
            "Sections:\n"
            "1. Price Position\n"
            "2. Company Status (current state)\n"
            "3. Active Storylines (ranked)\n"
            "4. What Changed Recently\n"
            "5. What To Watch Next\n"
            "6. Trigger Map and Uncertainties\n"
            f"Inputs JSON:\n{payload_json}\n"
        )
    return (
        f"Please build a company status snapshot for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal: help me quickly catch up on what happened to the company, what is happening now, what may happen next, and where the current stock price seems to sit in context.\n"
        "Requirements:\n"
        "- Use daily reports and weekly reports as primary sources; use raw news only as fallback context.\n"
        "- Use price context and broader market stories when judging whether the stock looks stretched, compressed, stable, volatile, risky, or relatively steady.\n"
        "- Ignore duplicate or near-duplicate information.\n"
        "- Keep all material company-related points and do not omit important developments.\n"
        "- Include plausible next paths, the triggers for those paths, and your probability/confidence view.\n"
        "- Rank information by importance to this company.\n"
        "- Use layered structure for output which is easy for reading.\n"
        f"{language_line}"
        f"Inputs JSON:\n{payload_json}\n"
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
        if article.is_filtered:
            continue
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


def _build_company_daily_cluster_prompt(
    company_name: str,
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    output_language: str,
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Cluster the company news for {company_name} on {target_date.isoformat()} into a small set of distinct daily company narratives.\n"
        "Goal:\n"
        f"- Produce {COMPANY_DAILY_CLUSTER_MIN} to {COMPANY_DAILY_CLUSTER_MAX} meaningful clusters when possible.\n"
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


def _build_company_story_qa_prompt(
    *,
    company_name: str,
    output_language: str,
    story: Dict[str, Any],
    recent_updates: List[Dict[str, Any]],
    question: str,
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {"story": story, "recent_updates": recent_updates},
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"You are answering a deep-dive question for company {company_name}.\n"
        "Use the story state and recent updates as the primary context.\n"
        "If evidence is insufficient, say what is missing.\n"
        "Use concise layered structure.\n"
        f"{language_line}"
        f"Question:\n{question}\n\n"
        f"Context JSON:\n{payload_json}\n"
    )


def _build_company_story_qa_merge_prompt(
    *,
    company_name: str,
    output_language: str,
    story: Dict[str, Any],
    recent_updates: List[Dict[str, Any]],
    qa_row: Dict[str, Any],
) -> str:
    language_line = _build_output_language_line(output_language)
    payload_json = json.dumps(
        {
            "story": story,
            "recent_updates": recent_updates,
            "qa": qa_row,
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"You are merging a story deep-dive answer back into the live story state for {company_name}.\n"
        "Use the existing story as the base.\n"
        "Use the Q&A answer only if it adds material clarification, context, or updated understanding.\n"
        "Do not drift away from the current storyline.\n"
        "Keep the same story_key.\n"
        "Past and Now should remain bullet-oriented.\n"
        "Next should remain concise bullet lines including scenario, impact, probability/confidence, and sentiment.\n"
        "Return JSON only with key story.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "story": {\n'
        '    "story_key": "same_existing_key",\n'
        '    "story_title": "short title",\n'
        '    "importance_rank": 1,\n'
        '    "story_status": "stable|rising|fading|resolved|finished|closed",\n'
        '    "happened_text": "- ...",\n'
        '    "happening_text": "- ...",\n'
        '    "next_text": "- Scenario: ... | Impact: ... | Probability: ... | Sentiment: ...",\n'
        '    "open_questions": ["..."],\n'
        '    "evidence": [{"news_title": "...", "news_date_time": "...", "news_source_link": "..."}],\n'
        '    "change_log": ["Merged clarification from story Q&A ..."]\n'
        "  }\n"
        "}\n"
        f"Context JSON:\n{payload_json}\n"
    )


def _build_output_language_line(output_language: str) -> str:
    normalized = str(output_language or "").strip().lower()
    if normalized in {"zh", "zh-cn", "zh_hans", "chinese", "simplified chinese"}:
        return "- Output should be written in Simplified Chinese.\n"
    return ""


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
    safe_slice_days = max(1, int(slice_days))
    slices = _build_story_warmup_slices(
        end_date=end_date,
        warmup_days=safe_warmup_days,
        slice_days=safe_slice_days,
    )
    start_date = slices[0][0]
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
            "job_state": "analyzing" if state.get("analysis_started") and not state.get("analysis_completed") else "running",
            "current_stage": "analyzing_stories" if state.get("analysis_started") and not state.get("analysis_completed") else "fetching_raw",
            "window_days": safe_warmup_days,
            "slice_days": safe_slice_days,
            "window_start_date": start_date,
            "window_end_date": end_date,
            "total_slices": len(slices),
            "started_at": datetime.now(timezone.utc),
            "retry_count": int(state.get("retry_count") or 0),
            "raw_fetched_count": int(state.get("raw_fetched_count") or 0),
            "raw_stored_count": int(state.get("raw_stored_count") or 0),
            "filtered_kept_count": int(state.get("filtered_kept_count") or 0),
            "ongoing_story_count": int(state.get("ongoing_story_count") or 0),
            "finished_story_count": int(state.get("finished_story_count") or 0),
            "analysis_started": bool(state.get("analysis_started")),
            "analysis_completed": bool(state.get("analysis_completed")),
            "completed_slices": int(state.get("completed_slices") or 0),
            "last_completed_slice_end_date": _parse_iso_date(state.get("last_completed_slice_end_date")),
            "last_error": "",
            "failed_stage": "",
            "completed_at": None,
        },
    )

    if not state.get("analysis_completed"):
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

        if not state.get("analysis_started"):
            finnhub_source = get_news_source("finnhub")
            ticker = _resolve_company_ticker(company_name) or company_name
            for slice_index, (slice_start, slice_end) in enumerate(slices, start=1):
                if last_completed_slice_end and slice_end <= last_completed_slice_end:
                    continue
                retries = 0
                while True:
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
                            "total_slices": len(slices),
                            "completed_slices": completed_slices,
                            "current_slice_start_date": slice_start,
                            "current_slice_end_date": slice_end,
                            "last_completed_slice_end_date": last_completed_slice_end,
                            "raw_fetched_count": fetched_total,
                            "raw_stored_count": raw_stored_count,
                            "filtered_kept_count": filtered_kept_count,
                            "retry_count": retries,
                            "last_error": "",
                            "failed_stage": "",
                            "analysis_started": False,
                            "analysis_completed": False,
                        },
                    )
                    logger.info(
                        "Story warm-up fetch start: company=%s slice=%d/%d range=%s..%s",
                        company_name,
                        slice_index,
                        len(slices),
                        slice_start.isoformat(),
                        slice_end.isoformat(),
                    )
                    try:
                        raw_items = finnhub_source.fetch_news(
                            company_name=ticker,
                            start_date=slice_start.isoformat(),
                            end_date=slice_end.isoformat(),
                        )
                        fetched_total += len(raw_items)
                        raw_articles = _news_items_from_provider(
                            company_name,
                            _tag_source(raw_items, "finnhub"),
                            end_date=slice_end,
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
                            start_date=slice_start,
                            end_date=slice_end,
                            provider=provider,
                            llm_model=model,
                        )
                        filtered_kept_count += kept_count
                        completed_slices += 1
                        last_completed_slice_end = slice_end
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
                                "total_slices": len(slices),
                                "completed_slices": completed_slices,
                                "current_slice_start_date": None,
                                "current_slice_end_date": None,
                                "last_completed_slice_end_date": last_completed_slice_end,
                                "raw_fetched_count": fetched_total,
                                "raw_stored_count": raw_stored_count,
                                "filtered_kept_count": filtered_kept_count,
                                "retry_count": 0,
                                "analysis_started": False,
                                "analysis_completed": False,
                            },
                        )
                        logger.info(
                            "Story warm-up fetch end: company=%s slice=%d/%d fetched=%d kept=%d",
                            company_name,
                            slice_index,
                            len(slices),
                            len(raw_items),
                            kept_count,
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
                                "total_slices": len(slices),
                                "completed_slices": completed_slices,
                                "current_slice_start_date": slice_start,
                                "current_slice_end_date": slice_end,
                                "last_completed_slice_end_date": last_completed_slice_end,
                                "raw_fetched_count": fetched_total,
                                "raw_stored_count": raw_stored_count,
                                "filtered_kept_count": filtered_kept_count,
                                "retry_count": retries,
                                "last_retry_at": datetime.now(timezone.utc),
                                "last_error": str(exc),
                                "failed_stage": "fetching_raw",
                                "analysis_started": False,
                                "analysis_completed": False,
                            },
                        )
                        logger.warning(
                            "Story warm-up fetch error: company=%s slice=%d/%d retry=%d error=%s",
                            company_name,
                            slice_index,
                            len(slices),
                            retries,
                            exc,
                        )
                        if retries >= DEFAULT_STORY_WARMUP_MAX_RETRIES:
                            if is_rate_limit:
                                return
                            raise
                        if is_rate_limit:
                            pytime.sleep(DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC)
                            continue
                        raise

        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "analyzing",
                "current_stage": "analyzing_stories",
                "window_days": safe_warmup_days,
                "slice_days": safe_slice_days,
                "window_start_date": start_date,
                "window_end_date": end_date,
                "total_slices": len(slices),
                "completed_slices": len(slices),
                "last_completed_slice_end_date": end_date,
                "analysis_started": True,
                "analysis_completed": False,
                "raw_fetched_count": fetched_total,
                "raw_stored_count": raw_stored_count,
                "filtered_kept_count": filtered_kept_count,
                "retry_count": 0,
                "last_error": "",
                "failed_stage": "",
            },
        )
        current_day = start_date
        while current_day <= end_date:
            refresh_company_daily_clusters(
                company_name,
                target_date=current_day,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
            )
            current_day += timedelta(days=1)
        logger.info("Story warm-up analyze start: company=%s", company_name)
        try:
            analysis_result = _generate_company_story_warmup_story_map(
                company_name,
                start_date=start_date,
                end_date=end_date,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
            )
        except Exception as exc:
            _upsert_story_warmup_state(
                company_name,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
                updates={
                    "job_state": "failed",
                    "current_stage": "analyzing_stories",
                    "window_days": safe_warmup_days,
                    "slice_days": safe_slice_days,
                    "window_start_date": start_date,
                    "window_end_date": end_date,
                    "total_slices": len(slices),
                    "completed_slices": len(slices),
                    "last_completed_slice_end_date": end_date,
                    "analysis_started": True,
                    "analysis_completed": False,
                    "last_error": str(exc),
                    "failed_stage": "analyzing_stories",
                },
            )
            logger.exception("Story warm-up analyze failed: company=%s", company_name)
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
                "total_slices": len(slices),
                "completed_slices": len(slices),
                "current_slice_start_date": None,
                "current_slice_end_date": None,
                "last_completed_slice_end_date": end_date,
                "analysis_started": True,
                "analysis_completed": True,
                "raw_fetched_count": int(analysis_result.get("raw_fetched_count", fetched_total)),
                "raw_stored_count": int(analysis_result.get("raw_stored_count", raw_stored_count)),
                "filtered_kept_count": int(analysis_result.get("filtered_kept_count", filtered_kept_count)),
                "ongoing_story_count": int(analysis_result.get("ongoing_story_count", 0)),
                "finished_story_count": int(analysis_result.get("finished_story_count", 0)),
                "last_error": "",
                "failed_stage": "",
                "completed_at": datetime.now(timezone.utc),
            },
        )
        logger.info(
            "Story warm-up analyze end: company=%s ongoing=%d finished=%d",
            company_name,
            int(analysis_result.get("ongoing_story_count", 0)),
            int(analysis_result.get("finished_story_count", 0)),
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
