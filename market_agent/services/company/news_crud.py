"""News CRUD functions: fetch, store, filter, delete, summarize."""

from __future__ import annotations

import json
import logging
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.llms.news_registry import get_news_provider
from market_agent.datasources.finnhub import get_news_source
from market_agent.schemas.news import NewsArticle
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    TBL_COMPANY_NEWS_ANALYZED,
)
from market_agent.services.company._constants import (
    ANALYZE_DAY_BATCH_SIZE,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_SOURCE,
    FILTER_DAY_BATCH_SIZE,
    FINNHUB_AUTO_ANALYZE_LIMIT,
)
from market_agent.services.company._helpers import (
    _as_text,
    _days,
    _decode_llm_content,
    _ensure_news_schema,
    _extract_analyzed_content,
    _extract_drop_reason,
    _is_item_relevant,
    _normalize_company_name,
    _parse_date_time,
    _tag_source,
)
from market_agent.services.company.profiles import (
    _resolve_company_ticker,
    ensure_company_profile,
)

logger = logging.getLogger("uvicorn.error")


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
        company_name, news_id, model, provider_name, analysis_prompt,
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, news_date_time, news_title, content, source, source_link
                FROM company_news_raw
                WHERE company_name = %s AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
    if not row:
        logger.info("Analyze single news skipped: company=%s news_id=%s not found", company_name, news_id)
        return False
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    start_date = row["news_date_time"].date().isoformat()
    end_date = start_date
    analyzed = provider.analyze_news_items(
        company_name=company_name, start_date=start_date, end_date=end_date,
        analysis_prompt=analysis_prompt,
        items=[{
            "news_date_time": row["news_date_time"].isoformat(),
            "news_title": row["news_title"],
            "original_content": row["content"],
            "news_source_link": row["source_link"],
            "news_source": row["source"],
        }],
    )
    if not analyzed:
        logger.warning("Analyze single news failed: company=%s news_id=%s empty analysis result", company_name, news_id)
        return False
    article = _news_item_from_payload(company_name, analyzed[0], end_date=row["news_date_time"].date(), analyzed=True)
    _store_articles([article], llm_model=model, output_language=output_language)
    logger.info("Analyze single news finish: company=%s news_id=%s outcome=analyzed", company_name, news_id)
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
        company_name, target_date.isoformat(), limit, model, provider_name, analysis_prompt,
    )
    safe_limit = max(1, min(int(limit), 100))
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, news_date_time, news_title, content, source, source_link
                FROM company_news_raw
                WHERE company_name = %s AND news_date_time >= %s AND news_date_time < %s
                  AND COALESCE(is_analyzed, FALSE) = FALSE
                ORDER BY news_date_time DESC, id DESC
                LIMIT %s
                """,
                (company_name, start_dt, end_dt, safe_limit),
            )
            rows = cur.fetchall()
    logger.info("Analyze day selected raw items: company=%s date=%s count=%d", company_name, target_date.isoformat(), len(rows))
    if not rows:
        logger.info("Analyze day finish: company=%s date=%s processed=0 analyzed=0 dropped=0 elapsed=%.2fs", company_name, target_date.isoformat(), pytime.perf_counter() - started_at)
        return {"processed": 0, "analyzed": 0, "dropped": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    analyzed_count = 0
    total_batches = (len(rows) + ANALYZE_DAY_BATCH_SIZE - 1) // ANALYZE_DAY_BATCH_SIZE
    for batch_index, offset in enumerate(range(0, len(rows), ANALYZE_DAY_BATCH_SIZE), start=1):
        batch_rows = rows[offset : offset + ANALYZE_DAY_BATCH_SIZE]
        logger.info("Analyze day batch start: company=%s date=%s batch=%d/%d size=%d", company_name, target_date.isoformat(), batch_index, total_batches, len(batch_rows))
        analyzed_items = provider.analyze_news_items(
            company_name=company_name, start_date=target_date.isoformat(), end_date=target_date.isoformat(),
            analysis_prompt=analysis_prompt,
            items=[{
                "news_date_time": row["news_date_time"].isoformat(),
                "news_title": row["news_title"],
                "original_content": row["content"],
                "news_source_link": row["source_link"],
                "news_source": row["source"],
            } for row in batch_rows],
        )
        logger.info("Analyze day batch end: company=%s date=%s batch=%d/%d returned=%d", company_name, target_date.isoformat(), batch_index, total_batches, len(analyzed_items))
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
            batch_articles.append(_news_item_from_payload(company_name, item, end_date=target_date, analyzed=True))
        if batch_articles:
            _store_articles(batch_articles, llm_model=model, output_language=output_language)
            analyzed_count += len(batch_articles)
    logger.info(
        "Analyze day finish: company=%s date=%s processed=%d analyzed=%d dropped=%d elapsed=%.2fs",
        company_name, target_date.isoformat(), len(rows), analyzed_count, 0, pytime.perf_counter() - started_at,
    )
    return {"processed": len(rows), "analyzed": analyzed_count, "dropped": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}


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
    logger.info("Filter single news start: company=%s news_id=%s model=%s provider=%s", company_name, news_id, model, provider_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, news_date_time, news_title, content, source, source_link
                FROM company_news_raw
                WHERE company_name = %s AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
    if not row:
        logger.info("Filter single news skipped: company=%s news_id=%s not found", company_name, news_id)
        return {"filtered": False, "dropped": False, "reason": "not found"}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    decisions = provider.filter_news_items(company_name=company_name, items=[{"news_title": row["news_title"]}])
    if not decisions:
        logger.warning("Filter single news failed: company=%s news_id=%s empty filter result", company_name, news_id)
        return {"filtered": False, "dropped": False, "reason": "empty filter result"}
    if not _is_item_relevant(decisions[0]):
        drop_reason = "Filtered by title relevance"
        _delete_raw_news_by_id(company_name, news_id, drop_reason=drop_reason, llm_model=model, dropped_by="manual_filter")
        logger.info("Filter single news finish: company=%s news_id=%s outcome=dropped reason=%s", company_name, news_id, drop_reason)
        return {"filtered": True, "dropped": True, "reason": drop_reason}
    _mark_raw_news_filtered_by_id(company_name, news_id)
    logger.info("Filter single news finish: company=%s news_id=%s outcome=kept", company_name, news_id)
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
    logger.info("Filter day start: company=%s date=%s limit=%s model=%s provider=%s", company_name, target_date.isoformat(), limit, model, provider_name)
    safe_limit = max(1, min(int(limit), 100))
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, news_date_time, news_title, content, source, source_link,
                       COALESCE(is_analyzed, FALSE) AS is_analyzed
                FROM company_news_raw
                WHERE company_name = %s AND news_date_time >= %s AND news_date_time < %s
                  AND COALESCE(is_filtered, FALSE) = FALSE
                ORDER BY news_date_time DESC, id DESC
                LIMIT %s
                """,
                (company_name, start_dt, end_dt, safe_limit),
            )
            rows = cur.fetchall()
    logger.info("Filter day selected items: company=%s date=%s count=%d", company_name, target_date.isoformat(), len(rows))
    if not rows:
        logger.info("Filter day finish: company=%s date=%s processed=0 kept=0 dropped=0 elapsed=%.2fs", company_name, target_date.isoformat(), pytime.perf_counter() - started_at)
        return {"processed": 0, "kept": 0, "dropped": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    dropped_count = 0
    kept_count = 0
    total_batches = (len(rows) + FILTER_DAY_BATCH_SIZE - 1) // FILTER_DAY_BATCH_SIZE
    for batch_index, offset in enumerate(range(0, len(rows), FILTER_DAY_BATCH_SIZE), start=1):
        batch_rows = rows[offset : offset + FILTER_DAY_BATCH_SIZE]
        batch_selected_ids = [int(row["id"]) for row in batch_rows]
        batch_dropped = 0
        logger.info("Filter day batch start: company=%s date=%s batch=%d/%d size=%d", company_name, target_date.isoformat(), batch_index, total_batches, len(batch_rows))
        decisions = provider.filter_news_items(
            company_name=company_name,
            items=[{"news_title": title} for title in list(dict.fromkeys(str(row["news_title"] or "").strip() for row in batch_rows)) if title],
        )
        logger.info("Filter day batch end: company=%s date=%s batch=%d/%d returned=%d", company_name, target_date.isoformat(), batch_index, total_batches, len(decisions))
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
                _delete_raw_news_by_id(company_name, int(matched_row["id"]), drop_reason="Filtered by title relevance", llm_model=model, dropped_by="manual_filter")
                dropped_count += 1
                batch_dropped += 1
        # Persist batch progress immediately so partially finished runs still
        # prevent re-filtering of already-processed kept items.
        _mark_raw_news_filtered_by_ids(company_name, batch_selected_ids)
        batch_kept = max(0, len(batch_rows) - batch_dropped)
        kept_count += batch_kept
        logger.info("Filter day batch progress: company=%s date=%s batch=%d/%d kept=%d dropped=%d", company_name, target_date.isoformat(), batch_index, total_batches, batch_kept, batch_dropped)
    logger.info("Filter day finish: company=%s date=%s processed=%d kept=%d dropped=%d elapsed=%.2fs", company_name, target_date.isoformat(), len(rows), kept_count, dropped_count, pytime.perf_counter() - started_at)
    return {"processed": len(rows), "kept": kept_count, "dropped": dropped_count, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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


def _news_items_from_provider(
    company_name: str,
    items: List[Dict[str, Any]],
    *,
    end_date: date,
    analyzed: bool,
) -> List[NewsArticle]:
    return [_news_item_from_payload(company_name, item, end_date=end_date, analyzed=analyzed) for item in items]


def _fetch_news_with_source(
    source_name: str,
    provider,
    *,
    company_name: str,
    start_date: date,
    end_date: date,
) -> tuple[List[Dict[str, Any]], bool, Dict[str, int]]:
    if source_name == "openai":
        items = provider.fetch_news(company_name=company_name, start_date=start_date.isoformat(), end_date=end_date.isoformat())
        tagged = _tag_source(items, "openai")
        return tagged, True, {"fetched_total": len(tagged), "filtered_out": 0, "kept_after_filter": len(tagged)}
    if source_name == "finnhub":
        ticker = _resolve_company_ticker(company_name) or company_name
        source = get_news_source("finnhub")
        logger.info("Calling Finnhub news: company=%s ticker=%s", company_name, ticker)
        raw_items = source.fetch_news(company_name=ticker, start_date=start_date.isoformat(), end_date=end_date.isoformat())
        logger.info("Finnhub raw items: %d for %s", len(raw_items), company_name)
        filtered_items = _filter_finnhub_items_in_batches(provider=provider, company_name=company_name, items=raw_items, batch_size=FILTER_DAY_BATCH_SIZE)
        logger.info("Finnhub kept after filter: %d/%d for %s", len(filtered_items), len(raw_items), company_name)
        if not filtered_items:
            return [], False, {"fetched_total": len(raw_items), "filtered_out": len(raw_items), "kept_after_filter": 0}
        if len(filtered_items) > FINNHUB_AUTO_ANALYZE_LIMIT:
            logger.info("Skipping auto-analysis for %s: %d filtered items > limit %d", company_name, len(filtered_items), FINNHUB_AUTO_ANALYZE_LIMIT)
            tagged = _tag_source(filtered_items, "finnhub")
            return tagged, False, {"fetched_total": len(raw_items), "filtered_out": len(raw_items) - len(filtered_items), "kept_after_filter": len(filtered_items)}
        batch_size = 5
        analyzed_items: List[Dict[str, Any]] = []
        batches: List[List[Dict[str, Any]]] = [filtered_items[offset : offset + batch_size] for offset in range(0, len(filtered_items), batch_size)]
        for batch_index, batch in enumerate(batches, start=1):
            logger.info("Finnhub analyze batch start %d/%d (%d items) for %s", batch_index, len(batches), len(batch), company_name)
            batch_result = provider.analyze_news_items(company_name=company_name, start_date=start_date.isoformat(), end_date=end_date.isoformat(), items=batch)
            logger.info("Finnhub analyze batch end %d/%d (%d items) for %s", batch_index, len(batches), len(batch_result), company_name)
            analyzed_items.extend(batch_result)
        logger.info("Finnhub analyzed items: %d for %s", len(analyzed_items), company_name)
        tagged = _tag_source(analyzed_items, "finnhub")
        return tagged, True, {"fetched_total": len(raw_items), "filtered_out": len(raw_items) - len(filtered_items), "kept_after_filter": len(filtered_items)}
    raise ValueError(f"Unknown news source: {source_name}")


def _filter_finnhub_items_in_batches(*, provider, company_name: str, items: List[Dict[str, Any]], batch_size: int) -> List[Dict[str, Any]]:
    if not items:
        return []
    kept_items: List[Dict[str, Any]] = []
    total_batches = (len(items) + batch_size - 1) // batch_size
    for batch_index, offset in enumerate(range(0, len(items), batch_size), start=1):
        batch = items[offset : offset + batch_size]
        unique_titles = [{"news_title": title} for title in list(dict.fromkeys(str(item.get("news_title") or "").strip() for item in batch)) if title]
        logger.info("Finnhub filter batch start %d/%d (%d titles) for %s", batch_index, total_batches, len(unique_titles), company_name)
        decisions = provider.filter_news_items(company_name=company_name, items=unique_titles)
        drop_titles: set[str] = set()
        for decision in decisions:
            title_key = str(decision.get("news_title") or "").strip().lower()
            if not title_key:
                continue
            if _is_item_relevant(decision):
                continue
            drop_titles.add(title_key)
        batch_kept = [item for item in batch if str(item.get("news_title") or "").strip().lower() not in drop_titles]
        kept_items.extend(batch_kept)
        logger.info("Finnhub filter batch end %d/%d kept=%d dropped=%d for %s", batch_index, total_batches, len(batch_kept), len(batch) - len(batch_kept), company_name)
    return kept_items


def _filter_company_news_range_raw(*, company_name: str, start_date: date, end_date: date, provider, llm_model: str) -> int:
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, news_title, news_date_time
                FROM company_news_raw
                WHERE company_name = %s AND news_date_time >= %s AND news_date_time < %s
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
    unique_titles = [{"news_title": bucket[0]["news_title"]} for bucket in title_to_rows.values() if bucket and bucket[0].get("news_title")]
    kept_ids: List[int] = []
    for offset in range(0, len(unique_titles), FILTER_DAY_BATCH_SIZE):
        batch = unique_titles[offset : offset + FILTER_DAY_BATCH_SIZE]
        decisions = provider.filter_news_items(company_name=company_name, items=batch)
        decision_map = {str(item.get("news_title") or "").strip().lower(): item for item in decisions if str(item.get("news_title") or "").strip()}
        for title_key, bucket in title_to_rows.items():
            if title_key not in {str(item.get("news_title") or "").strip().lower() for item in batch}:
                continue
            decision = decision_map.get(title_key) or {"keep_for_company": True}
            if _is_item_relevant(decision):
                kept_ids.extend(int(row["id"]) for row in bucket)
                continue
            for row in bucket:
                _delete_news_by_signature(
                    company_name, row["news_title"], row["news_date_time"],
                    archive=True, drop_reason=_extract_drop_reason(decision),
                    llm_model=llm_model, dropped_by="story_warmup_filter",
                )
    _mark_raw_news_filtered_by_ids(company_name, kept_ids)
    return len(kept_ids)


def _get_latest_news_date(company_name: str) -> Optional[datetime]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT news_date_time FROM company_news_raw
                WHERE company_name = %s ORDER BY news_date_time DESC LIMIT 1
                """,
                (company_name,),
            )
            row = cur.fetchone()
            return row["news_date_time"] if row else None


def _store_articles(articles: Iterable[NewsArticle], *, llm_model: str, output_language: str = "en") -> None:
    _ensure_news_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            for article in articles:
                cur.execute(
                    """
                    INSERT INTO company_news_raw (
                        company_name, news_date_time, news_title, content, source, source_link, is_analyzed, is_filtered
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_name, news_title, news_date_time)
                    DO UPDATE SET
                        content = COALESCE(EXCLUDED.content, company_news_raw.content),
                        source = COALESCE(EXCLUDED.source, company_news_raw.source),
                        source_link = COALESCE(EXCLUDED.source_link, company_news_raw.source_link),
                        is_analyzed = company_news_raw.is_analyzed OR EXCLUDED.is_analyzed,
                        is_filtered = company_news_raw.is_filtered OR EXCLUDED.is_filtered
                    """,
                    (article.company_name, article.news_date_time, article.news_title, article.original_content, article.news_source, article.news_source_link, bool(article.is_analyzed), False),
                )
                if not article.llm_analyzed_content:
                    continue
                if _exists_analyzed_article(cur, article, llm_model=llm_model, output_language=output_language):
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_NEWS_ANALYZED} (
                        company_name, news_date_time, news_title, content, source, source_link, llm_model, {COL_OUTPUT_LANGUAGE}
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (article.company_name, article.news_date_time, article.news_title, article.llm_analyzed_content, article.news_source, article.news_source_link, llm_model, output_language),
                )
                cur.execute(
                    """
                    UPDATE company_news_raw SET is_analyzed = TRUE
                    WHERE company_name = %s AND news_title = %s AND news_date_time = %s
                    """,
                    (article.company_name, article.news_title, article.news_date_time),
                )
        conn.commit()


def _exists_raw_article(cur, article: NewsArticle) -> bool:
    cur.execute("SELECT 1 FROM company_news_raw WHERE company_name = %s AND news_title = %s AND news_date_time = %s", (article.company_name, article.news_title, article.news_date_time))
    return cur.fetchone() is not None


def _exists_analyzed_article(cur, article: NewsArticle, *, llm_model: str, output_language: str) -> bool:
    cur.execute(
        f"SELECT 1 FROM {TBL_COMPANY_NEWS_ANALYZED} WHERE company_name = %s AND news_title = %s AND news_date_time = %s AND llm_model = %s AND {COL_OUTPUT_LANGUAGE} = %s",
        (article.company_name, article.news_title, article.news_date_time, llm_model, output_language),
    )
    return cur.fetchone() is not None


def _delete_raw_news_by_id(company_name: str, news_id: int, *, archive: bool = True, drop_reason: Optional[str] = None, llm_model: Optional[str] = None, dropped_by: Optional[str] = None) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT news_title, news_date_time FROM company_news_raw WHERE company_name = %s AND id = %s", (company_name, news_id))
            row = cur.fetchone()
            if not row:
                return
            _delete_news_by_signature_with_cursor(cur, company_name, row["news_title"], row["news_date_time"], archive=archive, drop_reason=drop_reason, llm_model=llm_model, dropped_by=dropped_by)
        conn.commit()


def _mark_raw_news_filtered_by_id(company_name: str, news_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE company_news_raw SET is_filtered = TRUE WHERE company_name = %s AND id = %s", (company_name, news_id))
        conn.commit()


def _mark_raw_news_filtered_by_ids(company_name: str, news_ids: List[int]) -> None:
    if not news_ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            for news_id in news_ids:
                cur.execute("UPDATE company_news_raw SET is_filtered = TRUE WHERE company_name = %s AND id = %s", (company_name, int(news_id)))
        conn.commit()


def _delete_news_by_signature(company_name: str, news_title: str, news_date_time: datetime, *, archive: bool = False, drop_reason: Optional[str] = None, llm_model: Optional[str] = None, dropped_by: Optional[str] = None) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            _delete_news_by_signature_with_cursor(cur, company_name, news_title, news_date_time, archive=archive, drop_reason=drop_reason, llm_model=llm_model, dropped_by=dropped_by)
        conn.commit()


def _delete_news_by_signature_with_cursor(cur, company_name: str, news_title: str, news_date_time: datetime, *, archive: bool = False, drop_reason: Optional[str] = None, llm_model: Optional[str] = None, dropped_by: Optional[str] = None) -> None:
    if archive:
        _archive_dropped_news_with_cursor(cur, company_name, news_title, news_date_time, drop_reason=drop_reason, llm_model=llm_model, dropped_by=dropped_by)
    cur.execute("DELETE FROM company_news_analyzed WHERE company_name = %s AND news_title = %s AND news_date_time = %s", (company_name, news_title, news_date_time))
    cur.execute("DELETE FROM company_news_raw WHERE company_name = %s AND news_title = %s AND news_date_time = %s", (company_name, news_title, news_date_time))


def _archive_dropped_news_with_cursor(cur, company_name: str, news_title: str, news_date_time: datetime, *, drop_reason: Optional[str], llm_model: Optional[str], dropped_by: Optional[str]) -> None:
    cur.execute(
        """
        SELECT
            r.id AS raw_news_id, r.company_name, r.news_date_time, r.news_title,
            r.content AS raw_content, r.source AS raw_source, r.source_link AS raw_source_link,
            COALESCE(r.is_analyzed, FALSE) AS raw_is_analyzed,
            a.content AS analyzed_content, a.source AS analyzed_source, a.source_link AS analyzed_source_link, a.llm_model AS analyzed_llm_model
        FROM company_news_raw AS r
        LEFT JOIN LATERAL (
            SELECT aa.content, aa.source, aa.source_link, aa.llm_model
            FROM company_news_analyzed AS aa
            WHERE aa.company_name = r.company_name AND aa.news_title = r.news_title AND aa.news_date_time = r.news_date_time
            ORDER BY CASE WHEN %s IS NOT NULL AND aa.llm_model = %s THEN 0 ELSE 1 END, aa.id DESC
            LIMIT 1
        ) AS a ON TRUE
        WHERE r.company_name = %s AND r.news_title = %s AND r.news_date_time = %s
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
            company_name, raw_news_id, news_date_time, news_title,
            raw_content, raw_source, raw_source_link, raw_is_analyzed,
            analyzed_content, analyzed_source, analyzed_source_link, analyzed_llm_model,
            drop_reason, dropped_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (row["company_name"], row["raw_news_id"], row["news_date_time"], row["news_title"], row["raw_content"], row["raw_source"], row["raw_source_link"], bool(row["raw_is_analyzed"]), row["analyzed_content"], row["analyzed_source"], row["analyzed_source_link"], row["analyzed_llm_model"], _as_text(drop_reason), _as_text(dropped_by)),
    )
