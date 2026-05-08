"""Daily update, news fetch, reports, and shared constants."""

from __future__ import annotations

import html
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from market_agent.config.models import DEFAULT_MARKET_OPENAI_MODEL
from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.services.company._helpers import (
    _build_output_language_line,
)
from market_agent.llms.usage_context import usage_context
from market_agent.llms.openai_news import generate_text_with_web_search
from market_agent.llms.news_registry import get_news_provider
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    TBL_MARKET_NEWS_RAW,
)

# Module self-reference so callee lookups go through the module namespace,
# allowing monkeypatching on the re-export shim (market_updates) to propagate
# when tests also patch this module.
def _self():
    return sys.modules[__name__]

# Reference to the re-export shim so that monkeypatches on market_updates
# (which is what tests use) are visible to code in this sub-module.
def _shim():
    return sys.modules.get('market_agent.workflows.market_updates') or sys.modules[__name__]

DEFAULT_MARKET_PROVIDER = "openai"
DEFAULT_MARKET_MODEL = DEFAULT_MARKET_OPENAI_MODEL
APP_LOCAL_TZ = ZoneInfo("America/Los_Angeles")

logger = logging.getLogger("uvicorn.error")


@dataclass
class MarketNewsItem:
    news_date: date
    date_time: Optional[datetime]
    headline: str
    source: str
    source_tag: str
    url: str
    summary: str
    payload: Dict[str, Any]


def _current_app_date() -> date:
    return datetime.now(APP_LOCAL_TZ).date()


