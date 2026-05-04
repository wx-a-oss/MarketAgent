"""LLM usage logging and query functions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from market_agent.config.pricing import calculate_cost
from market_agent.db.bootstrap import ensure_database_schema, get_connection

log = logging.getLogger(__name__)

TBL = "llm_usage_log"


def log_llm_usage(
    *,
    provider: str,
    model: str,
    purpose: str = "unknown",
    company_name: Optional[str] = None,
    module: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    input_char_count: Optional[int] = None,
    output_char_count: Optional[int] = None,
    response_time_ms: Optional[int] = None,
    used_web_search: bool = False,
    cache_hit: Optional[bool] = None,
    cached_tokens: Optional[int] = None,
    request_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        ensure_database_schema()
        if cost_usd is None and prompt_tokens is not None:
            cost_usd = calculate_cost(model, prompt_tokens, completion_tokens, cached_tokens)
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TBL}
                        (provider, model, purpose, company_name, module,
                         prompt_tokens, completion_tokens, total_tokens, cost_usd,
                         input_char_count, output_char_count, response_time_ms,
                         used_web_search, cache_hit, cached_tokens, request_metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        provider, model, purpose, company_name, module,
                        prompt_tokens, completion_tokens, total_tokens, cost_usd,
                        input_char_count, output_char_count, response_time_ms,
                        used_web_search, cache_hit, cached_tokens,
                        json.dumps(request_metadata or {}),
                    ),
                )
            conn.commit()
    except Exception:
        log.exception("Failed to log LLM usage")


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, days))


def _date_range(target_date: str) -> tuple[datetime, datetime]:
    from datetime import date as _date
    d = _date.fromisoformat(target_date)
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _where_clause(days: int, target_date: Optional[str] = None) -> tuple[str, list]:
    if target_date:
        start, end = _date_range(target_date)
        return "created_at >= %s AND created_at < %s", [start, end]
    return "created_at >= %s", [_cutoff(days)]


def get_usage_summary(days: int = 7, target_date: Optional[str] = None) -> Dict[str, Any]:
    ensure_database_schema()
    where, params = _where_clause(days, target_date)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_requests,
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cached_tokens), 0) AS total_cached_tokens
                FROM {TBL} WHERE {where}
                """,
                params,
            )
            row = cur.fetchone()
            summary = dict(row) if row else {}

            cur.execute(
                f"""
                SELECT provider, model,
                    COUNT(*) AS requests,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(total_tokens), 0) AS tokens
                FROM {TBL} WHERE {where}
                GROUP BY provider, model ORDER BY cost DESC
                """,
                params,
            )
            summary["by_model"] = [dict(r) for r in cur.fetchall()]

    summary["days"] = days
    summary["target_date"] = target_date
    return summary


def get_usage_by_company(days: int = 7, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_database_schema()
    where, params = _where_clause(days, target_date)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT company_name,
                    COUNT(*) AS requests,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(total_tokens), 0) AS tokens
                FROM {TBL} WHERE {where} AND company_name IS NOT NULL
                GROUP BY company_name ORDER BY cost DESC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]


def get_usage_by_module(days: int = 7, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_database_schema()
    where, params = _where_clause(days, target_date)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT module,
                    COUNT(*) AS requests,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(total_tokens), 0) AS tokens
                FROM {TBL} WHERE {where}
                GROUP BY module ORDER BY cost DESC
                """,
                params,
                (cutoff,),
            )
            return [dict(r) for r in cur.fetchall()]


def list_usage_requests(
    days: int = 7, *, limit: int = 100, offset: int = 0,
    company: Optional[str] = None, module: Optional[str] = None,
    target_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    ensure_database_schema()
    where, params = _where_clause(days, target_date)
    clauses = [where]
    if company:
        clauses.append("company_name = %s")
        params.append(company)
    if module:
        clauses.append("module = %s")
        params.append(module)
    where = " AND ".join(clauses)
    params.extend([max(1, min(500, limit)), max(0, offset)])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, provider, model, purpose, company_name, module,
                       prompt_tokens, completion_tokens, total_tokens, cost_usd,
                       input_char_count, output_char_count, response_time_ms,
                       used_web_search, cache_hit, cached_tokens, created_at
                FROM {TBL} WHERE {where}
                ORDER BY created_at DESC LIMIT %s OFFSET %s
                """,
                params,
            )
            return [
                {**dict(r), "created_at": r["created_at"].isoformat() if r["created_at"] else None}
                for r in cur.fetchall()
            ]


def get_daily_costs(days: int = 90) -> List[Dict[str, Any]]:
    ensure_database_schema()
    cutoff = _cutoff(days)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE(created_at) AS day,
                    COUNT(*) AS requests,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(total_tokens), 0) AS tokens
                FROM {TBL} WHERE created_at >= %s
                GROUP BY DATE(created_at) ORDER BY day DESC
                """,
                (cutoff,),
            )
            return [
                {"day": r["day"].isoformat(), "requests": r["requests"], "cost": float(r["cost"]), "tokens": r["tokens"]}
                for r in cur.fetchall()
            ]
