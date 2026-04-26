"""Macro calendar events: list, refresh, upsert, and supporting helpers."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from market_agent.analysis.company.news.db import ensure_database_schema, get_connection
from market_agent.analysis.company.news.service import (
    _build_output_language_line,
    _parse_json_object,
)
from market_agent.llms.news.openai import generate_text_with_web_search
from market_agent.llms.news.registry import get_news_provider
from market_agent.schema_fields import (
    COL_EVENT_DATE_TIME,
    COL_OUTPUT_LANGUAGE,
    TBL_MARKET_MACRO_EVENT,
)

from market_agent.workflows.market_news import (
    DEFAULT_MARKET_PROVIDER,
    DEFAULT_MARKET_MODEL,
    APP_LOCAL_TZ,
    _current_app_date,
    _generate_market_research_text,
)

logger = logging.getLogger("uvicorn.error")


# Reference to the re-export shim so that monkeypatches on market_updates
# (which is what tests use) are visible to code in this sub-module.
def _shim():
    return sys.modules.get('market_agent.workflows.market_updates') or sys.modules[__name__]


def list_market_macro_events(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    ensure_database_schema()
    clauses = []
    params: List[Any] = []
    if start_date:
        clauses.append(f"{COL_EVENT_DATE_TIME} >= %s")
        params.append(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
    if end_date:
        clauses.append(f"{COL_EVENT_DATE_TIME} <= %s")
        params.append(datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_MARKET_MACRO_EVENT}
                {where_sql}
                ORDER BY {COL_EVENT_DATE_TIME} ASC, updated_at DESC
                LIMIT %s
                """,
                (*params, max(1, int(limit))),
            )
            rows = cur.fetchall()
    return _dedupe_macro_events_for_display([_row_to_macro_event(row) for row in rows])


def refresh_market_macro_events(
    *,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    output_language: str = "zh-CN",
    extend_window: bool = False,
) -> Dict[str, Any]:
    ensure_database_schema()
    if extend_window:
        window_start, window_end = _shim()._resolve_macro_extension_window()
        action = "refresh_next_3_months"
    else:
        window_start, window_end = _shim()._resolve_macro_maintenance_window()
        action = "maintain_next_3_months"
    existing_events = _shim().list_market_macro_events(start_date=window_start, end_date=window_end, limit=500)
    selected = _shim()._fetch_macro_calendar_with_llm(
        provider_name=provider_name,
        model=model,
        output_language=output_language,
        start_date=window_start,
        end_date=window_end,
        existing_events=existing_events,
    )
    selected = _filter_new_macro_events(existing_events=existing_events, candidate_events=selected)
    updated = 0
    for item in selected:
        updated += int(
            _shim()._upsert_market_macro_event(
                item,
                summary_text=None,
                provider_name=provider_name,
                model=model,
                output_language=output_language,
            )
        )
    return {
        "updated": updated,
        "event_count": len(selected),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "action": action,
        "input_item_count": len(selected),
        "output_char_count": 0,
    }


def resolve_market_macro_calendar_window() -> tuple[date, date]:
    today = _shim()._current_app_date()
    window_start = today.replace(day=1)
    third_month_start = _add_months(window_start, 3)
    window_end = third_month_start - timedelta(days=1)
    return window_start, window_end


