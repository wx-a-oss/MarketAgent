"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
import os
import re
import logging
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.llms.news import get_news_provider
from market_agent.analysis.company.news.db import get_connection
from market_agent.analysis.company.news.datamodels import NewsArticle
from market_agent.datasources.finnhub import FinnhubClient
from market_agent.news_sources import get_news_source
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_STORY_KEY,
    TBL_COMPANY_NEWS_ANALYZED,
    TBL_COMPANY_STORY_QA,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
)

DEFAULT_MODEL = "gpt-5.2"
DEFAULT_PROVIDER = "openai"
DEFAULT_SOURCE = "openai"
FINNHUB_AUTO_ANALYZE_LIMIT = 10
ANALYZE_DAY_BATCH_SIZE = 3
FILTER_DAY_BATCH_SIZE = 10

logger = logging.getLogger("uvicorn.error")
_SCHEMA_READY = False


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
                    importance_rank,
                    story_status,
                    confidence,
                    happened_text,
                    happening_text,
                    next_text,
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
                    importance_rank,
                    story_status,
                    confidence,
                    happened_text,
                    happening_text,
                    next_text,
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
    safe_window_days = max(7, min(int(window_days), 90))
    start_date = end_date - timedelta(days=safe_window_days - 1)
    status_input = _build_company_status_input(
        company_name,
        start_date=start_date,
        end_date=end_date,
        provider_name=provider_name,
    )
    existing = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    prompt = _build_company_story_update_prompt(
        company_name,
        as_of_date=end_date,
        prompt_style=prompt_style,
        output_language=output_language,
        existing_stories=existing,
        status_input=status_input,
    )
    raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    stories = payload.get("stories")
    if not isinstance(stories, list):
        stories = []
    normalized = [_normalize_story_record(item) for item in stories if isinstance(item, dict)]
    normalized = [item for item in normalized if item]
    if not normalized:
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
            "prompt": prompt,
            "existing_story_count": len(existing),
            "status_input": status_input,
        },
        raw_output=raw_output,
        stories=normalized,
    )
    return {
        "generated": True,
        "story_count": len(normalized),
        "daily_report_count": len(status_input.get("daily_reports") or []),
        "weekly_report_count": len(status_input.get("weekly_reports") or []),
        "raw_news_count": len(status_input.get("raw_news") or []),
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
        logger.warning("Symbol lookup returned no ticker for %s", company_name)
        return None
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
                        importance_rank,
                        story_status,
                        confidence,
                        happened_text,
                        happening_text,
                        next_text,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (company_name, {COL_STORY_KEY}, provider, prompt_style, {COL_OUTPUT_LANGUAGE})
                    DO UPDATE SET
                        story_title = EXCLUDED.story_title,
                        importance_rank = EXCLUDED.importance_rank,
                        story_status = EXCLUDED.story_status,
                        confidence = EXCLUDED.confidence,
                        happened_text = EXCLUDED.happened_text,
                        happening_text = EXCLUDED.happening_text,
                        next_text = EXCLUDED.next_text,
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
                        int(item["importance_rank"]),
                        item["story_status"],
                        float(item["confidence"]),
                        item["happened_text"],
                        item["happening_text"],
                        item["next_text"],
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
    normalized_prompt = str(prompt_style or "simple").strip().lower()
    language_line = _build_output_language_line(output_language)
    if normalized_prompt == "structured":
        return (
            f"Summarize all {company_name} news for {target_date.isoformat()} into a structured daily company report.\n"
            "Requirements:\n"
            "- Ignore duplicate or near-duplicate news items.\n"
            "- Keep all material company-related points; ignore unrelated points.\n"
            "- Rank information by importance to this company.\n"
            "- Try to open links first for more context; if inaccessible, use available content/web search.\n"
            "- Use layered structure with clear sections and bullet points.\n"
            f"{language_line}"
            "Sections:\n"
            "1. Top Summary\n2. Important News & Insights\n3. What Changed Today\n4. What To Watch Next\n"
            f"News items JSON:\n{items_json}\n"
        )
    return (
        f"Please summarize all {company_name} news for {target_date.isoformat()}.\n"
        "Goal: help me quickly understand what happened to the company today and the most important insights.\n"
        "Requirements:\n"
        "- Ignore duplicate or near-duplicate news items.\n"
        "- Keep all material points and do not omit important company-related information.\n"
        "- Ignore points not related to this company or its market/investor outlook.\n"
        "- Rank information by importance to this company (most important first).\n"
        "- Try to open links first for fuller context. If inaccessible, use available content and best available information.\n"
        "- Use layered structure for output which is easy for reading.\n"
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

    return {
        "daily_reports": daily_reports,
        "weekly_reports": weekly_reports,
        "raw_news": raw_news,
    }


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
            "Goals:\n"
            "- Help me quickly catch up on what happened, what is happening now, and what may happen next.\n"
            "- Merge duplicates and repeated coverage.\n"
            "- Preserve all material company-related developments.\n"
            "- Rank storylines by importance to this company.\n"
            "- Use layered structure and clear bullet points.\n"
            f"{language_line}"
            "Sections:\n"
            "1. Company Status (current state)\n"
            "2. Active Storylines (ranked)\n"
            "3. What Changed Recently\n"
            "4. What To Watch Next\n"
            "5. Uncertainties / Open Questions\n"
            f"Inputs JSON:\n{payload_json}\n"
        )
    return (
        f"Please build a company status snapshot for {company_name} as of {as_of_date.isoformat()}.\n"
        "Goal: help me quickly catch up on what happened to the company, what is happening now, and what may happen next.\n"
        "Requirements:\n"
        "- Use daily reports and weekly reports as primary sources; use raw news only as fallback context.\n"
        "- Ignore duplicate or near-duplicate information.\n"
        "- Keep all material company-related points and do not omit important developments.\n"
        "- Rank information by importance to this company.\n"
        "- Use layered structure for output which is easy for reading.\n"
        f"{language_line}"
        f"Inputs JSON:\n{payload_json}\n"
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
    return {
        "story_key": story_key,
        "story_title": title,
        "importance_rank": max(1, rank),
        "story_status": _as_text(item.get("story_status")) or "stable",
        "confidence": confidence,
        "happened_text": _as_text(item.get("happened_text")) or "",
        "happening_text": _as_text(item.get("happening_text")) or "",
        "next_text": _as_text(item.get("next_text")) or "",
        "open_questions": item.get("open_questions") if isinstance(item.get("open_questions"), list) else [],
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "change_log": item.get("change_log") if isinstance(item.get("change_log"), list) else [],
    }


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
        "importance_rank": int(row["importance_rank"] or 999),
        "story_status": row["story_status"] or "stable",
        "confidence": float(row["confidence"] or 0.5),
        "happened_text": row["happened_text"] or "",
        "happening_text": row["happening_text"] or "",
        "next_text": row["next_text"] or "",
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
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Runtime schema guard keeps local/dev DBs aligned without manual migrations.
            cur.execute(
                """
                ALTER TABLE company_news_raw
                ADD COLUMN IF NOT EXISTS is_analyzed BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            cur.execute(
                """
                ALTER TABLE company_news_raw
                ADD COLUMN IF NOT EXISTS is_filtered BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TBL_COMPANY_NEWS_ANALYZED}
                ADD COLUMN IF NOT EXISTS {COL_OUTPUT_LANGUAGE} TEXT NOT NULL DEFAULT 'en'
                """
            )
            cur.execute(
                """
                DROP INDEX IF EXISTS idx_company_news_analyzed_unique
                """
            )
            cur.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_company_news_analyzed_unique
                ON {TBL_COMPANY_NEWS_ANALYZED} (
                    company_name,
                    news_title,
                    news_date_time,
                    llm_model,
                    {COL_OUTPUT_LANGUAGE}
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS company_news_dropped (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    raw_news_id BIGINT,
                    news_date_time TIMESTAMPTZ NOT NULL,
                    news_title TEXT NOT NULL,
                    raw_content TEXT,
                    raw_source TEXT,
                    raw_source_link TEXT,
                    raw_is_analyzed BOOLEAN NOT NULL DEFAULT FALSE,
                    analyzed_content TEXT,
                    analyzed_source TEXT,
                    analyzed_source_link TEXT,
                    analyzed_llm_model TEXT,
                    drop_reason TEXT,
                    dropped_by TEXT,
                    dropped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_company_news_dropped_company_name
                    ON company_news_dropped (company_name, dropped_at DESC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS company_news_daily_report (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    report_date DATE NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_style TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_company_news_daily_report_lookup
                ON company_news_daily_report (
                    company_name,
                    report_date DESC,
                    provider,
                    prompt_style,
                    created_at DESC
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS company_status_snapshot (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    as_of_date DATE NOT NULL,
                    window_start_date DATE NOT NULL,
                    window_end_date DATE NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_style TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_company_status_snapshot_lookup
                ON company_status_snapshot (
                    company_name,
                    provider,
                    prompt_style,
                    created_at DESC
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TBL_COMPANY_STORY_STATE} (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    {COL_STORY_KEY} TEXT NOT NULL,
                    story_title TEXT NOT NULL,
                    importance_rank INTEGER NOT NULL DEFAULT 999,
                    story_status TEXT NOT NULL DEFAULT 'stable',
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    happened_text TEXT,
                    happening_text TEXT,
                    next_text TEXT,
                    open_questions_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    change_log_json TEXT NOT NULL DEFAULT '[]',
                    last_event_at TIMESTAMPTZ,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_style TEXT NOT NULL,
                    {COL_OUTPUT_LANGUAGE} TEXT NOT NULL DEFAULT 'zh-CN',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_company_story_state_unique
                ON {TBL_COMPANY_STORY_STATE} (
                    company_name,
                    {COL_STORY_KEY},
                    provider,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE}
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_company_story_state_lookup
                ON {TBL_COMPANY_STORY_STATE} (
                    company_name,
                    provider,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    is_active,
                    importance_rank,
                    updated_at DESC
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TBL_COMPANY_STORY_UPDATE} (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    {COL_STORY_KEY} TEXT NOT NULL,
                    as_of_date DATE NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_style TEXT NOT NULL,
                    {COL_OUTPUT_LANGUAGE} TEXT NOT NULL DEFAULT 'zh-CN',
                    input_payload TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_company_story_update_lookup
                ON {TBL_COMPANY_STORY_UPDATE} (
                    company_name,
                    {COL_STORY_KEY},
                    provider,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    created_at DESC
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TBL_COMPANY_STORY_QA} (
                    id BIGSERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    {COL_STORY_KEY} TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_style TEXT NOT NULL,
                    {COL_OUTPUT_LANGUAGE} TEXT NOT NULL DEFAULT 'zh-CN',
                    input_payload TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_company_story_qa_lookup
                ON {TBL_COMPANY_STORY_QA} (
                    company_name,
                    {COL_STORY_KEY},
                    provider,
                    prompt_style,
                    {COL_OUTPUT_LANGUAGE},
                    created_at DESC
                )
                """
            )
            cur.execute(
                f"""
                UPDATE company_news_raw AS r
                SET is_analyzed = TRUE
                WHERE EXISTS (
                    SELECT 1
                    FROM {TBL_COMPANY_NEWS_ANALYZED} AS a
                    WHERE a.company_name = r.company_name
                      AND a.news_title = r.news_title
                      AND a.news_date_time = r.news_date_time
                )
                """
            )
        conn.commit()
    _SCHEMA_READY = True


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
