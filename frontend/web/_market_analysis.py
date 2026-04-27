"""Market summary DB operations and LLM calls.

Extracted from server.py — no logic changes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.llms.openai_analysis import chat_completion
from market_agent.utils.week import week_boundaries
from market_agent.schema_fields import (
    COL_HEADLINE,
    COL_INPUT_PAYLOAD,
    COL_MODEL,
    COL_NEWS_DATE,
    COL_NEWS_SOURCES,
    COL_NEWS_URL,
    COL_OUTPUT_JSON,
    COL_OUTPUT_LANGUAGE,
    COL_OUTPUT_TEXT,
    COL_PAYLOAD,
    COL_PROMPT_STYLE,
    COL_PROVIDER,
    COL_SNAPSHOT_DATE,
    COL_SOURCE,
    COL_SOURCE_TAG,
    TBL_MARKET_NEWS_DAILY_SUMMARY,
    TBL_MARKET_NEWS_ITEM_ANALYSIS,
    TBL_MARKET_PRICE_ANALYSIS_DAILY,
    TBL_MARKET_PRICE_DAILY_SNAPSHOT,
)

logger = logging.getLogger("uvicorn.error")

US_MARKET_TZ = ZoneInfo("America/New_York")


def _ensure_market_price_snapshot_schema() -> None:
    ensure_database_schema()


def _get_market_price_snapshot(snapshot_date: date) -> Optional[Dict[str, Any]]:
    _ensure_market_price_snapshot_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {COL_PAYLOAD}
                FROM {TBL_MARKET_PRICE_DAILY_SNAPSHOT}
                WHERE {COL_SNAPSHOT_DATE} = %s
                LIMIT 1
                """,
                (snapshot_date,),
            )
            row = cur.fetchone()
    if not row:
        return None
    raw_payload = row.get(COL_PAYLOAD)
    if not isinstance(raw_payload, str):
        return None
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return None
    return payload