def run_market_daily_update(
    *,
    target_date: Optional[date] = None,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = 14,
) -> Dict[str, Any]:
    _shim().ensure_database_schema()
    target = target_date or _shim()._current_app_date()
    logger.info(
        "Market daily update started: target_date=%s provider=%s model=%s prompt=%s language=%s warmup_days=%s",
        target.isoformat(),
        provider_name,
        model,
        prompt_style,
        output_language,
        warmup_days,
    )
    state = _shim().get_market_story_warmup_state()
    if state.get("job_state") != "completed":
        logger.info("Market daily update falling back to warmup: state=%s", state.get("job_state"))
        warmup = _shim().start_market_story_warmup(
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            warmup_days=warmup_days,
        )
        return {"mode": "warmup_started", "warmup": warmup, "target_date": target.isoformat()}
    if _shim()._has_market_raw_for_day(target):
        logger.info("Market daily update reusing existing raw news: target_date=%s", target.isoformat())
        refresh_stats = {
            "fetched_total": 0,
            "stored_total": 0,
            "start_date": target.isoformat(),
            "end_date": target.isoformat(),
            "mode": "reuse_existing_raw",
        }
    else:
        logger.info("Market daily update fetching raw news: target_date=%s", target.isoformat())
        refresh_stats = _shim().refresh_market_news_for_range(start_date=target, end_date=target)
    daily_report_stats = _shim().generate_market_daily_report(
        target_date=target,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    cluster_stats = _shim().refresh_market_daily_clusters(
        target_date=target,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    story_stats = _shim().refresh_market_story_states(
        as_of_date=target,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    logger.info(
        "Market daily update completed: target_date=%s fetched=%s stored=%s daily_reports=%s clusters=%s routed_clusters=%s ongoing=%s finished=%s",
        target.isoformat(),
        int(refresh_stats.get("fetched_total", 0)),
        int(refresh_stats.get("stored_total", 0)),
        int(daily_report_stats.get("report_count", 0)),
        int(cluster_stats.get("cluster_count", 0)),
        int(story_stats.get("routed_cluster_count", 0)),
        int(story_stats.get("ongoing_story_count", 0)),
        int(story_stats.get("finished_story_count", 0)),
    )
    return {
        "mode": "daily_update",
        "target_date": target.isoformat(),
        "refresh_stats": refresh_stats,
        "daily_report_stats": daily_report_stats,
        "cluster_stats": cluster_stats,
        "story_stats": story_stats,
    }


def refresh_market_news_for_range(*, start_date: date, end_date: date) -> Dict[str, Any]:
    _shim().ensure_database_schema()
    logger.info("Market raw news refresh started: %s..%s", start_date.isoformat(), end_date.isoformat())
    fetched_total = 0
    stored_total = 0
    skipped_existing_days = 0
    local_today = datetime.now().date()
    current = start_date
    while current <= end_date:
        if current < local_today and _shim()._has_market_raw_for_day(current):
            skipped_existing_days += 1
            logger.info(
                "Market raw news refresh skipping existing past date: %s",
                current.isoformat(),
            )
            current += timedelta(days=1)
            continue
        for item in _shim()._fetch_market_news_for_day(current):
            fetched_total += 1
            stored_total += int(_shim()._upsert_market_news_raw(item))
        current += timedelta(days=1)
    logger.info(
        "Market raw news refresh completed: %s..%s fetched_total=%s stored_total=%s skipped_existing_days=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        fetched_total,
        stored_total,
        skipped_existing_days,
    )
    return {
        "fetched_total": fetched_total,
        "stored_total": stored_total,
        "skipped_existing_days": skipped_existing_days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def list_market_raw_news(
    *,
    target_date: date,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT news_date, news_date_time, headline, source, source_tag, news_url, summary
                FROM {TBL_MARKET_NEWS_RAW}
                WHERE news_date = %s
                ORDER BY COALESCE(news_date_time, (news_date::timestamp)) DESC, id DESC
                LIMIT %s
                """,
                (target_date, max(1, int(limit))),
            )
            rows = cur.fetchall()
    return [
        {
            "date": row["news_date"].isoformat(),
            "datetime_text": row["news_date_time"].isoformat() if row["news_date_time"] else row["news_date"].isoformat(),
            "headline": row["headline"],
            "source": row["source"] or "",
            "source_tag": row["source_tag"] or "",
            "url": row["news_url"],
            "summary": row["summary"] or "",
        }
        for row in rows
    ]


def generate_market_daily_report(
    *,
    target_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    items = list_market_raw_news(target_date=target_date, limit=250)
    if not items:
        return {"generated": False, "report_count": 0, "target_date": target_date.isoformat(), "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=180)
    prompt = _build_market_daily_report_prompt(
        target_date=target_date,
        items=items,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    with usage_context("market_daily_report", module="market"):
        output_text = provider.generate_text(prompt=prompt)
    _upsert_market_daily_summary_shared(
        summary_date=target_date,
        provider=provider_name,
        model=model,
        prompt_style=prompt_style,
        news_sources=",".join(sorted({str(item.get("source_tag") or "").strip() for item in items if str(item.get("source_tag") or "").strip()})),
        input_payload={"items": items, "prompt": prompt},
        output_text=output_text,
    )
    return {
        "generated": True,
        "report_count": 1,
        "target_date": target_date.isoformat(),
        "input_item_count": len(items),
        "prompt_char_count": len(prompt),
        "output_char_count": len(output_text or ""),
    }


def get_market_daily_news_overview(
    *,
    target_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    from market_agent.workflows.market_clusters import list_market_daily_clusters

    return {
        "date": target_date.isoformat(),
        "raw_news": list_market_raw_news(target_date=target_date),
        "summaries": _get_market_daily_summaries_shared(target_date),
        "clusters": list_market_daily_clusters(
            target_date=target_date,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        ),
    }


def _upsert_market_news_raw(item: MarketNewsItem) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_NEWS_RAW}
                    (news_date, news_date_time, headline, source, source_tag, news_url, summary, payload_json, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (news_date, news_url)
                DO UPDATE SET
                    news_date_time = EXCLUDED.news_date_time,
                    headline = EXCLUDED.headline,
                    source = EXCLUDED.source,
                    source_tag = EXCLUDED.source_tag,
                    summary = EXCLUDED.summary,
                    payload_json = EXCLUDED.payload_json,
                    updated_at = NOW()
                """,
                (
                    item.news_date,
                    item.date_time,
                    item.headline,
                    item.source,
                    item.source_tag,
                    item.url,
                    item.summary,
                    json.dumps(item.payload, ensure_ascii=False),
                ),
            )
        conn.commit()
    return 1


def _has_market_raw_for_day(target_date: date) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT 1
                FROM {TBL_MARKET_NEWS_RAW}
                WHERE news_date = %s
                LIMIT 1
                """,
                (target_date,),
            )
            row = cur.fetchone()
    return bool(row)


def _get_market_raw_coverage(*, start_date: date, end_date: date) -> Dict[str, Any]:
    expected_dates = []
    cursor = start_date
    while cursor <= end_date:
        expected_dates.append(cursor)
        cursor += timedelta(days=1)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT news_date, COUNT(*) AS item_count
                FROM {TBL_MARKET_NEWS_RAW}
                WHERE news_date >= %s
                  AND news_date <= %s
                GROUP BY news_date
                ORDER BY news_date ASC
                """,
                (start_date, end_date),
            )
            rows = cur.fetchall()
    counts_by_day = {row["news_date"]: int(row["item_count"] or 0) for row in rows}
    missing_dates = [current for current in expected_dates if counts_by_day.get(current, 0) <= 0]
    return {
        "item_count": sum(counts_by_day.values()),
        "covered_day_count": sum(1 for current in expected_dates if counts_by_day.get(current, 0) > 0),
        "missing_dates": missing_dates,
    }


def _fetch_market_news_for_day(target_date: date) -> List[MarketNewsItem]:
    merged: List[MarketNewsItem] = []
    merged.extend(_fetch_finnhub_market_news(target_date=target_date))
    merged.extend(_fetch_yahoo_rss_market_news(target_date=target_date))
    deduped: List[MarketNewsItem] = []
    seen: set[tuple[date, str]] = set()
    for item in merged:
        key = (item.news_date, item.url.strip().lower() or item.headline.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _fetch_finnhub_market_news(*, target_date: date, limit: int = 200) -> List[MarketNewsItem]:
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return []
    url = "https://finnhub.io/api/v1/news?" + urllib.parse.urlencode({"category": "general", "token": api_key})
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    items: List[MarketNewsItem] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("headline") or "").strip()
        link = str(row.get("url") or "").strip()
        source = str(row.get("source") or "").strip() or "Finnhub"
        if not headline or not link:
            continue
        date_time = None
        if row.get("datetime"):
            try:
                date_time = datetime.fromtimestamp(int(row["datetime"]), tz=timezone.utc)
            except Exception:
                date_time = None
        news_date = date_time.date() if date_time else target_date
        if news_date != target_date:
            continue
        items.append(
            MarketNewsItem(
                news_date=news_date,
                date_time=date_time,
                headline=headline,
                source=source,
                source_tag="finnhub",
                url=link,
                summary=str(row.get("summary") or "").strip(),
                payload=row,
            )
        )
        if len(items) >= limit:
            break
    return items


def _fetch_yahoo_rss_market_news(*, target_date: date, limit: int = 200) -> List[MarketNewsItem]:
    request = urllib.request.Request(
        "https://news.yahoo.com/rss/finance",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        root = ElementTree.fromstring(payload)
    except Exception:
        return []
    items: List[MarketNewsItem] = []
    for entry in root.findall("./channel/item"):
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        summary = html.unescape((entry.findtext("description") or "").strip())
        source = (entry.findtext("source") or "").strip() or "Yahoo Finance"
        if not title or not link:
            continue
        date_time = None
        pub_raw = (entry.findtext("pubDate") or "").strip()
        if pub_raw:
            try:
                date_time = parsedate_to_datetime(pub_raw)
                if date_time.tzinfo is None:
                    date_time = date_time.replace(tzinfo=timezone.utc)
            except Exception:
                date_time = None
        news_date = date_time.date() if date_time else target_date
        if news_date != target_date:
            continue
        items.append(
            MarketNewsItem(
                news_date=news_date,
                date_time=date_time,
                headline=title,
                source=source,
                source_tag="yahoo",
                url=link,
                summary=summary,
                payload={
                    "title": title,
                    "link": link,
                    "description": summary,
                    "source": source,
                    "pubDate": pub_raw,
                },
            )
        )
        if len(items) >= limit:
            break
    return items


def _build_market_daily_report_prompt(
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    prompt_style: str,
    output_language: str,
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    normalized = str(prompt_style or "simple").strip().lower()
    if normalized == "structured":
        return (
            f"Summarize all market news for {target_date.isoformat()} into a structured daily market report.\n"
            "Keep all material market-moving points, remove duplicates, and rank the content by importance.\n"
            "Use layered sections and bullet points.\n"
            f"{language_line}"
            f"News items JSON:\n{items_json}\n"
        )
    return (
        f"Please summarize all market news for {target_date.isoformat()}.\n"
        "Help the reader quickly understand what happened in the market that day, the key narratives, and what mattered most.\n"
        "Remove duplicates and keep the important information.\n"
        "Use layered structure.\n"
        f"{language_line}"
        f"News items JSON:\n{items_json}\n"
    )


def _upsert_market_daily_summary_shared(
    *,
    summary_date: date,
    provider: str,
    model: str,
    prompt_style: str,
    news_sources: str,
    input_payload: Dict[str, Any],
    output_text: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM market_news_daily_summary
                WHERE summary_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                """,
                (summary_date, provider, prompt_style),
            )
            cur.execute(
                """
                INSERT INTO market_news_daily_summary (
                    summary_date, provider, model, prompt_style, news_sources, input_payload, output_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (summary_date, provider, model, prompt_style, news_sources, json.dumps(input_payload, ensure_ascii=False), output_text),
            )
        conn.commit()


def _get_market_daily_summaries_shared(summary_date: date) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, summary_date, provider, model, prompt_style, news_sources, input_payload, output_text, created_at
                FROM market_news_daily_summary
                WHERE summary_date = %s
                ORDER BY created_at DESC, id DESC
                """,
                (summary_date,),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "summary_date": row["summary_date"].isoformat(),
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "news_sources": row["news_sources"] or "",
            "input_payload": row["input_payload"],
            "output_text": row["output_text"] or "",
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def _generate_market_research_text(*, provider_name: str, model: str, prompt: str) -> str:
    normalized = str(provider_name or DEFAULT_MARKET_PROVIDER).strip().lower()
    if normalized == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for market macro research.")
        return generate_text_with_web_search(
            api_key=api_key,
            model=model,
            prompt=prompt,
            timeout_sec=180,
        )
    provider = get_news_provider(normalized, model=model, timeout_sec=180)
    with usage_context("market_news_summary", module="market"):
        return provider.generate_text(prompt=prompt)


# ---------------------------------------------------------------------------
# Market weekly / monthly reports
# ---------------------------------------------------------------------------

MARKET_REPORT_KEY = "__market__"


def generate_market_weekly_report(
    *,
    target_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    from market_agent.utils.week import week_boundaries
    from market_agent.services.company.reports import _store_weekly_report
    from market_agent.services.company._helpers import _build_output_language_line

    week_start, week_end = week_boundaries(target_date)
    daily_summaries = []
    current = week_start
    while current <= week_end:
        items = list_market_raw_news(target_date=current, limit=50)
        summaries = _get_market_daily_summaries_shared(current)
        if summaries:
            daily_summaries.append({
                "date": current.isoformat(),
                "summary": summaries[-1].get("output_text", ""),
            })
        elif items:
            headlines = [it.get("headline", "") for it in items[:20]]
            daily_summaries.append({
                "date": current.isoformat(),
                "headlines": headlines,
            })
        current += timedelta(days=1)

    if not daily_summaries:
        return {"generated": False, "week_start": week_start.isoformat(), "week_end": week_end.isoformat()}

    import json as _json
    context = _json.dumps(daily_summaries, ensure_ascii=False, indent=1)
    lang_line = _build_output_language_line(output_language)
    prompt = (
        "You are a senior market analyst. Synthesize the following daily market summaries "
        f"for the week of {week_start.isoformat()} to {week_end.isoformat()} into a comprehensive "
        "weekly market report.\n\n"
        "Return a JSON object with these keys (each is a list of bullet-point strings):\n"
        "summary, sentiment, facts, viewpoint, reasoning, uncertainties, short_term_impact, long_term_impact, trends\n\n"
        f"{lang_line}\n"
        "Return ONLY valid JSON.\n\n"
        f"Daily summaries:\n{context}"
    )

    provider = get_news_provider(provider_name, model=model, timeout_sec=120)
    with usage_context("market_weekly_report", module="market"):
        raw = provider.generate_text(prompt=prompt)

    try:
        report = _json.loads(raw) if isinstance(raw, str) else {}
    except _json.JSONDecodeError:
        report = {"summary": [raw]}

    if not isinstance(report, dict):
        report = {"summary": [str(report)]}

    _store_weekly_report(MARKET_REPORT_KEY, start_date=week_start, end_date=week_end, report_payload=report)
    return {"generated": True, "week_start": week_start.isoformat(), "week_end": week_end.isoformat()}


def generate_market_monthly_report(
    *,
    month: str,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    from market_agent.services.company.reports import get_news_report, _store_weekly_report
    from market_agent.services.company._helpers import _build_output_language_line
    from market_agent.utils.week import week_boundaries

    month_start = date.fromisoformat(f"{month}-01")
    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

    weekly_reports = []
    current = month_start
    while current <= month_end:
        ws, we = week_boundaries(current)
        if current == we:
            report = get_news_report(MARKET_REPORT_KEY, beginning_date=ws, end_date=we)
            if report:
                weekly_reports.append({"week_start": ws.isoformat(), "week_end": we.isoformat(), "report": report})
        current += timedelta(days=1)

    if not weekly_reports:
        return {"generated": False, "month": month}

    import json as _json
    context = _json.dumps(weekly_reports, ensure_ascii=False, indent=1)
    lang_line = _build_output_language_line(output_language)
    prompt = (
        f"You are a senior market analyst. Synthesize the following weekly market reports "
        f"for {month} into a comprehensive monthly market report.\n\n"
        "Return a JSON object with these keys (each is a list of bullet-point strings):\n"
        "summary, sentiment, facts, viewpoint, reasoning, trends\n\n"
        f"{lang_line}\n"
        "Return ONLY valid JSON.\n\n"
        f"Weekly reports:\n{context}"
    )

    provider = get_news_provider(provider_name, model=model, timeout_sec=120)
    with usage_context("market_monthly_report", module="market"):
        raw = provider.generate_text(prompt=prompt)

    try:
        report = _json.loads(raw) if isinstance(raw, str) else {}
    except _json.JSONDecodeError:
        report = {"summary": [raw]}

    if not isinstance(report, dict):
        report = {"summary": [str(report)]}

    _store_weekly_report(MARKET_REPORT_KEY, start_date=month_start, end_date=month_end, report_payload=report)
    return {"generated": True, "month": month}
