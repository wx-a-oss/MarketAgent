"""Status/price-intelligence functions."""

from __future__ import annotations

import json
import logging
import math
import time as pytime
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.llms.news_registry import get_news_provider
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_PAYLOAD,
    COL_POINT_DATE_TIME,
    COL_RANGE_KEY,
    COL_SNAPSHOT_DATE,
    TBL_COMPANY_PRICE_INTELLIGENCE_RUN,
    TBL_COMPANY_PRICE_MOVE_ANALYSIS,
    TBL_MARKET_PRICE_DAILY_SNAPSHOT,
)
from market_agent.services.company._constants import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PRICE_ANALYSIS_MARKET_SUMMARY_LIMIT,
    PRICE_ANALYSIS_RAW_FALLBACK_LIMIT,
    PRICE_ANALYSIS_REPORT_LIMIT,
)
from market_agent.services.company._helpers import (
    _as_text,
    _decode_llm_content,
    _ensure_news_schema,
    _normalize_company_name,
    _parse_json_object,
)
from market_agent.services.company.prompts import (
    _build_company_price_intelligence_prompt,
    _build_company_quick_price_intelligence_prompt,
)
from market_agent.llms.usage_context import usage_context
from market_agent.services.company.news_crud import (
    get_company_news_for_range,
)
from market_agent.services.company.reports import (
    get_company_daily_reports_for_range,
)

logger = logging.getLogger("uvicorn.error")