def _upsert_market_price_snapshot(snapshot_date: date, payload: Dict[str, Any]) -> None:
    _ensure_market_price_snapshot_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_PRICE_DAILY_SNAPSHOT} ({COL_SNAPSHOT_DATE}, {COL_PAYLOAD})
                VALUES (%s, %s)
                ON CONFLICT ({COL_SNAPSHOT_DATE})
                DO UPDATE SET
                    {COL_PAYLOAD} = EXCLUDED.{COL_PAYLOAD},
                    updated_at = NOW()
                """,
                (snapshot_date, json.dumps(payload)),
            )
        conn.commit()


def _ensure_market_daily_summary_schema() -> None:
    ensure_database_schema()


def _ensure_market_news_item_analysis_schema() -> None:
    ensure_database_schema()


def _upsert_market_daily_summary(
    *,
    summary_date: date,
    provider: str,
    model: str,
    prompt_style: str,
    news_sources: str,
    input_payload: Dict[str, Any],
    output_text: str,
) -> Dict[str, Any]:
    _ensure_market_daily_summary_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id
                FROM {TBL_MARKET_NEWS_DAILY_SUMMARY}
                WHERE summary_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (
                    summary_date,
                    provider,
                    prompt_style,
                ),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    f"""
                    UPDATE {TBL_MARKET_NEWS_DAILY_SUMMARY}
                    SET model = %s,
                        {COL_NEWS_SOURCES} = %s,
                        input_payload = %s,
                        output_text = %s,
                        created_at = NOW()
                    WHERE id = %s
                    RETURNING id, summary_date, provider, model, prompt_style, {COL_NEWS_SOURCES}, created_at
                    """,
                    (
                        model,
                        news_sources,
                        json.dumps(input_payload),
                        output_text,
                        existing["id"],
                    ),
                )
                row = cur.fetchone()
                cur.execute(
                    f"""
                    DELETE FROM {TBL_MARKET_NEWS_DAILY_SUMMARY}
                    WHERE summary_date = %s
                      AND provider = %s
                      AND prompt_style = %s
                      AND id <> %s
                    """,
                    (
                        summary_date,
                        provider,
                        prompt_style,
                        row["id"],
                    ),
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO {TBL_MARKET_NEWS_DAILY_SUMMARY} (
                        summary_date,
                        provider,
                        model,
                        prompt_style,
                        {COL_NEWS_SOURCES},
                        input_payload,
                        output_text
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, summary_date, provider, model, prompt_style, {COL_NEWS_SOURCES}, created_at
                    """,
                    (
                        summary_date,
                        provider,
                        model,
                        prompt_style,
                        news_sources,
                        json.dumps(input_payload),
                        output_text,
                    ),
                )
                row = cur.fetchone()
        conn.commit()
    return {
        "id": int(row["id"]),
        "summary_date": row["summary_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "news_sources": row[COL_NEWS_SOURCES] or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _upsert_market_news_item_analysis(
    *,
    news_date: date,
    news_url: str,
    headline: str,
    source: str,
    source_tag: str,
    provider: str,
    model: str,
    output_language: str,
    prompt_style: str,
    input_payload: Dict[str, Any],
    output_text: str,
) -> Dict[str, Any]:
    _ensure_market_news_item_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_NEWS_ITEM_ANALYSIS} (
                    {COL_NEWS_DATE},
                    {COL_NEWS_URL},
                    {COL_HEADLINE},
                    {COL_SOURCE},
                    {COL_SOURCE_TAG},
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_PROMPT_STYLE},
                    {COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_TEXT}
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ({COL_NEWS_DATE}, {COL_NEWS_URL}, {COL_MODEL}, {COL_OUTPUT_LANGUAGE}, {COL_PROMPT_STYLE})
                DO UPDATE SET
                    {COL_HEADLINE} = EXCLUDED.{COL_HEADLINE},
                    {COL_SOURCE} = EXCLUDED.{COL_SOURCE},
                    {COL_SOURCE_TAG} = EXCLUDED.{COL_SOURCE_TAG},
                    {COL_PROVIDER} = EXCLUDED.{COL_PROVIDER},
                    {COL_INPUT_PAYLOAD} = EXCLUDED.{COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_TEXT} = EXCLUDED.{COL_OUTPUT_TEXT},
                    updated_at = NOW()
                RETURNING
                    id,
                    {COL_NEWS_DATE},
                    {COL_NEWS_URL},
                    {COL_HEADLINE},
                    {COL_SOURCE},
                    {COL_SOURCE_TAG},
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_PROMPT_STYLE},
                    {COL_OUTPUT_TEXT},
                    updated_at
                """,
                (
                    news_date,
                    news_url,
                    headline,
                    source,
                    source_tag,
                    provider,
                    model,
                    output_language,
                    prompt_style,
                    json.dumps(input_payload),
                    output_text,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {
        "id": int(row["id"]),
        "news_date": row[COL_NEWS_DATE].isoformat(),
        "news_url": row[COL_NEWS_URL],
        "headline": row[COL_HEADLINE],
        "source": row[COL_SOURCE] or "",
        "source_tag": row[COL_SOURCE_TAG] or "",
        "provider": row[COL_PROVIDER],
        "model": row[COL_MODEL],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "prompt_style": row[COL_PROMPT_STYLE],
        "output_text": row[COL_OUTPUT_TEXT],
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_market_news_item_analyses(
    *,
    news_date: date,
    model: str,
    output_language: str,
) -> List[Dict[str, Any]]:
    _ensure_market_news_item_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    {COL_NEWS_DATE},
                    {COL_NEWS_URL},
                    {COL_HEADLINE},
                    {COL_SOURCE},
                    {COL_SOURCE_TAG},
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_PROMPT_STYLE},
                    {COL_OUTPUT_TEXT},
                    updated_at
                FROM {TBL_MARKET_NEWS_ITEM_ANALYSIS}
                WHERE {COL_NEWS_DATE} = %s
                  AND {COL_MODEL} = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                """,
                (news_date, model, output_language),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "news_date": row[COL_NEWS_DATE].isoformat(),
            "news_url": row[COL_NEWS_URL],
            "headline": row[COL_HEADLINE],
            "source": row[COL_SOURCE] or "",
            "source_tag": row[COL_SOURCE_TAG] or "",
            "provider": row[COL_PROVIDER],
            "model": row[COL_MODEL],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "prompt_style": row[COL_PROMPT_STYLE],
            "output_text": row[COL_OUTPUT_TEXT],
            "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def _get_market_daily_summaries(summary_date: date) -> List[Dict[str, Any]]:
    _ensure_market_daily_summary_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    summary_date,
                    provider,
                    model,
                    prompt_style,
                    {COL_NEWS_SOURCES},
                    input_payload,
                    output_text,
                    created_at
                FROM {TBL_MARKET_NEWS_DAILY_SUMMARY}
                WHERE summary_date = %s
                ORDER BY
                    CASE provider
                        WHEN 'openai' THEN 0
                        WHEN 'perplexity' THEN 1
                        WHEN 'gemini' THEN 2
                        ELSE 99
                    END,
                    created_at DESC,
                    id DESC
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
            "news_sources": row[COL_NEWS_SOURCES] or "",
            "input_payload": row["input_payload"],
            "output_text": row["output_text"],
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def _ensure_market_price_analysis_schema() -> None:
    ensure_database_schema()


