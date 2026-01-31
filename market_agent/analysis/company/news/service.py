"""News fetch/store workflow for companies."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from market_agent.llms.news import get_news_provider
from market_agent.analysis.company.news.db import get_connection
from market_agent.analysis.company.news.datamodels import NewsArticle

DEFAULT_MODEL = "gpt-5.2"
DEFAULT_PROVIDER = "openai"


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


def get_company_news(company_name: str) -> List[NewsArticle]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, news_date_time, news_title,
                       original_content, llm_analyzed_content,
                       news_source_link, news_source
                FROM company_news
                WHERE company_name = %s
                ORDER BY news_date_time DESC
                """,
                (company_name,),
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


def delete_company_news(company_name: str, *, news_id: int) -> None:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM company_news WHERE company_name = %s AND id = %s",
                (company_name, news_id),
            )
        conn.commit()


def refresh_company_news_if_needed(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> None:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return
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
    articles = provider.fetch_news(
        company_name=company_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    if articles:
        _store_articles(_news_items_from_provider(company_name, articles, end_date=end_date))
        report = provider.fetch_weekly_report(
            company_name=company_name,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            articles=articles,
        )
        _store_weekly_report(
            company_name,
            start_date=start_date,
            end_date=end_date,
            report_payload=report,
        )


def refresh_company_news_for_range(
    company_name: str,
    *,
    start_date: date,
    end_date: date,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> None:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    provider = get_news_provider(
        provider_name,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    articles = provider.fetch_news(
        company_name=company_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    if articles:
        _store_articles(_news_items_from_provider(company_name, articles, end_date=end_date))
        report = provider.fetch_weekly_report(
            company_name=company_name,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            articles=articles,
        )
        _store_weekly_report(
            company_name,
            start_date=start_date,
            end_date=end_date,
            report_payload=report,
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


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
                FROM company_news
                WHERE company_name = %s
                ORDER BY news_date_time DESC
                LIMIT 1
                """,
                (company_name,),
            )
            row = cur.fetchone()
            return row["news_date_time"] if row else None


def _store_articles(articles: Iterable[NewsArticle]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            for article in articles:
                if _exists_article(cur, article):
                    continue
                cur.execute(
                    """
                    INSERT INTO company_news (
                        company_name,
                        news_date_time,
                        news_title,
                        original_content,
                        llm_analyzed_content,
                        news_source_link,
                        news_source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        article.company_name,
                        article.news_date_time,
                        article.news_title,
                        article.original_content,
                        article.llm_analyzed_content,
                        article.news_source_link,
                        article.news_source,
                    ),
                )
        conn.commit()


def _exists_article(cur, article: NewsArticle) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM company_news
        WHERE company_name = %s
          AND news_title = %s
          AND news_date_time = %s
        """,
        (article.company_name, article.news_title, article.news_date_time),
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




def _days(count: int) -> timedelta:
    return timedelta(days=count)
