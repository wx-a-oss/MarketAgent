"""Comprehensive earnings report extraction via LLM web search."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.config.models import DEFAULT_OPENAI_MODEL
from market_agent.llms.news_registry import get_news_provider
from market_agent.llms.prompts.earnings_analysis import (
    build_earnings_report_prompt,
    build_latest_earnings_prompt,
    build_refresh_earnings_prompt,
)
from market_agent.llms.usage_context import usage_context
from market_agent.schema_fields import TBL_COMPANY_EARNINGS_REPORT

log = logging.getLogger(__name__)


def fetch_earnings_report(
    company_name: str,
    *,
    fiscal_year: str,
    fiscal_quarter: str,
    provider_name: str = "openai",
    model: str = DEFAULT_OPENAI_MODEL,
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    ensure_database_schema()
    ticker = _resolve_ticker(company_name)
    prompt = build_earnings_report_prompt(
        company_name, ticker, fiscal_year, fiscal_quarter, output_language,
    )
    return _fetch_and_store(
        company_name, ticker, prompt,
        provider_name=provider_name, model=model, output_language=output_language,
    )


def fetch_latest_earnings_report(
    company_name: str,
    *,
    provider_name: str = "openai",
    model: str = DEFAULT_OPENAI_MODEL,
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    ensure_database_schema()
    ticker = _resolve_ticker(company_name)
    prompt = build_latest_earnings_prompt(company_name, ticker, output_language)
    return _fetch_and_store(
        company_name, ticker, prompt,
        provider_name=provider_name, model=model, output_language=output_language,
    )


def refresh_earnings_report(
    company_name: str,
    *,
    fiscal_year: str,
    fiscal_quarter: str,
    provider_name: str = "openai",
    model: str = DEFAULT_OPENAI_MODEL,
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    ensure_database_schema()
    existing = get_earnings_report(company_name, fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter)
    if not existing:
        return fetch_earnings_report(
            company_name,
            fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter,
            provider_name=provider_name, model=model, output_language=output_language,
        )
    ticker = existing.get("ticker") or _resolve_ticker(company_name)
    existing_for_prompt = {
        "quarter_info": {
            "fiscal_year": existing["fiscal_year"],
            "fiscal_quarter": existing["fiscal_quarter"],
            "quarter_end_date": existing.get("quarter_end_date"),
            "earnings_date": existing.get("earnings_date"),
        },
        "financials": existing.get("financials") or {},
        "company_specific": existing.get("company_specific") or [],
        "estimates_vs_actuals": existing.get("estimates") or {},
        "guidance": (existing.get("analysis") or {}).get("guidance") or {},
        "management_commentary": (existing.get("analysis") or {}).get("management_commentary") or {},
        "analysis": (existing.get("analysis") or {}).get("analysis") or {},
        "keywords": (existing.get("analysis") or {}).get("keywords") or [],
    }
    prompt = build_refresh_earnings_prompt(
        company_name, ticker, fiscal_year, fiscal_quarter,
        json.dumps(existing_for_prompt, ensure_ascii=False, indent=2),
        output_language,
    )
    return _fetch_and_store_merged(
        company_name, ticker, prompt, existing,
        provider_name=provider_name, model=model, output_language=output_language,
    )


def _fetch_and_store_merged(
    company_name: str,
    ticker: str,
    prompt: str,
    existing: Dict[str, Any],
    *,
    provider_name: str,
    model: str,
    output_language: str,
) -> Dict[str, Any]:
    provider = get_news_provider(
        provider_name, model=model, timeout_sec=180, use_web_search=True,
    )
    with usage_context("earnings_report_refresh", company_name=company_name, module="earnings"):
        raw_response = provider.generate_text(prompt=prompt)
    parsed = _parse_json_response(raw_response)
    if not parsed:
        log.warning("Failed to parse refresh LLM response for %s", company_name)
        return existing

    quarter_info = parsed.get("quarter_info") or {}
    fiscal_year = str(quarter_info.get("fiscal_year") or existing["fiscal_year"]).strip()
    fiscal_quarter = str(quarter_info.get("fiscal_quarter") or existing["fiscal_quarter"]).strip()
    quarter_end_date = _parse_date(quarter_info.get("quarter_end_date")) or _parse_date(existing.get("quarter_end_date"))
    earnings_date = _parse_date(quarter_info.get("earnings_date")) or _parse_date(existing.get("earnings_date"))
    if not ticker:
        ticker = str(quarter_info.get("ticker") or "").strip().upper()

    new_financials = _deep_merge(existing.get("financials") or {}, parsed.get("financials") or {})
    new_company_specific = _merge_company_specific(
        existing.get("company_specific") or [], parsed.get("company_specific") or [],
    )
    new_analysis = _deep_merge(
        existing.get("analysis") or {},
        {
            "management_commentary": parsed.get("management_commentary") or {},
            "analysis": parsed.get("analysis") or {},
            "keywords": _merge_keywords(
                (existing.get("analysis") or {}).get("keywords") or [],
                parsed.get("keywords") or [],
            ),
            "guidance": parsed.get("guidance") or {},
        },
    )
    new_estimates = _deep_merge(existing.get("estimates") or {}, parsed.get("estimates_vs_actuals") or {})
    new_price_reaction = _deep_merge(existing.get("price_reaction") or {}, parsed.get("price_reaction") or {})

    record = {
        "company_name": company_name,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "quarter_end_date": quarter_end_date,
        "earnings_date": earnings_date,
        "financials": new_financials,
        "company_specific": new_company_specific,
        "analysis": new_analysis,
        "estimates": new_estimates,
        "price_reaction": new_price_reaction,
        "raw_llm_response": raw_response,
        "provider": provider_name,
        "model": model,
        "output_language": output_language,
    }
    _upsert_earnings_report(record)
    return get_earnings_report(company_name, fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter) or record


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, new_val in override.items():
        if new_val is None:
            continue
        old_val = result.get(key)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            result[key] = _deep_merge(old_val, new_val)
        elif isinstance(old_val, list) and isinstance(new_val, list):
            if new_val:
                result[key] = new_val if len(new_val) >= len(old_val) else old_val
        else:
            if new_val is not None and new_val != "":
                result[key] = new_val
    return result


def _merge_company_specific(existing: list, new: list) -> list:
    if not new:
        return existing
    if not existing:
        return new
    by_title = {str(sec.get("title") or "").strip().lower(): sec for sec in existing}
    for sec in new:
        title_key = str(sec.get("title") or "").strip().lower()
        if title_key in by_title:
            old_sec = by_title[title_key]
            merged = dict(old_sec)
            if sec.get("data"):
                if isinstance(old_sec.get("data"), dict) and isinstance(sec["data"], dict):
                    merged["data"] = _deep_merge(old_sec["data"], sec["data"])
                elif isinstance(old_sec.get("data"), list) and isinstance(sec["data"], list) and len(sec["data"]) >= len(old_sec.get("data") or []):
                    merged["data"] = sec["data"]
                elif sec["data"]:
                    merged["data"] = sec["data"]
            if sec.get("commentary"):
                merged["commentary"] = sec["commentary"]
            by_title[title_key] = merged
        else:
            by_title[title_key] = sec
    return list(by_title.values())


def _merge_keywords(existing: list, new: list) -> list:
    seen = set()
    result = []
    for kw in existing + new:
        lower = str(kw).strip().lower()
        if lower not in seen:
            seen.add(lower)
            result.append(str(kw).strip())
    return result


def list_earnings_reports(company_name: str, *, limit: int = 12) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM {TBL_COMPANY_EARNINGS_REPORT}
                WHERE company_name = %s
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT %s
                """,
                (company_name, max(1, int(limit))),
            )
            return [_row_to_dict(row) for row in cur.fetchall()]


