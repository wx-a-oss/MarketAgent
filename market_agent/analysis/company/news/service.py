"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor
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

logger = logging.getLogger("uvicorn.error")


def list_watchlist_companies() -> List[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_name FROM company_watchlist ORDER BY added_at DESC"
            )
            return [row["company_name"] for row in cur.fetchall()]


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
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id,
                       a.company_name,
                       a.news_date_time,
                       a.news_title,
                       r.content AS original_content,
                       a.content AS llm_analyzed_content,
                       COALESCE(a.source_link, r.source_link) AS news_source_link,
                       COALESCE(a.source, r.source) AS news_source
                FROM company_news_analyzed AS a
                LEFT JOIN company_news_raw AS r
                  ON r.company_name = a.company_name
                 AND r.news_title = a.news_title
                 AND r.news_date_time = a.news_date_time
                WHERE a.company_name = %s
                  AND a.llm_model = %s
                ORDER BY a.news_date_time DESC, a.id DESC
                """,
                (company_name, llm_model),
            )
            return [
                NewsArticle(
                    id=row["id"],
                    company_name=row["company_name"],
                    news_date_time=row["news_date_time"],
                    news_title=row["news_title"],
                    original_content=row["original_content"],
                    llm_analyzed_content=row["llm_analyzed_content"],
                    news_source_link=row["news_source_link"],
                    news_source=row["news_source"],
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
    company_name = _normalize_company_name(company_name)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id,
                       a.company_name,
                       a.news_date_time,
                       a.news_title,
                       r.content AS original_content,
                       a.content AS llm_analyzed_content,
                       COALESCE(a.source_link, r.source_link) AS news_source_link,
                       COALESCE(a.source, r.source) AS news_source
                FROM company_news_analyzed AS a
                LEFT JOIN company_news_raw AS r
                  ON r.company_name = a.company_name
                 AND r.news_title = a.news_title
                 AND r.news_date_time = a.news_date_time
                WHERE a.company_name = %s
                  AND a.llm_model = %s
                  AND a.news_date_time >= %s
                  AND a.news_date_time < %s
                ORDER BY a.news_date_time DESC, a.id DESC
                """,
                (company_name, llm_model, start_dt, end_dt),
            )
            return [
                NewsArticle(
                    id=row["id"],
                    company_name=row["company_name"],
                    news_date_time=row["news_date_time"],
                    news_title=row["news_title"],
                    original_content=row["original_content"],
                    llm_analyzed_content=row["llm_analyzed_content"],
                    news_source_link=row["news_source_link"],
                    news_source=row["news_source"],
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
    for article in articles:
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
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT news_title, news_date_time
                FROM company_news_analyzed
                WHERE company_name = %s AND id = %s
                """,
                (company_name, news_id),
            )
            row = cur.fetchone()
            if not row:
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
                (company_name, row["news_title"], row["news_date_time"]),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    DELETE FROM company_news_raw
                    WHERE company_name = %s
                      AND news_title = %s
                      AND news_date_time = %s
                    """,
                    (company_name, row["news_title"], row["news_date_time"]),
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
) -> None:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return
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
    articles = _fetch_news_with_source(
        source_name,
        provider,
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
    )
    if articles:
        _store_articles(
            _news_items_from_provider(company_name, articles, end_date=end_date),
            llm_model=model,
        )


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
) -> None:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return
    ensure_company_profile(company_name)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    articles = _fetch_news_with_source(
        source_name,
        provider,
        company_name=company_name,
        start_date=start_date,
        end_date=end_date,
    )
    if articles:
        _store_articles(
            _news_items_from_provider(company_name, articles, end_date=end_date),
            llm_model=model,
        )




def _news_item_from_payload(
    company_name: str,
    item: Dict[str, Any],
    *,
    end_date: date,
) -> NewsArticle:
    news_date_time = _parse_date_time(item.get("news_date_time"), end_date=end_date)
    original_content = _as_text(item.get("original_content"))
    content = {
        "summary": item.get("summary"),
        "facts": item.get("facts"),
        "viewpoint": item.get("viewpoint") or item.get("pointview"),
        "bias": item.get("bias"),
        "reasoning": item.get("reasoning"),
        "short_term_impact": item.get("short_term_impact"),
        "long_term_impact": item.get("long_term_impact"),
        "uncertainties": item.get("uncertainties"),
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
        llm_analyzed_content=json.dumps(content),
        news_source_link=_as_text(item.get("news_source_link")),
        news_source=_as_text(item.get("news_source")),
    )


def _news_items_from_provider(
    company_name: str,
    items: List[Dict[str, Any]],
    *,
    end_date: date,
) -> List[NewsArticle]:
    return [
        _news_item_from_payload(company_name, item, end_date=end_date)
        for item in items
    ]


def _fetch_news_with_source(
    source_name: str,
    provider,
    *,
    company_name: str,
    start_date: date,
    end_date: date,
) -> List[Dict[str, Any]]:
    if source_name == "openai":
        items = provider.fetch_news(
            company_name=company_name,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        return _tag_source(items, "openai")
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
        batch_size = 10
        max_parallel_batches = 2
        analyzed_items: List[Dict[str, Any]] = []
        batches: List[List[Dict[str, Any]]] = [
            raw_items[offset : offset + batch_size]
            for offset in range(0, len(raw_items), batch_size)
        ]

        def _analyze_batch(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return provider.analyze_news_items(
                company_name=company_name,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                items=batch,
            )

        with ThreadPoolExecutor(max_workers=max_parallel_batches) as executor:
            futures = []
            for batch_index, batch in enumerate(batches, start=1):
                logger.info(
                    "Queueing Finnhub batch %d/%d (%d items) for OpenAI analysis for %s",
                    batch_index,
                    len(batches),
                    len(batch),
                    company_name,
                )
                futures.append(executor.submit(_analyze_batch, batch))

            for batch_index, future in enumerate(futures, start=1):
                batch_result = future.result()
                logger.info(
                    "Completed Finnhub batch %d/%d (%d items) for %s",
                    batch_index,
                    len(batches),
                    len(batch_result),
                    company_name,
                )
                analyzed_items.extend(batch_result)
        logger.info("Finnhub analyzed items: %d for %s", len(analyzed_items), company_name)
        return _tag_source(analyzed_items, "finnhub")
    raise ValueError(f"Unknown news source: {source_name}")


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
    with get_connection() as conn:
        with conn.cursor() as cur:
            for article in articles:
                if not _exists_raw_article(cur, article):
                    cur.execute(
                        """
                        INSERT INTO company_news_raw (
                            company_name,
                            news_date_time,
                            news_title,
                            content,
                            source,
                            source_link
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            article.company_name,
                            article.news_date_time,
                            article.news_title,
                            article.original_content,
                            article.news_source,
                            article.news_source_link,
                        ),
                    )
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