def _parse_json_object_text(text: str) -> Optional[Dict[str, Any]]:
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


def _normalize_market_prices_analysis_payload(raw_output: str) -> Dict[str, Any]:
    payload = _parse_json_object_text(raw_output) or {}
    main_narrative = str(
        payload.get("main_narrative")
        or payload.get("us_market_logic")
        or payload.get("rotation_take")
        or raw_output
        or ""
    ).strip()
    section_notes_raw = payload.get("section_notes") if isinstance(payload.get("section_notes"), list) else []
    section_notes: List[Dict[str, str]] = []
    for item in section_notes_raw:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if not summary:
            continue
        section_notes.append(
            {
                "section_key": str(item.get("section_key") or "").strip(),
                "section_label": str(item.get("section_label") or item.get("section_key") or "Section").strip(),
                "summary": summary,
            }
        )
    return {
        "main_narrative": main_narrative,
        "us_market_logic": str(payload.get("us_market_logic") or "").strip(),
        "rotation_take": str(payload.get("rotation_take") or "").strip(),
        "section_notes": section_notes,
        "signals": [str(item).strip() for item in (payload.get("signals") or []) if str(item).strip()],
        "risks": [str(item).strip() for item in (payload.get("risks") or []) if str(item).strip()],
    }


def _upsert_market_price_analysis(
    *,
    analysis_date: date,
    provider: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
    output_json: Dict[str, Any],
    output_text: str,
) -> Dict[str, Any]:
    _ensure_market_price_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_PRICE_ANALYSIS_DAILY} (
                    analysis_date,
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_PROMPT_STYLE},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_JSON},
                    {COL_OUTPUT_TEXT}
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (analysis_date, {COL_PROVIDER}, {COL_PROMPT_STYLE}, {COL_OUTPUT_LANGUAGE})
                DO UPDATE SET
                    {COL_MODEL} = EXCLUDED.{COL_MODEL},
                    {COL_INPUT_PAYLOAD} = EXCLUDED.{COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_JSON} = EXCLUDED.{COL_OUTPUT_JSON},
                    {COL_OUTPUT_TEXT} = EXCLUDED.{COL_OUTPUT_TEXT},
                    updated_at = NOW()
                RETURNING
                    id,
                    analysis_date,
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_PROMPT_STYLE},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_JSON},
                    {COL_OUTPUT_TEXT},
                    created_at,
                    updated_at
                """,
                (
                    analysis_date,
                    provider,
                    model,
                    prompt_style,
                    output_language,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(output_json, ensure_ascii=False),
                    output_text,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    structured = _parse_json_object_text(row[COL_OUTPUT_JSON] or "") or {}
    return {
        "id": int(row["id"]),
        "analysis_date": row["analysis_date"].isoformat(),
        "provider": row[COL_PROVIDER],
        "model": row[COL_MODEL],
        "prompt_style": row[COL_PROMPT_STYLE],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "input_payload": _parse_json_object_text(row[COL_INPUT_PAYLOAD] or "") or {},
        "output_json": structured,
        "output_text": row[COL_OUTPUT_TEXT],
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_market_price_analysis(
    *,
    analysis_date: date,
    provider: str = "openai",
    prompt_style: str = "prices_v1",
    output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    _ensure_market_price_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    analysis_date,
                    {COL_PROVIDER},
                    {COL_MODEL},
                    {COL_PROMPT_STYLE},
                    {COL_OUTPUT_LANGUAGE},
                    {COL_INPUT_PAYLOAD},
                    {COL_OUTPUT_JSON},
                    {COL_OUTPUT_TEXT},
                    created_at,
                    updated_at
                FROM {TBL_MARKET_PRICE_ANALYSIS_DAILY}
                WHERE analysis_date = %s
                  AND {COL_PROVIDER} = %s
                  AND {COL_PROMPT_STYLE} = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (analysis_date, provider, prompt_style, output_language),
            )
            row = cur.fetchone()
    if not row:
        return None
    structured = _parse_json_object_text(row[COL_OUTPUT_JSON] or "") or {}
    return {
        "id": int(row["id"]),
        "analysis_date": row["analysis_date"].isoformat(),
        "provider": row[COL_PROVIDER],
        "model": row[COL_MODEL],
        "prompt_style": row[COL_PROMPT_STYLE],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "input_payload": _parse_json_object_text(row[COL_INPUT_PAYLOAD] or "") or {},
        "output_json": structured,
        "output_text": row[COL_OUTPUT_TEXT],
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_market_summary_dates(
    *,
    start_date: date,
    end_date: date,
) -> List[Dict[str, Any]]:
    _ensure_market_daily_summary_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    summary_date,
                    COUNT(*) AS summary_count,
                    COUNT(DISTINCT provider) AS provider_count
                FROM {TBL_MARKET_NEWS_DAILY_SUMMARY}
                WHERE summary_date >= %s
                  AND summary_date <= %s
                GROUP BY summary_date
                ORDER BY summary_date DESC
                """,
                (start_date, end_date),
            )
            rows = cur.fetchall()
    return [
        {
            "date": row["summary_date"].isoformat(),
            "summary_count": int(row["summary_count"] or 0),
            "provider_count": int(row["provider_count"] or 0),
        }
        for row in rows
    ]


