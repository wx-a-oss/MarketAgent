"""Watchlist and chart-layout functions."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from market_agent.config.models import DEFAULT_COMPANY_OPENAI_MODEL
from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.services.company._helpers import (
    _normalize_company_name,
    _normalize_ticker,
)

logger = logging.getLogger("uvicorn.error")


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
                    COALESCE(NULLIF(TRIM(w.llm_model), ''), %s) AS llm_model,
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
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL,),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "company_name": row["company_name"],
                        "llm_model": str(row.get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL),
                        "ticker": _normalize_ticker(row.get("ticker")),
                    }
                )
            return rows


def list_company_chart_layout_rows() -> List[Dict[str, Optional[str]]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    w.company_name,
                    COALESCE(NULLIF(TRIM(w.llm_model), ''), %s) AS llm_model,
                    p.ticker,
                    l.position_index
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
                LEFT JOIN company_chart_layout AS l
                    ON l.company_name = w.company_name
                ORDER BY
                    CASE WHEN l.position_index IS NULL THEN 1 ELSE 0 END,
                    l.position_index ASC,
                    w.added_at DESC
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL,),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "company_name": row["company_name"],
                        "llm_model": str(row.get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL),
                        "ticker": _normalize_ticker(row.get("ticker")),
                        "position_index": int(row["position_index"]) if row.get("position_index") is not None else None,
                    }
                )
            return rows


def save_company_chart_layout(company_names: Iterable[str]) -> List[str]:
    ensure_database_schema()
    normalized_names: List[str] = []
    seen: set[str] = set()
    for item in company_names:
        normalized = _normalize_company_name(item)
        if not normalized:
            continue
        if normalized in seen:
            raise ValueError(f"duplicate company_name in layout: {normalized}")
        seen.add(normalized)
        normalized_names.append(normalized)

    current_rows = list_watchlist_company_rows()
    current_names = [
        str(row.get("company_name") or "").strip()
        for row in current_rows
        if str(row.get("company_name") or "").strip()
    ]
    if set(normalized_names) != set(current_names) or len(normalized_names) != len(current_names):
        raise ValueError("layout must contain every subscribed company exactly once")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_chart_layout")
            if normalized_names:
                cur.executemany(
                    """
                    INSERT INTO company_chart_layout (company_name, position_index, updated_at)
                    VALUES (%s, %s, NOW())
                    """,
                    [(company_name, idx) for idx, company_name in enumerate(normalized_names)],
                )
        conn.commit()
    return normalized_names


def get_company_watchlist_model(company_name: str) -> str:
    normalized = _normalize_company_name(company_name)
    if not normalized:
        return DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(llm_model), ''), %s) AS llm_model
                FROM company_watchlist
                WHERE company_name = %s
                """,
                (DEFAULT_COMPANY_OPENAI_MODEL, normalized),
            )
            row = cur.fetchone()
    return str((row or {}).get("llm_model") or DEFAULT_COMPANY_OPENAI_MODEL)


def update_company_watchlist_model(company_name: str, model: Optional[str]) -> Dict[str, str]:
    from market_agent.services.company.profiles import ensure_company_profile

    normalized = _normalize_company_name(company_name)
    if not normalized:
        raise ValueError("company_name is required")
    selected_model = str(model or "").strip() or DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_watchlist (company_name, llm_model)
                VALUES (%s, %s)
                ON CONFLICT (company_name)
                DO UPDATE SET llm_model = EXCLUDED.llm_model
                RETURNING company_name, llm_model
                """,
                (normalized, selected_model),
            )
            row = cur.fetchone()
        conn.commit()
    ensure_company_profile(normalized)
    return {
        "company_name": str(row["company_name"]),
        "llm_model": str(row["llm_model"] or DEFAULT_COMPANY_OPENAI_MODEL),
    }


def add_company_to_watchlist(company_name: str, *, model: Optional[str] = None) -> None:
    from market_agent.services.company.profiles import ensure_company_profile

    normalized = _normalize_company_name(company_name)
    if not normalized:
        return
    selected_model = str(model or "").strip() or DEFAULT_COMPANY_OPENAI_MODEL
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_watchlist (company_name, llm_model)
                VALUES (%s, %s)
                ON CONFLICT (company_name)
                DO UPDATE SET llm_model = EXCLUDED.llm_model
                """,
                (normalized, selected_model),
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
