"""Report functions: daily, weekly, monthly reports and daily clusters."""

from __future__ import annotations

import json
import logging
import time as pytime
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.llms.news_registry import get_news_provider
from market_agent.llms.prompts.news_analysis_structured import ANALYSIS_FIELDS
from market_agent.utils.week import week_boundaries
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_STORY_KEY,
    TBL_COMPANY_NEWS_DAILY_CLUSTER,
)
from market_agent.services.company._constants import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PRICE_ANALYSIS_REPORT_LIMIT,
)
from market_agent.services.company._helpers import (
    _as_text,
    _build_output_language_line,
    _decode_llm_content,
    _ensure_news_schema,
    _normalize_company_name,
    _normalize_story_key,
    _normalize_story_record,
    _parse_json_object,
)
from market_agent.services.company.prompts import (
    _build_company_daily_cluster_prompt,
    _build_company_daily_report_prompt,
)
from market_agent.llms.usage_context import usage_context
from market_agent.services.company.news_crud import (
    get_company_news_for_range,
)

logger = logging.getLogger("uvicorn.error")


def get_news_report(
    company_name: str, *, beginning_date: date, end_date: date
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content FROM news_report
                WHERE company_name = %s AND beginning_date = %s AND end_date = %s
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
                SELECT provider, model, prompt_style, input_payload, output_text, created_at
                FROM company_news_daily_report
                WHERE company_name = %s AND report_date = %s AND provider = %s AND prompt_style = %s
                ORDER BY created_at DESC, id DESC LIMIT 1
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
                    report_date, provider, model, prompt_style, input_payload, output_text, created_at
                FROM company_news_daily_report
                WHERE company_name = %s AND report_date >= %s AND report_date <= %s AND provider = %s AND prompt_style = %s
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
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    items = _build_weekly_report_input_items(company_name, start_date=start_date, end_date=end_date, llm_model=model, provider_name=provider_name)
    if not items:
        return None
    with usage_context("company_weekly_report", company_name=company_name, module="company"):
        report = provider.fetch_weekly_report(company_name=company_name, start_date=start_date.isoformat(), end_date=end_date.isoformat(), articles=items, output_language=output_language)
    _store_weekly_report(company_name, start_date=start_date, end_date=end_date, report_payload=report)
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
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    weekly_reports = _build_monthly_report_input_items(company_name, month_start=month_start, month_end=month_end)
    if not weekly_reports:
        return None
    prompt = _build_company_monthly_report_prompt(company_name, month_start=month_start, month_end=month_end, weekly_reports=weekly_reports, output_language=output_language)
    with usage_context("company_monthly_report", company_name=company_name, module="company"):
        payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    report = _normalize_structured_period_report(payload)
    if not any(report.values()):
        return None
    _store_weekly_report(company_name, start_date=month_start, end_date=month_end, report_payload=report)
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
    items = _build_company_daily_report_input_items(company_name, target_date=target_date, llm_model=model)
    if not items:
        return {"generated": False, "item_count": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    prompt = _build_company_daily_report_prompt(company_name, target_date=target_date, items=items, prompt_style=prompt_style, output_language=output_language)
    with usage_context("company_daily_report", company_name=company_name, module="company"):
        output_text = provider.generate_text(prompt=prompt)
    _upsert_company_daily_report(company_name=company_name, report_date=target_date, provider=provider_name, model=model, prompt_style=prompt_style, input_payload={"items": items, "prompt": prompt}, output_text=output_text)
    return {"generated": True, "item_count": len(items), "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}


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
                SELECT * FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                WHERE company_name = %s AND cluster_date = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s
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
    items = _build_company_story_incremental_news_items(company_name, target_date=target_date, llm_model=model, output_language=output_language)
    if not items:
        return {"generated": False, "cluster_count": 0, "target_date": target_date.isoformat()}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    prompt = _build_company_daily_cluster_prompt(company_name, target_date=target_date, items=items, output_language=output_language)
    with usage_context("company_daily_clusters", company_name=company_name, module="company"):
        payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    clusters = _normalize_company_cluster_rows(company_name=company_name, target_date=target_date, payload=payload)
    _replace_company_daily_clusters(company_name=company_name, target_date=target_date, clusters=clusters, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"items": items, "prompt": prompt})
    return {"generated": True, "cluster_count": len(clusters), "target_date": target_date.isoformat()}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_company_daily_report_input_items(
    company_name: str, *, target_date: date, llm_model: str = DEFAULT_MODEL,
) -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(company_name, start_date=target_date, end_date=target_date, llm_model=llm_model)
    items: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, datetime]] = set()
    for article in articles:
        key = (article.news_title, article.news_date_time)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        content = _decode_llm_content(article.llm_analyzed_content, article.original_content)
        items.append({
            "news_date_time": article.news_date_time.isoformat(),
            "news_title": article.news_title,
            "news_source": article.news_source,
            "news_source_link": article.news_source_link,
            "original_content": article.original_content,
            "analyzed_content": content if article.llm_analyzed_content else None,
            "is_analyzed": bool(article.is_analyzed),
        })
    return items