def _build_market_news_summary_prompt(
    items: List[Dict[str, Any]],
    *,
    prompt_style: str,
    output_language: str = "zh-CN",
) -> str:
    news_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_market_output_language_line(output_language)
    if prompt_style == "simple":
        return (
            "Please summarize all market news below for me.\n"
            "This summary should help me quickly understand what happened in today's market "
            "and what the impact is.\n"
            "Ignore duplicate or near-duplicate news items and avoid repeating the same information in the summary.\n"
            "Keep all material points in the news and do not omit important information.\n"
            "Ignore points that are not related to the market.\n"
            "Rank information by importance (most important first).\n"
            "For each item, try to open the link first for fuller context. If the link is inaccessible, "
            "use web search and analyze based on best available information.\n\n"
            f"{language_line}"
            "Use layered structure for output which is easy for reading.\n\n"
            f"News items JSON:\n{news_json}\n"
        )
    return (
        "Summarize all market news below into a structured daily market brief.\n"
        "Use bullet points and focus on decision-useful content.\n"
        "For each item, try to open the link first for fuller context. If inaccessible, use web search.\n"
        "Sections to include:\n"
        "1. Summary\n"
        "2. Facts\n"
        "3. Viewpoint\n"
        "4. Reasoning\n"
        "5. Uncertainties\n"
        "6. Short-term impact\n"
        "7. Long-term impact\n"
        "8. Priced in\n"
        "9. Insider signals\n"
        "10. Trends\n"
        "11. Sentiment\n\n"
        f"{language_line}"
        f"News items JSON:\n{news_json}\n"
    )


def _build_market_prices_analysis_prompt(
    *,
    context: Dict[str, Any],
    output_language: str,
) -> str:
    language_line = _build_market_output_language_line(output_language)
    return (
        f"You are explaining what drove the US stock market on {context['analysis_date']}.\n"
        "Use the structured market snapshot, nearby macro events, and same-day market news.\n"
        "Focus on cross-asset logic and rotation, not just headlines.\n"
        "The output must be US-centered, while using global markets as supporting context.\n"
        "Explain what price action across equities, rates, commodities, crypto, and regions suggests about today's market regime.\n"
        "Return strict JSON only with this schema:\n"
        "{\n"
        '  "main_narrative": string,\n'
        '  "us_market_logic": string,\n'
        '  "rotation_take": string,\n'
        '  "section_notes": [\n'
        '    {"section_key": string, "section_label": string, "summary": string}\n'
        "  ],\n"
        '  "signals": [string],\n'
        '  "risks": [string]\n'
        "}\n"
        "Keep section_notes concise and decision-useful.\n"
        f"{language_line}"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"
    )