def get_company_status_snapshot(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    snapshot_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    params: List[Any] = [company_name, provider_name, prompt_style]
    where_extra = ""
    if snapshot_id is not None:
        where_extra = " AND id = %s"
        params.append(int(snapshot_id))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, as_of_date, window_start_date, window_end_date, provider, model, prompt_style,
                       input_payload, output_json, output_text, created_at
                FROM company_status_snapshot
                WHERE company_name = %s AND provider = %s AND prompt_style = %s {where_extra}
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        return None
    structured = _parse_json_object(row["output_json"] or "") or {}
    if not structured:
        structured = _normalize_company_status_payload({"output_markdown": row["output_text"] or ""}, as_of_date=row["as_of_date"])
    snapshot = {
        "id": int(row["id"]),
        "as_of_date": row["as_of_date"].isoformat(),
        "window_start_date": row["window_start_date"].isoformat(),
        "window_end_date": row["window_end_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "input_payload": row["input_payload"],
        "output_json": row["output_json"],
        "output_text": row["output_text"],
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }
    snapshot.update(structured)
    return snapshot


def list_company_status_snapshots(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, as_of_date, provider, model, prompt_style, output_json, output_text, created_at
                FROM company_status_snapshot
                WHERE company_name = %s AND provider = %s AND prompt_style = %s
                ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                (company_name, provider_name, prompt_style, safe_limit),
            )
            rows = cur.fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        structured = _parse_json_object(row["output_json"] or "") or {}
        result.append({
            "id": int(row["id"]),
            "as_of_date": row["as_of_date"].isoformat(),
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "price_position_summary": str(structured.get("price_position_summary") or ""),
            "technical_summary": str(structured.get("technical_summary") or structured.get("company_summary") or ""),
        })
    return result


def get_company_price_intelligence_run(
    company_name: str,
    *,
    run_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    where_sql = "company_name = %s"
    params: List[Any] = [company_name]
    if run_id is not None:
        where_sql += " AND id = %s"
        params.append(int(run_id))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, as_of_date, provider, model, {COL_OUTPUT_LANGUAGE},
                       context_window_days, focus_window_days, input_payload, output_json, output_text, created_at
                FROM {TBL_COMPANY_PRICE_INTELLIGENCE_RUN}
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        return None
    structured = _parse_json_object(row["output_json"] or "") or {}
    payload = {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "as_of_date": row["as_of_date"].isoformat(),
        "provider": row["provider"],
        "model": row["model"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "context_window_days": int(row["context_window_days"] or 0),
        "focus_window_days": int(row["focus_window_days"] or 0),
        "input_payload": _parse_json_object(row["input_payload"] or "") or {},
        "output_json": row["output_json"] or "",
        "output_text": row["output_text"] or "",
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(structured)
    return payload


def list_company_price_intelligence_runs(company_name: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, as_of_date, provider, model, {COL_OUTPUT_LANGUAGE},
                       context_window_days, focus_window_days, output_json, output_text, created_at
                FROM {TBL_COMPANY_PRICE_INTELLIGENCE_RUN}
                WHERE company_name = %s
                ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                (company_name, safe_limit),
            )
            rows = cur.fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        structured = _parse_json_object(row["output_json"] or "") or {}
        result.append({
            "id": int(row["id"]),
            "company_name": row["company_name"],
            "as_of_date": row["as_of_date"].isoformat(),
            "provider": row["provider"],
            "model": row["model"],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "context_window_days": int(row["context_window_days"] or 0),
            "focus_window_days": int(row["focus_window_days"] or 0),
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "bottom_line": str(structured.get("bottom_line") or ""),
            "current_price": structured.get("current_price"),
            "fair_price_zone": structured.get("fair_price_zone") if isinstance(structured.get("fair_price_zone"), dict) else {},
            "price_position": structured.get("price_position") if isinstance(structured.get("price_position"), dict) else {},
        })
    return result


def generate_company_status_snapshot(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    window_days: int = 90,
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
        return {"generated": False, "daily_report_count": 0, "weekly_report_count": 0, "elapsed_sec": 0.0, "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    end_date = as_of_date or datetime.now(timezone.utc).date()
    safe_window_days = max(7, min(int(window_days), 90))
    start_date = end_date - timedelta(days=safe_window_days - 1)
    status_input = _build_company_price_intelligence_input(company_name, start_date=start_date, end_date=end_date, provider_name=provider_name, output_language=output_language)
    price_point_count = int((status_input.get("price_context") or {}).get("point_count") or 0)
    if price_point_count <= 0:
        return {"generated": False, "price_point_count": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2), "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    prompt = _build_company_price_intelligence_prompt(company_name, as_of_date=end_date, status_input=status_input, output_language=output_language)
    with usage_context("company_status_snapshot", company_name=company_name, module="company"):
        raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    normalized_output = _normalize_company_status_payload(payload, as_of_date=end_date)
    output_text = str(normalized_output.get("output_markdown") or "").strip() or raw_output
    _upsert_company_status_snapshot(company_name=company_name, as_of_date=end_date, window_start_date=start_date, window_end_date=end_date, provider=provider_name, model=model, prompt_style="simple", input_payload={"prompt": prompt, **status_input}, output_json=normalized_output, output_text=output_text)
    return {"generated": True, "price_point_count": price_point_count, "elapsed_sec": round(pytime.perf_counter() - started_at, 2), "input_item_count": int((status_input.get("input_coverage") or {}).get("input_item_count") or 0), "prompt_char_count": len(prompt), "output_char_count": len(output_text or "")}


def generate_company_price_intelligence_run(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
    context_window_days: int = 365,
    focus_window_days: int = 60,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "elapsed_sec": 0.0, "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    end_date = as_of_date or datetime.now(timezone.utc).date()
    safe_context_days = max(180, min(int(context_window_days), 365))
    safe_focus_days = max(14, min(int(focus_window_days), 90))
    context_start = end_date - timedelta(days=safe_context_days - 1)
    focus_start = end_date - timedelta(days=safe_focus_days - 1)
    previous_run = get_company_price_intelligence_run(company_name)
    pi_input = _build_company_quick_price_intelligence_input(company_name, context_start=context_start, focus_start=focus_start, end_date=end_date, provider_name=provider_name, output_language=output_language)
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    prompt = _build_company_quick_price_intelligence_prompt(company_name=company_name, as_of_date=end_date, quick_input=pi_input, previous_run=previous_run, output_language=output_language)
    with usage_context("company_status_snapshot", company_name=company_name, module="company"):
        raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    normalized_output = _normalize_company_quick_price_intelligence_payload(payload, as_of_date=end_date, current_price=pi_input.get("latest_price"), previous_run=previous_run)
    output_text = str(normalized_output.get("output_markdown") or "").strip() or raw_output
    run_id = _insert_company_price_intelligence_run(company_name=company_name, as_of_date=end_date, provider=provider_name, model=model, output_language=output_language, context_window_days=safe_context_days, focus_window_days=safe_focus_days, input_payload={"prompt": prompt, **pi_input}, output_json=normalized_output, output_text=output_text)
    return {"generated": True, "run_id": run_id, "daily_report_count": len(pi_input.get("daily_reports") or []), "raw_news_count": len(pi_input.get("raw_news_fallback") or []), "elapsed_sec": round(pytime.perf_counter() - started_at, 2), "input_item_count": int(pi_input.get("input_coverage", {}).get("input_item_count", 0)), "prompt_char_count": len(prompt), "output_char_count": len(output_text or "")}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_company_price_intelligence_input(company_name: str, *, start_date: date, end_date: date, provider_name: str, output_language: str) -> Dict[str, Any]:
    price_context = _build_company_status_price_context(company_name, start_date=start_date, end_date=end_date)
    input_coverage = {
        "window_start": start_date.isoformat(), "window_end": end_date.isoformat(),
        "window_days": int((end_date - start_date).days) + 1,
        "price_point_count": int(price_context.get("point_count") or 0),
        "recent_point_count": len(price_context.get("recent_points") or []),
        "move_analysis_count": len(price_context.get("move_analyses") or []),
        "input_item_count": int(price_context.get("point_count") or 0),
    }
    return {"price_context": price_context, "input_coverage": input_coverage, "output_language": output_language}


def _build_company_quick_price_intelligence_input(company_name: str, *, context_start: date, focus_start: date, end_date: date, provider_name: str, output_language: str) -> Dict[str, Any]:
    all_daily_reports = get_company_daily_reports_for_range(company_name, start_date=context_start, end_date=end_date, provider_name=provider_name, prompt_style="simple")
    daily_reports = all_daily_reports[:PRICE_ANALYSIS_REPORT_LIMIT]
    daily_report_dates = {str(item.get("report_date") or "").strip() for item in daily_reports if str(item.get("report_date") or "").strip()}
    raw_news_fallback = _build_company_status_raw_news_fallback(company_name, start_date=focus_start, end_date=end_date, covered_dates=daily_report_dates)[:PRICE_ANALYSIS_RAW_FALLBACK_LIMIT]
    price_context = _build_company_status_price_context(company_name, start_date=context_start, end_date=end_date)
    focus_price_context = _build_company_status_price_context(company_name, start_date=focus_start, end_date=end_date)
    technical_focus_points = (focus_price_context.get("recent_points") or [])[-10:]
    market_stories = _build_company_status_market_story_context(limit=6)
    market_daily_summaries = _build_company_status_market_daily_summary_context(start_date=focus_start, end_date=end_date)[:PRICE_ANALYSIS_MARKET_SUMMARY_LIMIT]
    latest_price = price_context.get("latest_close")
    coverage = {
        "context_window_start": context_start.isoformat(), "focus_window_start": focus_start.isoformat(), "window_end": end_date.isoformat(),
        "daily_report_count": len(daily_reports), "raw_news_fallback_count": len(raw_news_fallback), "market_story_count": len(market_stories),
        "market_summary_count": len(market_daily_summaries), "price_point_count": int(price_context.get("point_count") or 0),
        "input_item_count": len(daily_reports) + len(raw_news_fallback) + len(market_stories) + len(market_daily_summaries) + len(technical_focus_points),
    }
    return {
        "daily_reports": daily_reports, "raw_news_fallback": raw_news_fallback,
        "price_context": price_context, "focus_price_context": focus_price_context,
        "technical_focus_points": technical_focus_points, "market_stories": market_stories,
        "market_daily_summaries": market_daily_summaries, "latest_price": latest_price,
        "input_coverage": coverage, "output_language": output_language,
    }


def _build_company_status_input_coverage(*, daily_reports: List[Dict[str, Any]], raw_news_fallback: List[Dict[str, Any]], start_date: date, end_date: date, market_daily_summaries: List[Dict[str, Any]], price_context: Dict[str, Any]) -> Dict[str, Any]:
    report_dates = {str(item.get("report_date") or "").strip() for item in daily_reports if str(item.get("report_date") or "").strip()}
    total_days = max(1, (end_date - start_date).days + 1)
    return {"window_start": start_date.isoformat(), "window_end": end_date.isoformat(), "window_days": total_days, "daily_report_count": len(daily_reports), "daily_report_coverage_days": len(report_dates), "raw_news_fallback_count": len(raw_news_fallback), "market_summary_count": len(market_daily_summaries), "price_point_count": int(price_context.get("point_count") or 0)}


def _build_company_status_raw_news_fallback(company_name: str, *, start_date: date, end_date: date, covered_dates: set[str]) -> List[Dict[str, Any]]:
    fallback: List[Dict[str, Any]] = []
    for article in get_company_news_for_range(company_name, start_date=start_date, end_date=end_date)[:80]:
        article_date = article.news_date_time.date().isoformat()
        if article_date in covered_dates:
            continue
        fallback.append({"news_date_time": article.news_date_time.isoformat(), "news_title": article.news_title, "news_source": article.news_source, "news_source_link": article.news_source_link, "summary": _decode_llm_content(article.llm_analyzed_content, article.original_content).get("summary")})
    return fallback


def _build_company_status_price_context(company_name: str, *, start_date: date, end_date: date) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker, trade_date, open, high, low, close, adj_close, volume FROM company_price_daily WHERE company_name = %s AND trade_date >= %s AND trade_date <= %s ORDER BY trade_date ASC", (company_name, start_date, end_date))
            rows = cur.fetchall()
    if not rows:
        return {}
    closes = [float(row["close"] if row["close"] is not None else row["adj_close"]) for row in rows if row["close"] is not None or row["adj_close"] is not None]
    if not closes:
        return {}
    latest_close = closes[-1]
    first_close = closes[0]
    highs = [float(row["high"]) for row in rows if row["high"] is not None]
    lows = [float(row["low"]) for row in rows if row["low"] is not None]
    volumes = [int(row["volume"]) for row in rows if row["volume"] is not None]

    def _pct_change(points_back: int) -> Optional[float]:
        if len(closes) <= points_back:
            return None
        base = closes[-(points_back + 1)]
        if base in (None, 0):
            return None
        return round(((latest_close - base) / base) * 100.0, 2)

    returns = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        curr = closes[idx]
        if prev:
            returns.append((curr - prev) / prev)
    volatility = round((math.sqrt(sum(r * r for r in returns) / len(returns)) * 100.0), 2) if returns else None
    window_high = max(highs) if highs else max(closes)
    window_low = min(lows) if lows else min(closes)
    recent_20 = closes[-20:]
    recent_50 = closes[-50:]
    recent_200 = closes[-200:]
    avg_volume_20 = round(sum(volumes[-20:]) / len(volumes[-20:])) if volumes[-20:] else None
    move_analyses = _build_company_status_price_move_context(company_name, ticker=str(rows[-1]["ticker"] or "").strip().upper())
    return {
        "ticker": str(rows[-1]["ticker"] or "").strip().upper(),
        "point_count": len(rows), "window_start": rows[0]["trade_date"].isoformat(), "window_end": rows[-1]["trade_date"].isoformat(),
        "latest_close": round(latest_close, 4),
        "window_high": round(window_high, 4) if window_high is not None else None,
        "window_low": round(window_low, 4) if window_low is not None else None,
        "window_change_pct": round(((latest_close - first_close) / first_close) * 100.0, 2) if first_close else None,
        "return_5d_pct": _pct_change(5), "return_20d_pct": _pct_change(20), "return_60d_pct": _pct_change(60),
        "distance_to_window_high_pct": round(((latest_close - window_high) / window_high) * 100.0, 2) if window_high else None,
        "distance_to_window_low_pct": round(((latest_close - window_low) / window_low) * 100.0, 2) if window_low else None,
        "ma_20": round(sum(recent_20) / len(recent_20), 4) if recent_20 else None,
        "ma_50": round(sum(recent_50) / len(recent_50), 4) if recent_50 else None,
        "ma_200": round(sum(recent_200) / len(recent_200), 4) if recent_200 else None,
        "realized_volatility_pct": volatility,
        "latest_volume": volumes[-1] if volumes else None, "avg_volume_20": avg_volume_20,
        "recent_points": [{"trade_date": row["trade_date"].isoformat(), "close": float(row["close"] if row["close"] is not None else row["adj_close"]) if row["close"] is not None or row["adj_close"] is not None else None, "high": float(row["high"]) if row["high"] is not None else None, "low": float(row["low"]) if row["low"] is not None else None, "volume": int(row["volume"]) if row["volume"] is not None else None} for row in rows[-10:]],
        "move_analyses": move_analyses,
    }


def _build_company_status_price_move_context(company_name: str, *, ticker: str) -> List[Dict[str, Any]]:
    if not ticker:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {COL_RANGE_KEY}, {COL_POINT_DATE_TIME}, output_text, updated_at FROM {TBL_COMPANY_PRICE_MOVE_ANALYSIS} WHERE company_name = %s AND ticker = %s ORDER BY updated_at DESC, id DESC LIMIT 6", (company_name, ticker))
            rows = cur.fetchall()
    return [{"range_key": row[COL_RANGE_KEY], "point_date_time": row[COL_POINT_DATE_TIME].isoformat() if row[COL_POINT_DATE_TIME] else None, "output_text": row["output_text"] or "", "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None} for row in rows]


def _build_company_status_market_story_context(*, limit: int = 6) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT story_title, story_summary, priority, importance_rank, updated_at FROM market_story_state WHERE is_active = TRUE ORDER BY importance_rank ASC, updated_at DESC LIMIT %s", (max(1, int(limit)),))
            rows = cur.fetchall()
    return [{"story_title": row["story_title"], "story_summary": row["story_summary"] or "", "priority": row["priority"] or "normal", "importance_rank": int(row["importance_rank"] or 999), "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None} for row in rows]


def _build_company_status_market_daily_summary_context(*, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT summary_date, output_text, provider, model, prompt_style, created_at FROM market_news_daily_summary WHERE summary_date >= %s AND summary_date <= %s ORDER BY summary_date DESC, created_at DESC LIMIT 10", (start_date, end_date))
            rows = cur.fetchall()
    return [{"summary_date": row["summary_date"].isoformat(), "output_text": row["output_text"] or "", "provider": row["provider"], "model": row["model"], "prompt_style": row["prompt_style"], "created_at": row["created_at"].isoformat() if row["created_at"] else None} for row in rows]


def _build_company_status_macro_context(*, as_of_date: date) -> Dict[str, Any]:
    recent_events: List[Dict[str, Any]] = []
    upcoming_events: List[Dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_name, event_date_time, category, importance, impact_summary, country, event_code FROM market_macro_event WHERE event_date_time >= %s AND event_date_time < %s ORDER BY event_date_time ASC LIMIT 12",
                (datetime.combine(as_of_date - timedelta(days=7), time.min, tzinfo=timezone.utc), datetime.combine(as_of_date + timedelta(days=14), time.min, tzinfo=timezone.utc)),
            )
            rows = cur.fetchall()
    for row in rows:
        entry = {"event_name": row["event_name"], "event_date_time": row["event_date_time"].isoformat() if row["event_date_time"] else None, "category": row["category"] or "", "importance": row["importance"] or "", "impact_summary": row["impact_summary"] or "", "country": row["country"] or "", "event_code": row["event_code"] or ""}
        if row["event_date_time"] and row["event_date_time"].date() < as_of_date:
            recent_events.append(entry)
        else:
            upcoming_events.append(entry)
    market_snapshot = _build_company_status_market_snapshot_context(as_of_date=as_of_date)
    return {"recent_macro_events": recent_events[:6], "upcoming_macro_events": upcoming_events[:6], "market_price_snapshot": market_snapshot}


def _build_company_status_market_snapshot_context(*, as_of_date: date) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {COL_PAYLOAD} FROM {TBL_MARKET_PRICE_DAILY_SNAPSHOT} WHERE {COL_SNAPSHOT_DATE} <= %s ORDER BY {COL_SNAPSHOT_DATE} DESC LIMIT 1", (as_of_date,))
            row = cur.fetchone()
    if not row or not isinstance(row[COL_PAYLOAD], str):
        return {}
    try:
        payload = json.loads(row[COL_PAYLOAD])
    except json.JSONDecodeError:
        return {}
    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, list):
        return {}
    return {"snapshot_date": payload.get("date"), "price_date": payload.get("price_date"), "sections": sections[:6]}


def _normalize_company_quick_price_intelligence_payload(payload: Dict[str, Any], *, as_of_date: date, current_price: Any, previous_run: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    def _to_text(value: Any) -> str:
        return str(value or "").strip()

    def _to_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = _to_text(value)
        return [text] if text else []

    def _to_number(value: Any, fallback: Optional[float] = None) -> Optional[float]:
        try:
            if value is None or value == "":
                return fallback
            return round(float(value), 4)
        except Exception:
            return fallback

    def _normalize_zone(value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        low = _to_number(data.get("low"), _to_number(current_price))
        mid = _to_number(data.get("mid"), low)
        high = _to_number(data.get("high"), mid)
        return {"low": low, "mid": mid, "high": high, "basis": _to_text(data.get("basis"))}

    def _normalize_method(value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        return {"summary": _to_text(data.get("summary")), "fair_price_read": _to_text(data.get("fair_price_read")), "signals": _to_list(data.get("signals")), "risks": _to_list(data.get("risks"))}

    normalized = {
        "as_of_date": as_of_date.isoformat(),
        "current_price": _to_number(payload.get("current_price"), _to_number(current_price)),
        "fair_price_zone": _normalize_zone(payload.get("fair_price_zone")),
        "price_position": payload.get("price_position") if isinstance(payload.get("price_position"), dict) else {"label": "near_fair", "explanation": ""},
        "bottom_line": _to_text(payload.get("bottom_line")),
        "technical_view": _normalize_method(payload.get("technical_view")),
        "fundamental_market_view": _normalize_method(payload.get("fundamental_market_view")),
        "synthesis_view": {
            "summary": _to_text((payload.get("synthesis_view") or {}).get("summary") if isinstance(payload.get("synthesis_view"), dict) else ""),
            "dominant_method": _to_text((payload.get("synthesis_view") or {}).get("dominant_method") if isinstance(payload.get("synthesis_view"), dict) else ""),
            "triggers": _to_list((payload.get("synthesis_view") or {}).get("triggers") if isinstance(payload.get("synthesis_view"), dict) else []),
            "invalidations": _to_list((payload.get("synthesis_view") or {}).get("invalidations") if isinstance(payload.get("synthesis_view"), dict) else []),
        },
    }
    normalized["output_markdown"] = _render_company_quick_price_intelligence_markdown(normalized)
    return normalized


def _render_company_quick_price_intelligence_markdown(payload: Dict[str, Any]) -> str:
    def _bullet(items: List[str]) -> str:
        rows = [f"- {item}" for item in items if str(item).strip()]
        return "\n".join(rows) if rows else "- —"
    zone = payload.get("fair_price_zone") or {}
    position = payload.get("price_position") or {}
    synthesis = payload.get("synthesis_view") or {}
    return (
        "## Price Intelligence\n"
        f"- Current Price: {payload.get('current_price') or '—'}\n"
        f"- Fair Price Zone: {zone.get('low') or '—'} / {zone.get('mid') or '—'} / {zone.get('high') or '—'}\n"
        f"- Price Position: {position.get('label') or '—'} · {position.get('explanation') or '—'}\n"
        f"- Bottom Line: {payload.get('bottom_line') or '—'}\n"
        "\n### Technical View\n"
        f"- Summary: {(payload.get('technical_view') or {}).get('summary') or '—'}\n"
        f"- Fair Price Read: {(payload.get('technical_view') or {}).get('fair_price_read') or '—'}\n"
        f"- Signals:\n{_bullet((payload.get('technical_view') or {}).get('signals') or [])}\n"
        f"- Risks:\n{_bullet((payload.get('technical_view') or {}).get('risks') or [])}\n"
        "\n### Fundamental / Market View\n"
        f"- Summary: {(payload.get('fundamental_market_view') or {}).get('summary') or '—'}\n"
        f"- Fair Price Read: {(payload.get('fundamental_market_view') or {}).get('fair_price_read') or '—'}\n"
        f"- Signals:\n{_bullet((payload.get('fundamental_market_view') or {}).get('signals') or [])}\n"
        f"- Risks:\n{_bullet((payload.get('fundamental_market_view') or {}).get('risks') or [])}\n"
        "\n### Synthesis\n"
        f"- Summary: {synthesis.get('summary') or '—'}\n"
        f"- Dominant Method: {synthesis.get('dominant_method') or '—'}\n"
        f"- Triggers:\n{_bullet(synthesis.get('triggers') or [])}\n"
        f"- Invalidations:\n{_bullet(synthesis.get('invalidations') or [])}\n"
    )


def _normalize_company_status_payload(payload: Dict[str, Any], *, as_of_date: date) -> Dict[str, Any]:
    def _to_text(value: Any) -> str:
        return str(value or "").strip()
    def _to_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []
    def _normalize_horizon(name: str, value: Any) -> Dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        confidence = data.get("confidence")
        try:
            confidence_value = max(0.0, min(float(confidence), 1.0))
        except Exception:
            confidence_value = 0.5
        return {"horizon": name, "confidence": round(confidence_value, 2), "price_judgment": _to_text(data.get("price_judgment")), "rationale": _to_list(data.get("rationale")), "watch_signals": _to_list(data.get("watch_signals")), "invalidations": _to_list(data.get("invalidations"))}
    normalized = {
        "as_of_date": as_of_date.isoformat(),
        "company_summary": _to_text(payload.get("company_summary") or payload.get("technical_summary")),
        "technical_summary": _to_text(payload.get("technical_summary")),
        "dominant_personality": payload.get("dominant_personality") if isinstance(payload.get("dominant_personality"), dict) else {"label": "", "dominant_horizon": "balanced", "why": ""},
        "price_position_summary": _to_text(payload.get("price_position_summary")),
        "market_regime_context": _to_text(payload.get("market_regime_context")),
        "decision_brief": payload.get("decision_brief") if isinstance(payload.get("decision_brief"), dict) else {},
        "research_memo": payload.get("research_memo") if isinstance(payload.get("research_memo"), dict) else {},
        "trader_view": payload.get("trader_view") if isinstance(payload.get("trader_view"), dict) else {},
        "volume_participation": _to_text(payload.get("volume_participation")),
        "volatility_range_context": _to_text(payload.get("volatility_range_context")),
        "short_horizon_view": _normalize_horizon("short", payload.get("short_horizon_view")),
        "medium_horizon_view": _normalize_horizon("medium", payload.get("medium_horizon_view")),
        "long_horizon_view": _normalize_horizon("long", payload.get("long_horizon_view")),
        "signals_to_watch": _to_list(payload.get("signals_to_watch")),
        "risk_map": _to_list(payload.get("risk_map")),
        "uncertainty_map": _to_list(payload.get("uncertainty_map")),
        "trading_style_fit": _to_list(payload.get("trading_style_fit")),
        "supporting_reasoning": _to_list(payload.get("supporting_reasoning")),
    }
    markdown = _to_text(payload.get("output_markdown"))
    if not markdown:
        markdown = _render_company_status_markdown(normalized)
    normalized["output_markdown"] = markdown
    return normalized


def _render_company_status_markdown(payload: Dict[str, Any]) -> str:
    def _bullet_block(items: List[str]) -> str:
        rows = [f"- {item}" for item in items if str(item).strip()]
        return "\n".join(rows) if rows else "- —"
    def _render_horizon(section: Dict[str, Any]) -> str:
        return (f"- Confidence: {section.get('confidence', 0.5)}\n" f"- Price Judgment: {section.get('price_judgment') or '—'}\n" f"- Rationale:\n{_bullet_block(section.get('rationale') or [])}\n" f"- Watch Signals:\n{_bullet_block(section.get('watch_signals') or [])}\n" f"- Invalidations:\n{_bullet_block(section.get('invalidations') or [])}")
    personality = payload.get("dominant_personality") if isinstance(payload.get("dominant_personality"), dict) else {}
    return (
        "## Technical Summary\n"
        f"- Summary: {payload.get('technical_summary') or payload.get('company_summary') or '—'}\n"
        f"- Price Position: {payload.get('price_position_summary') or '—'}\n"
        f"- Dominant Personality: {personality.get('label') or '—'}\n"
        f"- Dominant Horizon: {personality.get('dominant_horizon') or 'balanced'}\n"
        f"- Why Dominant: {personality.get('why') or '—'}\n"
        "\n## Volume And Participation\n" f"- {payload.get('volume_participation') or '—'}\n"
        "\n## Volatility And Range\n" f"- {payload.get('volatility_range_context') or '—'}\n"
        "\n### Short Horizon\n" f"{_render_horizon(payload.get('short_horizon_view') or {})}\n"
        "\n### Medium Horizon\n" f"{_render_horizon(payload.get('medium_horizon_view') or {})}\n"
        "\n### Long Horizon\n" f"{_render_horizon(payload.get('long_horizon_view') or {})}\n"
        f"\n## Risk Map\n{_bullet_block(payload.get('risk_map') or [])}\n"
        f"\n## Uncertainty Map\n{_bullet_block(payload.get('uncertainty_map') or [])}\n"
    )


def _upsert_company_status_snapshot(*, company_name: str, as_of_date: date, window_start_date: date, window_end_date: date, provider: str, model: str, prompt_style: str, input_payload: Dict[str, Any], output_json: Dict[str, Any], output_text: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO company_status_snapshot (company_name, as_of_date, window_start_date, window_end_date, provider, model, prompt_style, input_payload, output_json, output_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (company_name, as_of_date, window_start_date, window_end_date, provider, model, prompt_style, json.dumps(input_payload), json.dumps(output_json, ensure_ascii=False), output_text),
            )
        conn.commit()


def _insert_company_price_intelligence_run(*, company_name: str, as_of_date: date, provider: str, model: str, output_language: str, context_window_days: int, focus_window_days: int, input_payload: Dict[str, Any], output_json: Dict[str, Any], output_text: str) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {TBL_COMPANY_PRICE_INTELLIGENCE_RUN} (company_name, as_of_date, provider, model, {COL_OUTPUT_LANGUAGE}, context_window_days, focus_window_days, input_payload, output_json, output_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (company_name, as_of_date, provider, model, output_language, int(context_window_days), int(focus_window_days), json.dumps(input_payload, ensure_ascii=False), json.dumps(output_json, ensure_ascii=False), output_text),
            )
            row = cur.fetchone()
        conn.commit()
    return int(row["id"])