def get_earnings_report(
    company_name: str, *, fiscal_year: str, fiscal_quarter: str,
) -> Optional[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM {TBL_COMPANY_EARNINGS_REPORT}
                WHERE company_name = %s AND fiscal_year = %s AND fiscal_quarter = %s
                """,
                (company_name, fiscal_year, fiscal_quarter),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None


def list_earnings_report_quarters(company_name: str) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT fiscal_year, fiscal_quarter, earnings_date
                FROM {TBL_COMPANY_EARNINGS_REPORT}
                WHERE company_name = %s
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                """,
                (company_name,),
            )
            return [
                {
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_quarter": row["fiscal_quarter"],
                    "earnings_date": row["earnings_date"].isoformat() if row["earnings_date"] else None,
                }
                for row in cur.fetchall()
            ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_ticker(company_name: str) -> str:
    try:
        from market_agent.services.company import get_company_profile
        profile = get_company_profile(company_name)
        return str((profile or {}).get("ticker") or "").strip().upper()
    except Exception:
        return ""


def _fetch_and_store(
    company_name: str,
    ticker: str,
    prompt: str,
    *,
    provider_name: str,
    model: str,
    output_language: str,
) -> Dict[str, Any]:
    provider = get_news_provider(
        provider_name, model=model, timeout_sec=180, use_web_search=True,
    )
    with usage_context("earnings_report", company_name=company_name, module="earnings"):
        raw_response = provider.generate_text(prompt=prompt)
    parsed = _parse_json_response(raw_response)
    if not parsed:
        log.warning("Failed to parse LLM response for %s earnings", company_name)
        return {"error": "Failed to parse LLM response", "raw": raw_response}

    quarter_info = parsed.get("quarter_info") or {}
    fiscal_year = str(quarter_info.get("fiscal_year") or "").strip()
    fiscal_quarter = str(quarter_info.get("fiscal_quarter") or "").strip()
    if not fiscal_year or not fiscal_quarter:
        log.warning("Missing quarter_info in LLM response for %s", company_name)
        return {"error": "LLM did not return quarter identification", "raw": raw_response}

    quarter_end_date = _parse_date(quarter_info.get("quarter_end_date"))
    earnings_date = _parse_date(quarter_info.get("earnings_date"))
    if not ticker:
        ticker = str(quarter_info.get("ticker") or "").strip().upper()

    record = {
        "company_name": company_name,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "quarter_end_date": quarter_end_date,
        "earnings_date": earnings_date,
        "financials": parsed.get("financials") or {},
        "company_specific": parsed.get("company_specific") or [],
        "analysis": {
            "management_commentary": parsed.get("management_commentary") or {},
            "analysis": parsed.get("analysis") or {},
            "keywords": parsed.get("keywords") or [],
            "guidance": parsed.get("guidance") or {},
        },
        "estimates": parsed.get("estimates_vs_actuals") or {},
        "price_reaction": parsed.get("price_reaction") or {},
        "raw_llm_response": raw_response,
        "provider": provider_name,
        "model": model,
        "output_language": output_language,
    }
    _upsert_earnings_report(record)
    return get_earnings_report(company_name, fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter) or record


def _upsert_earnings_report(item: Dict[str, Any]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_EARNINGS_REPORT}
                    (company_name, ticker, fiscal_year, fiscal_quarter, quarter_end_date,
                     earnings_date, financials, company_specific, analysis, estimates,
                     price_reaction, raw_llm_response, provider, model, output_language, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s, %s, %s, %s, NOW())
                ON CONFLICT (company_name, fiscal_year, fiscal_quarter)
                DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    quarter_end_date = EXCLUDED.quarter_end_date,
                    earnings_date = EXCLUDED.earnings_date,
                    financials = EXCLUDED.financials,
                    company_specific = EXCLUDED.company_specific,
                    analysis = EXCLUDED.analysis,
                    estimates = EXCLUDED.estimates,
                    price_reaction = EXCLUDED.price_reaction,
                    raw_llm_response = EXCLUDED.raw_llm_response,
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    output_language = EXCLUDED.output_language,
                    updated_at = NOW()
                """,
                (
                    item["company_name"], item["ticker"],
                    item["fiscal_year"], item["fiscal_quarter"],
                    item["quarter_end_date"], item["earnings_date"],
                    json.dumps(item["financials"], ensure_ascii=False),
                    json.dumps(item["company_specific"], ensure_ascii=False),
                    json.dumps(item["analysis"], ensure_ascii=False),
                    json.dumps(item["estimates"], ensure_ascii=False),
                    json.dumps(item["price_reaction"], ensure_ascii=False),
                    item["raw_llm_response"],
                    item["provider"], item["model"], item["output_language"],
                ),
            )
        conn.commit()


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    def _jsonb(val: Any) -> Any:
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return {}
        return {}

    return {
        "id": row["id"],
        "company_name": row["company_name"],
        "ticker": row["ticker"],
        "fiscal_year": row["fiscal_year"],
        "fiscal_quarter": row["fiscal_quarter"],
        "quarter_end_date": row["quarter_end_date"].isoformat() if row["quarter_end_date"] else None,
        "earnings_date": row["earnings_date"].isoformat() if row["earnings_date"] else None,
        "financials": _jsonb(row["financials"]),
        "company_specific": _jsonb(row["company_specific"]),
        "analysis": _jsonb(row["analysis"]),
        "estimates": _jsonb(row["estimates"]),
        "price_reaction": _jsonb(row["price_reaction"]),
        "provider": row["provider"],
        "model": row["model"],
        "output_language": row["output_language"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                parsed = json.loads(text[brace_start : brace_end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value)).date()
    except (ValueError, TypeError):
        return None
