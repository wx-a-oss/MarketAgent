"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
import os
import logging
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.llms.news import get_news_provider
from market_agent.analysis.company.news.db import get_connection
from market_agent.analysis.company.news.datamodels import NewsArticle
from market_agent.datasources.finnhub import FinnhubClient
from market_agent.news_sources import get_news_source

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
) -> List[NewsArticle]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    r.id AS raw_id,
                    r.company_name,
                    r.news_date_time,
                    r.news_title,
                    r.content AS original_content,
                    a.content AS llm_analyzed_content,
                    COALESCE(a.source_link, r.source_link) AS news_source_link,
                    COALESCE(a.source, r.source) AS news_source,
                    COALESCE(r.is_analyzed, FALSE) AS is_analyzed,
                    COALESCE(r.is_filtered, FALSE) AS is_filtered
                FROM company_news_raw AS r
                LEFT JOIN LATERAL (
                    SELECT
                        aa.content,
                        aa.source_link,
                        aa.source
                    FROM company_news_analyzed AS aa
                    WHERE aa.company_name = r.company_name
                      AND aa.news_title = r.news_title
                      AND aa.news_date_time = r.news_date_time
                    ORDER BY
                        CASE WHEN aa.llm_model = %s THEN 0 ELSE 1 END,
                        aa.id DESC
                    LIMIT 1
                ) AS a ON TRUE
                WHERE r.company_name = %s
                ORDER BY r.news_date_time DESC, r.id DESC
                """,
                (llm_model, company_name),
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


def get_company_news_for_range(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    llm_model: str = DEFAULT_MODEL,
) -> List[NewsArticle]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    r.id AS raw_id,
                    r.company_name,
                    r.news_date_time,
                    r.news_title,
                    r.content AS original_content,
                    a.content AS llm_analyzed_content,
                    COALESCE(a.source_link, r.source_link) AS news_source_link,
                    COALESCE(a.source, r.source) AS news_source,
                    COALESCE(r.is_analyzed, FALSE) AS is_analyzed,
                    COALESCE(r.is_filtered, FALSE) AS is_filtered
                FROM company_news_raw AS r
                LEFT JOIN LATERAL (
                    SELECT
                        aa.content,
                        aa.source_link,
                        aa.source
                    FROM company_news_analyzed AS aa
                    WHERE aa.company_name = r.company_name
                      AND aa.news_title = r.news_title
                      AND aa.news_date_time = r.news_date_time
                    ORDER BY
                        CASE WHEN aa.llm_model = %s THEN 0 ELSE 1 END,
                        aa.id DESC
                    LIMIT 1
                ) AS a ON TRUE
                WHERE r.company_name = %s
                  AND r.news_date_time >= %s
                  AND r.news_date_time < %s
                ORDER BY r.news_date_time DESC, r.id DESC
                """,
                (llm_model, company_name, start_dt, end_dt),
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
                )
                for row in cur.fetchall()
            ]


def generate_weekly_report(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
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
    articles = get_company_news_for_range(
        company_name,
        start_date=start_date,
        end_date=end_date,
        llm_model=model,
    )
    if not articles:
        return None
    items = []
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
    report = provider.fetch_weekly_report(
        company_name=company_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        articles=items,
    )
    _store_weekly_report(
        company_name,
        start_date=start_date,
        end_date=end_date,
        report_payload=report,
    )
    return report


def summarize_company_news_item(
    company_name: str,
    *,
    news_id: int,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    logger.info(
        "Analyze single news start: company=%s news_id=%s model=%s provider=%s",
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
    _store_articles([article], llm_model=model)
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
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"processed": 0, "analyzed": 0, "dropped": 0, "elapsed_sec": 0.0}
    logger.info(
        "Analyze day start: company=%s date=%s limit=%s model=%s provider=%s",
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
            _store_articles(batch_articles, llm_model=model)
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
    content = {
        "summary": item.get("summary"),
        "facts": item.get("facts"),
        "viewpoint": item.get("viewpoint") or item.get("pointview"),
        "reasoning": item.get("reasoning"),
        "uncertainties": item.get("uncertainties"),
        "short_term_impact": item.get("short_term_impact"),
        "long_term_impact": item.get("long_term_impact"),
        "priced_in": item.get("priced_in"),
        "insider_signals": item.get("insider_signals"),
        "trends": item.get("trends"),
        "sentiment": item.get("sentiment"),
    }
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


def _store_articles(articles: Iterable[NewsArticle], *, llm_model: str) -> None:
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
                if _exists_analyzed_article(cur, article, llm_model=llm_model):
                    continue
                cur.execute(
                    """
                    INSERT INTO company_news_analyzed (
                        company_name,
                        news_date_time,
                        news_title,
                        content,
                        source,
                        source_link,
                        llm_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        article.company_name,
                        article.news_date_time,
                        article.news_title,
                        article.llm_analyzed_content,
                        article.news_source,
                        article.news_source_link,
                        llm_model,
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
) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM company_news_analyzed
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
          AND llm_model = %s
        """,
        (article.company_name, article.news_title, article.news_date_time, llm_model),
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
                UPDATE company_news_raw AS r
                SET is_analyzed = TRUE
                WHERE EXISTS (
                    SELECT 1
                    FROM company_news_analyzed AS a
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