def _build_market_prices_analysis_context(
    *,
    target_date: date,
) -> Dict[str, Any]:
    from frontend.web._market_data import (
        _fetch_market_news,
        _is_us_market_open_now,
        _is_us_trading_day,
        _previous_us_trading_day,
        _resolve_market_price_sections,
    )
    from market_agent.workflows import list_market_macro_events

    market_today = datetime.now(US_MARKET_TZ).date()
    price_target_date = target_date
    if not _is_us_trading_day(target_date):
        price_target_date = _previous_us_trading_day(target_date)
    elif target_date == market_today and _is_us_market_open_now():
        price_target_date = _previous_us_trading_day(target_date)
    sections, price_source, snapshot_exists = _resolve_market_price_sections(target_date=price_target_date)
    macro_rows = list_market_macro_events(
        start_date=target_date - timedelta(days=3),
        end_date=target_date + timedelta(days=7),
        limit=200,
    )
    trimmed_macro_rows = []
    for item in macro_rows[:16]:
        trimmed_macro_rows.append(
            {
                "event_name": item.get("event_name"),
                "event_date_time": item.get("event_date_time"),
                "country": item.get("country"),
                "category": item.get("category"),
                "actual_value": item.get("actual_value"),
                "previous_value": item.get("previous_value"),
                "consensus_value": item.get("consensus_value"),
                "unit": item.get("unit"),
            }
        )
    news_items = _fetch_market_news(target_date=target_date)
    trimmed_news_items = []
    for item in news_items[:24]:
        trimmed_news_items.append(
            {
                "headline": item.get("headline"),
                "source": item.get("source"),
                "source_tag": item.get("source_tag"),
                "datetime_text": item.get("datetime_text"),
                "url": item.get("url"),
                "summary": item.get("summary"),
            }
        )
    return {
        "analysis_date": target_date.isoformat(),
        "price_date": price_target_date.isoformat(),
        "price_data_source": price_source,
        "price_snapshot_exists": bool(snapshot_exists),
        "sections": sections,
        "macro_events": trimmed_macro_rows,
        "market_news": trimmed_news_items,
    }


def _generate_market_prices_analysis(
    *,
    target_date: date,
    provider_name: str,
    model: str,
    output_language: str,
    prompt_style: str = "prices_v1",
) -> Dict[str, Any]:
    context = _build_market_prices_analysis_context(target_date=target_date)
    prompt = _build_market_prices_analysis_prompt(context=context, output_language=output_language)
    raw_output = _run_market_news_summary(provider=provider_name, model=model, prompt=prompt)
    structured = _normalize_market_prices_analysis_payload(raw_output)
    return _upsert_market_price_analysis(
        analysis_date=target_date,
        provider=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload=context,
        output_json=structured,
        output_text=structured.get("main_narrative") or raw_output,
    )


def _build_market_output_language_line(output_language: str) -> str:
    normalized = str(output_language or "").strip().lower()
    if normalized in {"zh", "zh-cn", "zh_hans", "chinese", "simplified chinese"}:
        return "Write the output in Simplified Chinese.\n"
    return ""


def _build_market_single_news_prompt(
    *,
    item: Dict[str, Any],
    output_language: str,
) -> str:
    payload = json.dumps(item, ensure_ascii=False, indent=2)
    language_line = _build_market_output_language_line(output_language)
    return (
        "Analyze this single market news item.\n"
        "Focus on the key facts, why it matters for the market, and important risks/uncertainties.\n"
        "Try to open the source link first for fuller context; if inaccessible, use web search and best available information.\n"
        "Use a clear layered structure for easy reading.\n"
        f"{language_line}"
        f"News item JSON:\n{payload}\n"
    )


def _resolve_news_provider_for_model(model: str) -> str:
    from market_agent.llms.news_registry import list_news_models
    normalized_model = str(model or "").strip()
    for provider, models in list_news_models().items():
        if normalized_model in models:
            return provider
    return "openai"


def _run_market_news_summary(
    *,
    provider: str,
    model: str,
    prompt: str,
) -> str:
    normalized = str(provider or "openai").strip().lower()
    if normalized == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        return chat_completion(
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            timeout_sec=90,
        )
    if normalized == "perplexity":
        return _run_perplexity_text(model=model, prompt=prompt)
    if normalized == "gemini":
        return _run_gemini_text(model=model, prompt=prompt)
    raise RuntimeError(f"Unknown provider: {provider}")


