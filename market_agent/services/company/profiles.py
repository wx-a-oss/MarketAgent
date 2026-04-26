"""Company profile functions."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, time, timedelta, datetime, timezone
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.datasources.finnhub import FinnhubClient
from market_agent.services.company.ticker_fallbacks import resolve_company_ticker_fallback
from market_agent.schema_fields import (
    TBL_COMPANY_NEWS_ANALYZED,
    TBL_COMPANY_NEWS_DAILY_CLUSTER,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
)
from market_agent.services.company._helpers import (
    _normalize_company_name,
    _normalize_ticker,
    _resolve_symbol_from_lookup,
)

logger = logging.getLogger("uvicorn.error")


def get_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    company_name,
                    ticker,
                    name,
                    exchange,
                    currency,
                    country,
                    ipo,
                    weburl,
                    logo,
                    finnhub_industry,
                    phone,
                    market_capitalization,
                    share_outstanding,
                    cusip,
                    isin,
                    lei,
                    properties_extension
                FROM company_profile
                WHERE company_name = %s
                """,
                (company_name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            profile = {key: row[key] for key in row.keys()}
            extra = profile.pop("properties_extension", None) or {}
            if isinstance(extra, dict):
                profile.update(extra)
            return profile


def set_company_ticker(company_name: str, ticker: Optional[str]) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return None
    normalized_ticker = _normalize_ticker(ticker)
    existing = get_company_profile(company_name)
    existing_ticker = _normalize_ticker(existing.get("ticker")) if existing else None
    if company_has_fetched_data(company_name) and normalized_ticker != existing_ticker:
        raise ValueError("ticker cannot be changed after company news or story data has been fetched")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_profile (
                    company_name,
                    ticker,
                    fetched_at
                )
                VALUES (%s, %s, NOW())
                ON CONFLICT (company_name)
                DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    fetched_at = NOW()
                """,
                (company_name, normalized_ticker),
            )
        conn.commit()
    return get_company_profile(company_name)


def ensure_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    existing = get_company_profile(company_name)
    if existing:
        return existing
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        logger.warning("FINNHUB_API_KEY not set; skipping profile fetch for %s", company_name)
        return None
    client = FinnhubClient(api_key)
    logger.info("Resolving ticker via Finnhub symbol lookup for %s", company_name)
    ticker = _resolve_symbol_from_lookup(client.symbol_lookup(company_name), company_name)
    if not ticker:
        fallback_ticker = resolve_company_ticker_fallback(company_name)
        if not fallback_ticker:
            logger.warning("Symbol lookup returned no ticker for %s", company_name)
            return None
        ticker = fallback_ticker
        logger.info(
            "Using manual ticker fallback for %s (ticker=%s)",
            company_name,
            ticker,
        )
    logger.info("Fetching company profile from Finnhub for %s (ticker=%s)", company_name, ticker)
    profile = client.company_profile(ticker)
    if not profile:
        logger.warning("Finnhub profile fetch returned empty for %s (ticker=%s)", company_name, ticker)
        return None
    logger.info("Finnhub profile fetch succeeded for %s", company_name)
    properties_extension = _extract_profile_extension(profile)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_profile (
                    company_name,
                    ticker,
                    name,
                    exchange,
                    currency,
                    country,
                    ipo,
                    weburl,
                    logo,
                    finnhub_industry,
                    phone,
                    market_capitalization,
                    share_outstanding,
                    cusip,
                    isin,
                    lei,
                    properties_extension
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (company_name)
                DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange,
                    currency = EXCLUDED.currency,
                    country = EXCLUDED.country,
                    ipo = EXCLUDED.ipo,
                    weburl = EXCLUDED.weburl,
                    logo = EXCLUDED.logo,
                    finnhub_industry = EXCLUDED.finnhub_industry,
                    phone = EXCLUDED.phone,
                    market_capitalization = EXCLUDED.market_capitalization,
                    share_outstanding = EXCLUDED.share_outstanding,
                    cusip = EXCLUDED.cusip,
                    isin = EXCLUDED.isin,
                    lei = EXCLUDED.lei,
                    properties_extension = EXCLUDED.properties_extension,
                    fetched_at = NOW()
                """,
                (
                    company_name,
                    profile.get("ticker") or profile.get("symbol"),
                    profile.get("name"),
                    profile.get("exchange"),
                    profile.get("currency"),
                    profile.get("country"),
                    profile.get("ipo") or None,
                    profile.get("weburl"),
                    profile.get("logo"),
                    profile.get("finnhubIndustry"),
                    profile.get("phone"),
                    profile.get("marketCapitalization"),
                    profile.get("shareOutstanding"),
                    profile.get("cusip"),
                    profile.get("isin"),
                    profile.get("lei"),
                    json.dumps(properties_extension) if properties_extension else None,
                ),
            )
        conn.commit()
    return profile