def _upsert_market_macro_event(
    item: Dict[str, Any],
    *,
    summary_text: Optional[str],
    provider_name: str,
    model: str,
    output_language: str,
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_MARKET_MACRO_EVENT}
                    (event_code, event_name, category, country, {COL_EVENT_DATE_TIME},
                     actual_value, previous_value, consensus_value, unit, importance,
                     source_payload, impact_summary, provider, model, {COL_OUTPUT_LANGUAGE}, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
                ON CONFLICT (event_name, event_date_time, country)
                DO NOTHING
                """,
                (
                    item.get("event_code"),
                    item.get("event_name"),
                    item.get("category"),
                    item.get("country"),
                    item.get("event_date_time"),
                    item.get("actual_value"),
                    item.get("previous_value"),
                    item.get("consensus_value"),
                    item.get("unit"),
                    item.get("importance"),
                    json.dumps(item.get("source_payload") or {}, ensure_ascii=False),
                    summary_text,
                    provider_name,
                    model,
                    output_language,
                ),
            )
        conn.commit()
    return int(cur.rowcount or 0)


def _row_to_macro_event(row: Dict[str, Any]) -> Dict[str, Any]:
    source_payload = row.get("source_payload") or {}
    source_url = None
    if isinstance(source_payload, dict):
        source_url = source_payload.get("source_url")
    return {
        "id": int(row["id"]),
        "event_name": row["event_name"],
        "category": row["category"],
        "country": row["country"],
        "event_date_time": row[COL_EVENT_DATE_TIME].isoformat() if row[COL_EVENT_DATE_TIME] else None,
        "actual_value": row["actual_value"],
        "previous_value": row["previous_value"],
        "consensus_value": row["consensus_value"],
        "unit": row["unit"],
        "importance": row["importance"],
        "impact_summary": row["impact_summary"],
        "source_url": source_url,
        "provider": row["provider"],
        "model": row["model"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
    }


def _macro_prompt_existing_events(events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "event_date": _macro_event_date_key(item),
            "event_name": str(item.get("event_name") or ""),
            "country": str(item.get("country") or "US"),
            "category": str(item.get("category") or "macro"),
        }
        for item in events[:200]
    ]


def _dedupe_macro_events_for_display(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_key: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for item in events:
        key = _macro_event_semantic_key(item)
        current = best_by_key.get(key)
        if current is None or _macro_event_quality(item) > _macro_event_quality(current):
            best_by_key[key] = item
    return sorted(best_by_key.values(), key=lambda item: (str(item.get("event_date_time") or ""), str(item.get("event_name") or "")))


def _filter_new_macro_events(
    *,
    existing_events: List[Dict[str, Any]],
    candidate_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    existing_keys = {_macro_event_semantic_key(item) for item in existing_events}
    seen_keys: set[tuple[str, str, str]] = set()
    filtered: List[Dict[str, Any]] = []
    for item in candidate_events:
        key = _macro_event_semantic_key(item)
        if key in existing_keys or key in seen_keys:
            continue
        seen_keys.add(key)
        filtered.append(item)
    return filtered


def _macro_event_semantic_key(item: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        _macro_event_date_key(item),
        str(item.get("country") or "US").strip().lower() or "us",
        _macro_event_name_key(str(item.get("event_name") or "")),
    )


def _macro_event_date_key(item: Dict[str, Any]) -> str:
    value = item.get("event_date_time")
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def _macro_event_name_key(name: str) -> str:
    text = " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in name).split())
    if not text:
        return "event"
    if "federal open market" in text or "fomc" in text:
        if "press conference" in text or "powell" in text:
            return "fomc_press_conference"
        if "minutes" in text:
            return "fomc_minutes"
        if "begin" in text or "starts" in text or ("meeting" in text and not any(token in text for token in ["rate", "decision", "statement", "end"])):
            return "fomc_meeting_start"
        return "fomc_rate_decision"
    if "consumer price index" in text or text in {"cpi", "us cpi"} or " cpi" in f" {text}":
        return "cpi"
    if "producer price index" in text or text in {"ppi", "us ppi"} or " ppi" in f" {text}":
        return "ppi"
    if "nonfarm payroll" in text or "payrolls" in text or " nfp" in f" {text}":
        return "nonfarm_payrolls"
    if "unemployment" in text:
        return "unemployment"
    if "gross domestic product" in text or " gdp" in f" {text}":
        return "gdp"
    if "retail sales" in text:
        return "retail_sales"
    if "consumer confidence" in text or text == "confidence":
        return "consumer_confidence"
    if "trade balance" in text:
        return "trade_balance"
    if "ism" in text and "manufacturing" in text:
        return "ism_manufacturing_pmi"
    if "ism" in text and "services" in text:
        return "ism_services_pmi"
    if "housing" in text and ("starts" in text or "permits" in text):
        return "housing_starts_building_permits"
    words = [word for word in text.split() if word not in {"us", "u", "s", "united", "states", "release", "data"}]
    return "_".join(words[:8]) or "event"


def _macro_event_quality(item: Dict[str, Any]) -> tuple[int, int, int]:
    name = str(item.get("event_name") or "").lower()
    score = 0
    if "rate decision" in name:
        score += 40
    if "press conference" in name or "powell" in name:
        score += 35
    if "minutes" in name:
        score += 30
    if "meeting ends" in name or "statement" in name:
        score += 10
    if name.startswith("us "):
        score += 2
    if item.get("source_url"):
        score += 1
    return (score, len(name), int(item.get("id") or 0))


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _resolve_macro_extension_window() -> tuple[date, date]:
    return resolve_market_macro_calendar_window()


def _resolve_macro_maintenance_window() -> tuple[date, date]:
    return resolve_market_macro_calendar_window()


def _fetch_macro_calendar_with_llm(
    *,
    provider_name: str,
    model: str,
    output_language: str,
    start_date: date,
    end_date: date,
    existing_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    prompt = _build_market_macro_calendar_prompt(
        start_date=start_date,
        end_date=end_date,
        output_language=output_language,
        existing_events=existing_events,
    )
    raw_output = _shim()._generate_market_research_text(
        provider_name=provider_name,
        model=model,
        prompt=prompt,
    )
    payload: Any
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        payload = _parse_json_object(raw_output)
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        items = payload.get("events") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    selected = [_normalize_macro_row(item) for item in items if _macro_event_supported(item)]
    selected = [item for item in selected if item]
    selected.sort(key=lambda row: row["event_date_time"])
    return selected[:60]


def _build_market_macro_calendar_prompt(
    *,
    start_date: date,
    end_date: date,
    output_language: str,
    existing_events: List[Dict[str, Any]],
) -> str:
    existing_json = json.dumps(_macro_prompt_existing_events(existing_events), ensure_ascii=False, indent=2)
    return (
        f"Update a U.S. macro and government release calendar from {start_date.isoformat()} through {end_date.isoformat()}.\n"
        "Use web search / grounded search to find scheduled market-relevant releases.\n"
        "Include at least CPI, PPI, nonfarm payrolls, unemployment rate, GDP, FOMC/rate decisions, and major Treasury or central-bank policy statements.\n"
        "For the Fed, include the scheduled FOMC rate decision and Powell press conference when scheduled. Do not create separate duplicate entries for generic FOMC meeting, meeting ends, statement, or rate decision if they refer to the same release on the same date.\n"
        "Also include retail sales, PMI/ISM, consumer confidence, housing data, and trade balance when scheduled in this window.\n"
        "This refresh is used repeatedly to fill missing future events in the stored calendar, so completeness matters more than commentary.\n"
        "The stored calendar already contains the events listed below. Return only missing events. Do not return the same event or a semantically equivalent event under a slightly different name.\n"
        "Focus only on when the release happens and what is being released.\n"
        "Return JSON only as an object with an events array.\n"
        "Each object must contain:\n"
        '- event_name\n'
        '- event_date_time (ISO 8601 if possible)\n'
        '- category\n'
        '- country\n'
        '- actual_value\n'
        '- prior_value\n'
        '- expectation_value\n'
        '- source_url\n'
        "Rules:\n"
        "- Keep only scheduled releases/events.\n"
        "- Do not add narrative analysis, impact analysis, or market commentary.\n"
        "- Do not rank importance.\n"
        "- If exact release time is known, include it.\n"
        "- If only the date is known, use the date and leave time empty or use 00:00:00.\n"
        "- Deduplicate repeated entries before returning JSON.\n"
        "- Focus on U.S. releases first for v1.\n"
        "- Keep event names in standard English market terminology even if the UI language is not English.\n"
        "If actual/prior/expectation are not known yet for future releases, leave them empty strings.\n"
        f"Existing stored events JSON:\n{existing_json}\n"
        "Output JSON schema:\n"
        "{\n"
        '  "events": [\n'
        "    {\n"
        '      "event_name": "US CPI",\n'
        '      "event_date_time": "2026-04-10T12:30:00+00:00",\n'
        '      "category": "inflation",\n'
        '      "country": "US",\n'
        '      "actual_value": "",\n'
        '      "prior_value": "",\n'
        '      "expectation_value": "",\n'
        '      "source_url": "https://..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def _macro_event_supported(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    event = str(
        item.get("event")
        or item.get("name")
        or item.get("event_name")
        or ""
    ).strip().lower()
    watched = [
        "cpi",
        "ppi",
        "gdp",
        "payroll",
        "unemployment",
        "fomc",
        "fed",
        "retail sales",
        "pmi",
        "ism",
        "consumer confidence",
        "housing",
        "trade balance",
        "rate",
        "treasury",
    ]
    return any(token in event for token in watched)


def _normalize_macro_row(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw_dt = item.get("event_date_time") or item.get("time") or item.get("date")
    event_dt = None
    if raw_dt:
        try:
            event_dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
        except ValueError:
            try:
                event_dt = parsedate_to_datetime(str(raw_dt))
            except Exception:
                event_dt = None
    if event_dt is None:
        return None
    event_name = str(
        item.get("event")
        or item.get("name")
        or item.get("event_name")
        or ""
    ).strip()
    if not event_name:
        return None
    return {
        "event_code": str(item.get("code") or "").strip() or None,
        "event_name": event_name,
        "category": str(item.get("category") or "").strip() or "macro",
        "country": str(item.get("country") or "US").strip() or "US",
        "event_date_time": event_dt,
        "actual_value": str(item.get("actual") or item.get("actualValue") or item.get("actual_value") or "").strip() or None,
        "previous_value": str(item.get("prev") or item.get("previous") or item.get("prior_value") or "").strip() or None,
        "consensus_value": str(item.get("consensus") or item.get("estimate") or item.get("expectation_value") or "").strip() or None,
        "unit": str(item.get("unit") or "").strip() or None,
        "importance": str(item.get("importance") or item.get("impact") or "").strip() or None,
        "source_payload": item,
    }