def _run_perplexity_text(*, model: str, prompt: str) -> str:
    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY is required")
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Perplexity API error: {detail}") from exc
    choices = payload.get("choices") or []
    message = choices[0].get("message") if choices else {}
    text = str((message or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Perplexity returned empty output")
    return text


def _run_gemini_text(*, model: str, prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error: {detail}") from exc
    candidates = payload.get("candidates") or []
    content = candidates[0].get("content") if candidates else {}
    parts = (content or {}).get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty output")
    return text


def _group_news_items(
    company_name: str,
    articles: List[Any],
) -> List[Dict[str, Any]]:
    from market_agent.services.company import (
        get_company_daily_report,
        get_news_report,
        list_company_daily_clusters,
    )

    daily: Dict[date, List[Dict[str, Any]]] = {}
    weekly: Dict[date, List[Dict[str, Any]]] = {}
    monthly: Dict[date, List[Dict[str, Any]]] = {}
    today = datetime.now().date()

    for article in articles:
        news_date = article.news_date_time.date()
        week_start, _ = week_boundaries(news_date)
        month_start = news_date.replace(day=1)
        item = {
            "id": article.id,
            "news_title": article.news_title,
            "news_date_time": article.news_date_time.isoformat(),
            "news_source": article.news_source,
            "news_source_link": article.news_source_link,
            "is_analyzed": bool(article.is_analyzed),
            "is_filtered": bool(getattr(article, "is_filtered", False)),
            "content": _decode_news_content(
                article.llm_analyzed_content,
                article.original_content,
            ),
            "llm_response_raw": article.llm_analyzed_content,
            "original_content": article.original_content,
        }
        item["publisher"] = item["content"].get("publisher")
        daily.setdefault(news_date, []).append(item)
        weekly.setdefault(week_start, []).append(item)
        monthly.setdefault(month_start, []).append(item)

    groups: List[Dict[str, Any]] = []
    added_weeks: set[date] = set()
    added_months: set[date] = set()
    for day in sorted(daily.keys(), reverse=True):
        week_start, week_end = week_boundaries(day)
        month_start = day.replace(day=1)
        next_month = date(month_start.year + (1 if month_start.month == 12 else 0), 1 if month_start.month == 12 else month_start.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        if month_start not in added_months:
            month_items: List[Dict[str, Any]] = []
            cursor = month_start
            while cursor <= month_end:
                wb_start, wb_end = week_boundaries(cursor)
                if cursor == wb_end:
                    week_report = get_news_report(
                        company_name,
                        beginning_date=wb_start,
                        end_date=wb_end,
                    )
                    if week_report:
                        month_items.append(
                            {
                                "news_title": f"Week of {wb_start.isoformat()}",
                                "news_date_time": wb_end.isoformat(),
                                "report_start": wb_start.isoformat(),
                                "report_end": wb_end.isoformat(),
                                "report": week_report,
                            }
                        )
                cursor += timedelta(days=1)
            monthly_report = get_news_report(
                company_name,
                beginning_date=month_start,
                end_date=month_end,
            )
            month_label = month_start.strftime("%Y-%m")
            groups.append(
                {
                    "type": "monthly",
                    "key": f"month-{month_start.isoformat()}",
                    "label": month_label,
                    "items": month_items,
                    "report": monthly_report,
                    "report_start": month_start.isoformat(),
                    "report_end": month_end.isoformat(),
                }
            )
            added_months.add(month_start)
        if week_start not in added_weeks:
            week_items = weekly.get(week_start, [])
            report = get_news_report(
                company_name,
                beginning_date=week_start,
                end_date=week_end,
            )
            week_label = f"Week of {week_start.isoformat()}"
            groups.append(
                {
                    "type": "weekly",
                    "key": f"week-{week_start.isoformat()}",
                    "label": week_label,
                    "items": week_items,
                    "report": report,
                    "report_start": week_start.isoformat(),
                    "report_end": week_end.isoformat(),
                }
            )
            added_weeks.add(week_start)

        day_label = day.isoformat()
        daily_report = get_company_daily_report(
            company_name,
            report_date=day,
        )
        daily_clusters = list_company_daily_clusters(
            company_name,
            target_date=day,
            provider_name="openai",
            prompt_style="simple",
        )
        groups.append(
            {
                "type": "daily",
                "key": f"day-{day.isoformat()}",
                "label": day_label,
                "items": daily[day],
                "daily_report": daily_report,
                "daily_clusters": daily_clusters,
            }
        )
    return groups


def _decode_news_content(
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
