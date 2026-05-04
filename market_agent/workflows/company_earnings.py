"""Shared company earnings timeline helpers."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from market_agent.services.company import ensure_company_profile, get_company_profile
from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.config.models import DEFAULT_OPENAI_MODEL
from market_agent.datasources.finnhub.finnhub_client import FinnhubClient
from market_agent.llms.usage_context import usage_context
from market_agent.llms.news_registry import get_news_provider
from market_agent.schema_fields import (
    COL_EARNINGS_DATE,
    COL_MODEL,
    COL_OUTPUT_LANGUAGE,
    COL_PROVIDER,
    COL_TICKER,
    TBL_COMPANY_EARNINGS_EVENT,
)


def refresh_company_earnings(
    company_name: str,
    *,
    provider_name: str = "openai",
    model: str = DEFAULT_OPENAI_MODEL,
    output_language: str = "zh-CN",
    limit: int = 4,
) -> Dict[str, Any]:
    ensure_database_schema()
    ensure_company_profile(company_name)
    profile = get_company_profile(company_name)
    ticker = str((profile or {}).get("ticker") or "").strip().upper()
    if not ticker:
        return {"updated": 0, "events": []}
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return {"updated": 0, "events": []}
    client = FinnhubClient(api_key)
    raw = client.earnings(symbol=ticker).get("data") or []
    if not isinstance(raw, list):
        raw = []
    events: List[Dict[str, Any]] = []
    for row in raw[: max(4, int(limit))]:
        if not isinstance(row, dict):
            continue
        earnings_date = _parse_earnings_date(row)
        if not earnings_date:
            continue
        price_reaction = _compute_earnings_price_reaction(company_name, ticker, earnings_date)
        prompt_payload = {
            "company_name": company_name,
            "ticker": ticker,
            "earnings_date": earnings_date.isoformat(),
            "earnings_payload": row,
            "price_reaction": price_reaction,
        }
        provider = get_news_provider(provider_name, model=model, timeout_sec=120)
        with usage_context("company_earnings_legacy", company_name=company_name, module="earnings"):
            analysis_text = provider.generate_text(prompt=_build_company_earnings_prompt(prompt_payload, output_language))
        event = {
            "company_name": company_name,
            "ticker": ticker,
            "earnings_date": earnings_date,
            "fiscal_period": str(row.get("period") or row.get("quarter") or "").strip() or None,
            "estimate_eps": _as_float(row.get("estimate")),
            "actual_eps": _as_float(row.get("actual")),
            "surprise_percent": _as_float(row.get("surprisePercent")),
            "estimate_revenue": _as_float(row.get("revenueEstimate") or row.get("revenue_estimate")),
            "actual_revenue": _as_float(row.get("revenueActual") or row.get("revenue_actual")),
            "guidance_summary": None,
            "price_reaction_json": price_reaction,
            "source_payload": row,
            "analysis_text": analysis_text,
            "provider": provider_name,
            "model": model,
            "output_language": output_language,
        }
        _upsert_company_earnings_event(event)
        events.append(_row_from_event(event))
    return {"updated": len(events), "events": list_company_earnings(company_name, limit=limit)}


def list_company_earnings(company_name: str, *, limit: int = 4) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_COMPANY_EARNINGS_EVENT}
                WHERE company_name = %s
                ORDER BY {COL_EARNINGS_DATE} DESC, updated_at DESC
                LIMIT %s
                """,
                (company_name, max(1, int(limit))),
            )
            rows = cur.fetchall()
    return [_row_to_company_earnings(row) for row in rows]


def _build_company_earnings_prompt(payload: Dict[str, Any], output_language: str) -> str:
    language_line = "- Output should be written in Simplified Chinese.\n" if str(output_language or "").lower() != "en" else ""
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "Summarize this earnings event for an investor.\n"
        "Explain what was reported, what stood out versus expectation, and how the stock reacted afterward.\n"
        "If guidance is missing, say that clearly.\n"
        "Use short sections and bullet points.\n"
        f"{language_line}"
        f"Context JSON:\n{payload_json}\n"
    )