def _build_company_story_incremental_news_items(
    company_name: str, *, target_date: date, llm_model: str = DEFAULT_MODEL, output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    articles = get_company_news_for_range(company_name, start_date=target_date, end_date=target_date, llm_model=llm_model, output_language=output_language)
    items: List[Dict[str, Any]] = []
    for article in sorted(articles, key=lambda item: (item.news_date_time, item.id or 0)):
        decoded = _decode_llm_content(article.llm_analyzed_content, article.original_content)
        items.append({
            "news_id": int(article.id or 0),
            "news_date_time": article.news_date_time.isoformat(),
            "news_title": article.news_title,
            "news_source": article.news_source,
            "news_source_link": article.news_source_link,
            "summary": decoded.get("summary") or article.original_content or "",
        })
    return items


def _build_weekly_report_input_items(
    company_name: str, *, start_date: date, end_date: date, llm_model: str, provider_name: str,
) -> List[Dict[str, Any]]:
    all_daily_reports = get_company_daily_reports_for_range(company_name, start_date=start_date, end_date=end_date, provider_name=provider_name, prompt_style="simple")
    daily_reports = all_daily_reports[:PRICE_ANALYSIS_REPORT_LIMIT]
    if not daily_reports:
        return []
    items: List[Dict[str, Any]] = []
    for report in sorted(daily_reports, key=lambda x: x["report_date"]):
        items.append({
            "news_title": f"Daily report for {company_name}",
            "news_date_time": report["report_date"],
            "news_source": "company_daily_report",
            "news_source_link": None,
            "summary": report["output_text"],
            "facts": [], "viewpoint": [], "reasoning": [], "uncertainties": [],
            "short_term_impact": [], "long_term_impact": [], "priced_in": [],
            "insider_signals": [], "trends": [], "sentiment": [],
        })
    return items


def _build_monthly_report_input_items(
    company_name: str, *, month_start: date, month_end: date,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    current_day = month_start
    while current_day <= month_end:
        wb_start, wb_end = week_boundaries(current_day)
        if current_day == wb_end:
            report = get_news_report(company_name, beginning_date=wb_start, end_date=wb_end)
            if report:
                items.append({
                    "week_start": wb_start.isoformat(),
                    "week_end": wb_end.isoformat(),
                    "summary": _render_period_report_as_text(report),
                    "report": report,
                })
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
    company_name: str, *, month_start: date, month_end: date, weekly_reports: List[Dict[str, Any]], output_language: str,
) -> str:
    lang_line = _build_output_language_line(output_language)
    return (
        f"You are a senior equity research analyst writing a monthly intelligence report for {company_name} "
        f"covering {month_start.isoformat()} to {month_end.isoformat()}.\n\n"
        "Your input is the weekly reports for this month. Synthesize them into a higher-level monthly view.\n\n"
        "Your goal is NOT to repeat weekly details — it's to identify the month's key narrative arcs, "
        "what structurally changed, and what matters going forward.\n\n"
        f"{lang_line}"
        "Return a JSON object with these sections (each is an array of bullet-point strings):\n\n"
        "1. **summary** (3-5 bullets): The month's most important developments ranked by significance. "
        "What would an investor need to know if they were away for a month?\n\n"
        "2. **key_storylines** (2-4 bullets): Major narrative arcs that evolved across the month. "
        "For each: what started, how it developed, and where it stands now.\n\n"
        "3. **structural_changes** (2-3 bullets): Anything that fundamentally changed about the company's "
        "position, competitive landscape, or market perception this month.\n\n"
        "4. **catalysts_ahead** (2-4 bullets): What's coming next month that could move the stock. "
        "Include dates if known.\n\n"
        "5. **sentiment** (2-3 bullets): How market sentiment shifted over the month. "
        "Net bullish/bearish, analyst consensus direction, flow signals.\n\n"
        "6. **viewpoint** (2-3 bullets): Your analytical take — what does this month mean for the "
        "investment thesis? What's the market getting right/wrong?\n\n"
        "7. **reasoning** (2-3 bullets): If-then logic about what happens next based on this month's data.\n\n"
        "8. **trends** (2-3 bullets): Multi-month structural trends confirmed or challenged.\n\n"
        "Rules:\n"
        "- RANK by importance within each section\n"
        "- Be CONCISE — each bullet 1-2 sentences max\n"
        "- DEDUPLICATE across weeks — synthesize, don't concatenate\n"
        "- Tag [HIGH IMPACT] items with outsized significance\n"
        "- Focus on WHAT CHANGED, not what stayed the same\n\n"
        "Weekly reports JSON:\n"
        f"{json.dumps(weekly_reports, ensure_ascii=False, indent=2)}\n"
    )


def _normalize_company_cluster_rows(*, company_name: str, target_date: date, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        normalized.append({
            "company_name": company_name,
            "cluster_date": target_date,
            "cluster_key": cluster_key,
            "cluster_title": title,
            "cluster_summary": summary or title,
            "source_news": source_news,
        })
    return normalized


def _replace_company_daily_clusters(
    *, company_name: str, target_date: date, clusters: List[Dict[str, Any]],
    provider_name: str, model: str, prompt_style: str, output_language: str, input_payload: Dict[str, Any],
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER} WHERE company_name = %s AND cluster_date = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s",
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
                    (company_name, item["cluster_date"], item["cluster_key"], item["cluster_title"], item["cluster_summary"],
                     json.dumps(item.get("source_news") or [], ensure_ascii=False), provider_name, model, prompt_style, output_language,
                     json.dumps(input_payload, ensure_ascii=False)),
                )
        conn.commit()


def _store_weekly_report(company_name: str, *, start_date: date, end_date: date, report_payload: Optional[Dict[str, Any]]) -> None:
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
    *, company_name: str, report_date: date, provider: str, model: str, prompt_style: str,
    input_payload: Dict[str, Any], output_text: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM company_news_daily_report
                WHERE company_name = %s AND report_date = %s AND provider = %s AND prompt_style = %s
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (company_name, report_date, provider, prompt_style),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE company_news_daily_report SET model = %s, input_payload = %s, output_text = %s, created_at = NOW() WHERE id = %s",
                    (model, json.dumps(input_payload), output_text, existing["id"]),
                )
                cur.execute(
                    "DELETE FROM company_news_daily_report WHERE company_name = %s AND report_date = %s AND provider = %s AND prompt_style = %s AND id <> %s",
                    (company_name, report_date, provider, prompt_style, existing["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO company_news_daily_report (company_name, report_date, provider, model, prompt_style, input_payload, output_text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (company_name, report_date, provider, model, prompt_style, json.dumps(input_payload), output_text),
                )
        conn.commit()


def _build_company_story_cluster_input_items(
    *, company_name: str, start_date: date, end_date: date, provider_name: str, prompt_style: str, output_language: str,
) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cluster_date, cluster_key, cluster_title, cluster_summary, source_news_json
                FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER}
                WHERE company_name = %s AND cluster_date >= %s AND cluster_date <= %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s
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