def _has_company_raw_for_day(company_name: str, target_date: date) -> bool:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM company_news_raw
                    WHERE company_name = %s
                      AND news_date_time >= %s
                      AND news_date_time < %s
                    LIMIT 1
                )
                """,
                (company_name, start_dt, end_dt),
            )
            row = cur.fetchone()
    return bool(row and row[0])


def _count_company_raw_for_range(company_name: str, start_date: date, end_date: date) -> int:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return 0
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM company_news_raw
                WHERE company_name = %s
                  AND news_date_time >= %s
                  AND news_date_time < %s
                """,
                (company_name, start_dt, end_dt),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _build_fetch_ranges_for_slice(
    company_name: str,
    *,
    slice_start: date,
    slice_end: date,
    today: date,
) -> List[tuple[date, date]]:
    fetch_days: List[date] = []
    current = slice_start
    while current <= slice_end:
        if current >= today or not _has_company_raw_for_day(company_name, current):
            fetch_days.append(current)
        current += timedelta(days=1)
    if not fetch_days:
        return []
    ranges: List[tuple[date, date]] = []
    range_start = fetch_days[0]
    prev = fetch_days[0]
    for day in fetch_days[1:]:
        if day == prev + timedelta(days=1):
            prev = day
            continue
        ranges.append((range_start, prev))
        range_start = day
        prev = day
    ranges.append((range_start, prev))
    return ranges


def company_has_fetched_data(company_name: str) -> bool:
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return False
    with get_connection() as conn:
        with conn.cursor() as cur:
            checks = [
                "SELECT EXISTS(SELECT 1 FROM company_news_raw WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_NEWS_ANALYZED} WHERE company_name = %s LIMIT 1)",
                "SELECT EXISTS(SELECT 1 FROM company_news_daily_report WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_NEWS_DAILY_CLUSTER} WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_STORY_STATE} WHERE company_name = %s LIMIT 1)",
                f"SELECT EXISTS(SELECT 1 FROM {TBL_COMPANY_STORY_UPDATE} WHERE company_name = %s LIMIT 1)",
            ]
            for sql in checks:
                cur.execute(sql, (company_name,))
                row = cur.fetchone()
                if row and bool(row[0]):
                    return True
    return False


def _extract_profile_extension(profile: Dict[str, Any]) -> Dict[str, Any]:
    known = {
        "ticker",
        "symbol",
        "name",
        "exchange",
        "currency",
        "country",
        "ipo",
        "weburl",
        "logo",
        "finnhubIndustry",
        "phone",
        "marketCapitalization",
        "shareOutstanding",
        "cusip",
        "isin",
        "lei",
    }
    return {key: value for key, value in profile.items() if key not in known}


def _resolve_company_ticker(company_name: str) -> Optional[str]:
    profile = get_company_profile(company_name)
    if not profile:
        profile = ensure_company_profile(company_name)
    if not profile:
        return None
    for key in ("ticker", "symbol"):
        value = profile.get(key)
        if value:
            return str(value).strip()
    return None