def _compute_earnings_price_reaction(company_name: str, ticker: str, earnings_date: date) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, close_price
                FROM company_price_daily
                WHERE company_name = %s
                  AND ticker = %s
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY trade_date ASC
                """,
                (company_name, ticker, earnings_date - timedelta(days=2), earnings_date + timedelta(days=5)),
            )
            rows = cur.fetchall()
    if not rows:
        return {}
    points = [{"date": row["trade_date"].isoformat(), "close_price": float(row["close_price"])} for row in rows]
    baseline = points[0]["close_price"]
    latest = points[-1]["close_price"]
    pct_change = 0.0 if baseline == 0 else ((latest - baseline) / baseline) * 100.0
    return {
        "points": points,
        "window_change_pct": round(pct_change, 2),
    }


def _upsert_company_earnings_event(item: Dict[str, Any]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_EARNINGS_EVENT}
                    (company_name, ticker, earnings_date, fiscal_period, estimate_eps, actual_eps,
                     surprise_percent, estimate_revenue, actual_revenue, guidance_summary,
                     price_reaction_json, source_payload, analysis_text, provider, model, {COL_OUTPUT_LANGUAGE}, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, NOW())
                ON CONFLICT (company_name, ticker, earnings_date)
                DO UPDATE SET
                    fiscal_period = EXCLUDED.fiscal_period,
                    estimate_eps = EXCLUDED.estimate_eps,
                    actual_eps = EXCLUDED.actual_eps,
                    surprise_percent = EXCLUDED.surprise_percent,
                    estimate_revenue = EXCLUDED.estimate_revenue,
                    actual_revenue = EXCLUDED.actual_revenue,
                    guidance_summary = EXCLUDED.guidance_summary,
                    price_reaction_json = EXCLUDED.price_reaction_json,
                    source_payload = EXCLUDED.source_payload,
                    analysis_text = EXCLUDED.analysis_text,
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    output_language = EXCLUDED.output_language,
                    updated_at = NOW()
                """,
                (
                    item["company_name"],
                    item["ticker"],
                    item["earnings_date"],
                    item["fiscal_period"],
                    item["estimate_eps"],
                    item["actual_eps"],
                    item["surprise_percent"],
                    item["estimate_revenue"],
                    item["actual_revenue"],
                    item["guidance_summary"],
                    json.dumps(item["price_reaction_json"], ensure_ascii=False),
                    json.dumps(item["source_payload"], ensure_ascii=False),
                    item["analysis_text"],
                    item["provider"],
                    item["model"],
                    item["output_language"],
                ),
            )
        conn.commit()


def _row_to_company_earnings(row: Dict[str, Any]) -> Dict[str, Any]:
    def _json_obj(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}
    return {
        "company_name": row["company_name"],
        "ticker": row[COL_TICKER],
        "earnings_date": row[COL_EARNINGS_DATE].isoformat(),
        "fiscal_period": row["fiscal_period"],
        "estimate_eps": row["estimate_eps"],
        "actual_eps": row["actual_eps"],
        "surprise_percent": row["surprise_percent"],
        "estimate_revenue": row["estimate_revenue"],
        "actual_revenue": row["actual_revenue"],
        "guidance_summary": row["guidance_summary"],
        "price_reaction": _json_obj(row["price_reaction_json"]),
        "analysis_text": row["analysis_text"],
        "provider": row[COL_PROVIDER],
        "model": row[COL_MODEL],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _row_from_event(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "company_name": item["company_name"],
        "ticker": item["ticker"],
        "earnings_date": item["earnings_date"].isoformat(),
        "analysis_text": item["analysis_text"],
    }


def _parse_earnings_date(row: Dict[str, Any]) -> Optional[date]:
    for key in ("date", "period"):
        value = row.get(key)
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value)).date()
        except ValueError:
            continue
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
