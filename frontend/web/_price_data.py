"""Company price history and move analysis.

Extracted from server.py — no logic changes.
"""
from __future__ import annotations

import json
import logging
import os
import time as pytime
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_POINT_DATE_TIME,
    COL_RANGE_KEY,
    COL_TICKER,
    COL_TRADE_DATE,
    TBL_COMPANY_PRICE_DAILY,
    TBL_COMPANY_PRICE_MOVE_ANALYSIS,
)

logger = logging.getLogger("uvicorn.error")


def _parse_ma_windows(raw: str) -> List[int]:
    values: List[int] = []
    for part in str(raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value <= 1 or value > 500:
            continue
        if value not in values:
            values.append(value)
    return values or [20, 50, 200]


def _fetch_yahoo_daily_price_history(symbol: str, *, years: int) -> List[Dict[str, Any]]:
    safe_years = max(1, min(int(years), 5))
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?"
        + urllib.parse.urlencode(
            {
                "interval": "1d",
                "range": f"{safe_years}y",
                "includeAdjustedClose": "true",
                "events": "div,splits",
            }
        )
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results:
        return []
    result = results[0] or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    quote = quotes[0] if quotes else {}
    adjclose_list = []
    adjclose_nodes = indicators.get("adjclose") or []
    if adjclose_nodes:
        adjclose_list = adjclose_nodes[0].get("adjclose") or []

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    points: List[Dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        try:
            ts_int = int(ts)
        except Exception:
            continue
        close = closes[idx] if idx < len(closes) else None
        if close is None:
            continue
        dt = datetime.utcfromtimestamp(ts_int).date()
        point: Dict[str, Any] = {
            "date": dt.isoformat(),
            "open": _round_num(opens[idx] if idx < len(opens) else None),
            "high": _round_num(highs[idx] if idx < len(highs) else None),
            "low": _round_num(lows[idx] if idx < len(lows) else None),
            "close": _round_num(close),
            "volume": _int_or_none(volumes[idx] if idx < len(volumes) else None),
        }
        adj_close = adjclose_list[idx] if idx < len(adjclose_list) else None
        if adj_close is not None:
            point["adj_close"] = _round_num(adj_close)
        points.append(point)
    return points


def _fetch_finnhub_daily_price_history(
    symbol: str,
    *,
    years: int,
    api_key: str,
) -> List[Dict[str, Any]]:
    safe_years = max(1, min(int(years), 5))
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=366 * safe_years)
    url = (
        "https://finnhub.io/api/v1/stock/candle?"
        + urllib.parse.urlencode(
            {
                "symbol": symbol,
                "resolution": "D",
                "from": int(start_dt.timestamp()),
                "to": int(end_dt.timestamp()),
                "token": api_key,
            }
        )
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    if payload.get("s") != "ok":
        return []
    timestamps = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or []
    points: List[Dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        try:
            ts_int = int(ts)
        except Exception:
            continue
        close = closes[idx] if idx < len(closes) else None
        if close is None:
            continue
        dt = datetime.utcfromtimestamp(ts_int).date()
        points.append(
            {
                "date": dt.isoformat(),
                "date_time": datetime.utcfromtimestamp(ts_int).replace(tzinfo=ZoneInfo("UTC")).isoformat(),
                "open": _round_num(opens[idx] if idx < len(opens) else None),
                "high": _round_num(highs[idx] if idx < len(highs) else None),
                "low": _round_num(lows[idx] if idx < len(lows) else None),
                "close": _round_num(close),
                "volume": _int_or_none(volumes[idx] if idx < len(volumes) else None),
            }
        )
    return points


def _attach_moving_averages(
    points: List[Dict[str, Any]],
    *,
    windows: List[int],
) -> List[Dict[str, Any]]:
    if not points:
        return []
    closes: List[Optional[float]] = []
    rolling_sums: Dict[int, float] = {window: 0.0 for window in windows}
    rolling_queues: Dict[int, List[Optional[float]]] = {window: [] for window in windows}
    rolling_valid_counts: Dict[int, int] = {window: 0 for window in windows}

    enriched: List[Dict[str, Any]] = []
    for point in points:
        close_val_raw = point.get("adj_close")
        if not isinstance(close_val_raw, (int, float)):
            close_val_raw = point.get("close")
        close_val = float(close_val_raw) if isinstance(close_val_raw, (int, float)) else None
        closes.append(close_val)
        out = dict(point)
        for window in windows:
            q = rolling_queues[window]
            q.append(close_val)
            if close_val is not None:
                rolling_sums[window] += close_val
                rolling_valid_counts[window] += 1
            if len(q) > window:
                removed = q.pop(0)
                if removed is not None:
                    rolling_sums[window] -= float(removed)
                    rolling_valid_counts[window] -= 1
            ma_key = f"ma_{window}"
            if len(q) == window and rolling_valid_counts[window] == window:
                out[ma_key] = round(rolling_sums[window] / window, 4)
            else:
                out[ma_key] = None
        enriched.append(out)
    return enriched


def _normalize_price_range_key(range_key: str) -> str:
    token = str(range_key or "").strip().upper()
    allowed = {"1D", "5D", "1M", "3M", "6M", "8M", "1Y", "2Y", "3Y", "5Y"}
    return token if token in allowed else "1Y"


def _price_range_config(range_key: str) -> Tuple[str, str]:
    mapping = {
        "1D": ("1d", "5m"),
        "5D": ("5d", "30m"),
        "1M": ("1mo", "1d"),
        "3M": ("3mo", "1d"),
        "6M": ("6mo", "1d"),
        # Yahoo chart doesn't provide 8mo directly; fetch 1y then trim.
        "8M": ("1y", "1d"),
        "1Y": ("1y", "1d"),
        "2Y": ("2y", "1d"),
        "3Y": ("3y", "1d"),
        "5Y": ("5y", "1d"),
    }
    normalized = _normalize_price_range_key(range_key)
    return mapping[normalized]


def _fetch_yahoo_price_history_by_range(symbol: str, *, range_key: str) -> List[Dict[str, Any]]:
    yahoo_range, interval = _price_range_config(range_key)
    hosts = [
        "https://query1.finance.yahoo.com",
        "https://query2.finance.yahoo.com",
    ]
    query = urllib.parse.urlencode(
        {
            "interval": interval,
            "range": yahoo_range,
            "includeAdjustedClose": "true",
            "events": "div,splits",
        }
    )
    for host in hosts:
        url = f"{host}/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning(
                "Yahoo price fetch failed: symbol=%s range=%s host=%s error=%s",
                symbol,
                range_key,
                host,
                exc,
            )
            continue
        points = _parse_yahoo_chart_payload(payload, intraday=(interval != "1d"))
        if points:
            return points
    return []


def _parse_yahoo_chart_payload(payload: Dict[str, Any], *, intraday: bool) -> List[Dict[str, Any]]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results:
        return []
    result = results[0] or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    quote = quotes[0] if quotes else {}
    adjclose_list: List[Any] = []
    adjclose_nodes = indicators.get("adjclose") or []
    if adjclose_nodes:
        adjclose_list = adjclose_nodes[0].get("adjclose") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    points: List[Dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        try:
            ts_int = int(ts)
        except Exception:
            continue
        close = closes[idx] if idx < len(closes) else None
        if close is None:
            continue
        dt = datetime.utcfromtimestamp(ts_int)
        point: Dict[str, Any] = {
            "date": dt.date().isoformat(),
            "date_time": dt.replace(tzinfo=ZoneInfo("UTC")).isoformat(),
            "open": _round_num(opens[idx] if idx < len(opens) else None),
            "high": _round_num(highs[idx] if idx < len(highs) else None),
            "low": _round_num(lows[idx] if idx < len(lows) else None),
            "close": _round_num(close),
            "volume": _int_or_none(volumes[idx] if idx < len(volumes) else None),
            "is_intraday": intraday,
        }
        adj_close = adjclose_list[idx] if idx < len(adjclose_list) else None
        if adj_close is not None:
            point["adj_close"] = _round_num(adj_close)
        points.append(point)
    return points


def _fetch_price_points_for_range(symbol: str, range_key: str) -> List[Dict[str, Any]]:
    normalized = _normalize_price_range_key(range_key)
    for attempt in range(2):
        points = _fetch_yahoo_price_history_by_range(symbol, range_key=normalized)
        if points:
            points = _trim_points_for_range(points, normalized)
            points = _attach_pct_change(points)
            return points
        # Stooq fallback (daily bars, no API key) when Yahoo is unavailable/rate-limited.
        stooq_daily = _fetch_stooq_daily_price_history(symbol)
        if stooq_daily:
            if normalized == "1D":
                stooq_daily = stooq_daily[-2:]
            elif normalized == "5D":
                stooq_daily = stooq_daily[-5:]
            elif normalized == "1M":
                stooq_daily = stooq_daily[-31:]
            elif normalized == "3M":
                stooq_daily = stooq_daily[-93:]
            elif normalized == "6M":
                stooq_daily = stooq_daily[-186:]
            elif normalized == "8M":
                stooq_daily = stooq_daily[-248:]
            elif normalized == "1Y":
                stooq_daily = stooq_daily[-366:]
            elif normalized == "2Y":
                stooq_daily = stooq_daily[-(366 * 2):]
            elif normalized == "3Y":
                stooq_daily = stooq_daily[-(366 * 3):]
            elif normalized == "5Y":
                stooq_daily = stooq_daily[-(366 * 5):]
            points = _attach_pct_change(stooq_daily)
            if points:
                return points
        # Finnhub fallback for daily windows only.
        if normalized in {"1M", "3M", "6M", "8M", "1Y", "2Y", "3Y", "5Y"}:
            api_key = os.getenv("FINNHUB_API_KEY", "").strip()
            if api_key:
                if normalized in {"1M", "3M", "6M", "8M", "1Y"}:
                    years = 1
                elif normalized in {"2Y"}:
                    years = 2
                elif normalized in {"3Y"}:
                    years = 3
                else:
                    years = 5
                history = _fetch_finnhub_daily_price_history(symbol, years=years, api_key=api_key)
                if normalized == "1M":
                    history = history[-31:]
                elif normalized == "3M":
                    history = history[-93:]
                elif normalized == "6M":
                    history = history[-186:]
                elif normalized == "8M":
                    history = history[-248:]
                elif normalized == "1Y":
                    history = history[-366:]
                elif normalized == "2Y":
                    history = history[-(366 * 2):]
                elif normalized == "3Y":
                    history = history[-(366 * 3):]
                points = _attach_pct_change(history)
                if points:
                    return points
        if attempt == 0:
            logger.warning(
                "Company price fetch returned no points on first attempt: symbol=%s range=%s; retrying",
                symbol,
                normalized,
            )
            pytime.sleep(0.6)
    return []


def _get_or_refresh_company_price_series(
    *,
    company_name: str,
    ticker: str,
    range_key: str,
) -> List[Dict[str, Any]]:
    _ensure_company_price_daily_schema()
    normalized = _normalize_price_range_key(range_key)
    company = str(company_name or "").strip()
    symbol = str(ticker or "").strip().upper()
    if not company or not symbol:
        return []
    latest_cached = _get_company_price_daily_latest_date(company_name=company, ticker=symbol)
    from frontend.web._market_data import _latest_settled_us_market_date
    latest_target = _latest_settled_us_market_date()
    fetch_range: Optional[str] = None
    if latest_cached is None:
        # New company: fetch as much as available up front.
        fetch_range = "5Y"
    elif latest_cached < latest_target:
        days_behind = (latest_target - latest_cached).days
        fetch_range = _pick_catchup_range(days_behind)
    if fetch_range:
        fetched = _fetch_price_points_for_range(symbol, fetch_range)
        if fetched:
            _upsert_company_price_daily_points(
                company_name=company,
                ticker=symbol,
                points=fetched,
                source="api_fallback_chain",
            )
    points = _list_company_price_daily_points(company_name=company, ticker=symbol, range_key=normalized)
    return points


def _pick_catchup_range(days_behind: int) -> str:
    safe_days = max(1, int(days_behind))
    if safe_days <= 31:
        return "1M"
    if safe_days <= 93:
        return "3M"
    if safe_days <= 186:
        return "6M"
    if safe_days <= 248:
        return "8M"
    if safe_days <= 366:
        return "1Y"
    if safe_days <= 366 * 2:
        return "2Y"
    if safe_days <= 366 * 3:
        return "3Y"
    return "5Y"


def _start_date_for_range(end_date: date, range_key: str) -> date:
    normalized = _normalize_price_range_key(range_key)
    if normalized == "1D":
        return end_date - timedelta(days=2)
    if normalized == "5D":
        return end_date - timedelta(days=12)
    mapping = {
        "1M": 31,
        "3M": 93,
        "6M": 186,
        "8M": 248,
        "1Y": 366,
        "2Y": 366 * 2,
        "3Y": 366 * 3,
        "5Y": 366 * 5,
    }
    return end_date - timedelta(days=mapping.get(normalized, 366) - 1)


def _list_company_price_daily_points(
    *,
    company_name: str,
    ticker: str,
    range_key: str,
) -> List[Dict[str, Any]]:
    _ensure_company_price_daily_schema()
    latest = _get_company_price_daily_latest_date(company_name=company_name, ticker=ticker)
    if latest is None:
        return []
    start = _start_date_for_range(latest, range_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    {COL_TRADE_DATE},
                    open,
                    high,
                    low,
                    close,
                    adj_close,
                    volume
                FROM {TBL_COMPANY_PRICE_DAILY}
                WHERE company_name = %s
                  AND {COL_TICKER} = %s
                  AND {COL_TRADE_DATE} >= %s
                ORDER BY {COL_TRADE_DATE} ASC
                """,
                (company_name, ticker, start),
            )
            rows = cur.fetchall()
    points: List[Dict[str, Any]] = []
    for row in rows:
        d = row[COL_TRADE_DATE]
        if not d:
            continue
        dt = datetime.combine(d, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
        points.append(
            {
                "date": d.isoformat(),
                "date_time": dt.isoformat(),
                "open": _round_num(row.get("open")),
                "high": _round_num(row.get("high")),
                "low": _round_num(row.get("low")),
                "close": _round_num(row.get("close")),
                "adj_close": _round_num(row.get("adj_close")),
                "volume": _int_or_none(row.get("volume")),
                "is_intraday": False,
            }
        )
    return points


def _list_company_price_daily_points_all(
    *,
    company_name: str,
    ticker: str,
) -> List[Dict[str, Any]]:
    _ensure_company_price_daily_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    {COL_TRADE_DATE},
                    open,
                    high,
                    low,
                    close,
                    adj_close,
                    volume
                FROM {TBL_COMPANY_PRICE_DAILY}
                WHERE company_name = %s
                  AND {COL_TICKER} = %s
                ORDER BY {COL_TRADE_DATE} ASC
                """,
                (company_name, ticker),
            )
            rows = cur.fetchall()
    points: List[Dict[str, Any]] = []
    for row in rows:
        d = row[COL_TRADE_DATE]
        if not d:
            continue
        dt = datetime.combine(d, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
        points.append(
            {
                "date": d.isoformat(),
                "date_time": dt.isoformat(),
                "open": _round_num(row.get("open")),
                "high": _round_num(row.get("high")),
                "low": _round_num(row.get("low")),
                "close": _round_num(row.get("close")),
                "adj_close": _round_num(row.get("adj_close")),
                "volume": _int_or_none(row.get("volume")),
                "is_intraday": False,
            }
        )
    return points


def _merge_trimmed_ma_points(
    *,
    visible_points: List[Dict[str, Any]],
    ma_points: List[Dict[str, Any]],
    windows: List[int],
) -> List[Dict[str, Any]]:
    if not visible_points:
        return []
    ma_by_date: Dict[str, Dict[str, Any]] = {
        str(point.get("date") or ""): point
        for point in ma_points
        if str(point.get("date") or "")
    }
    merged: List[Dict[str, Any]] = []
    for point in visible_points:
        row = dict(point)
        source = ma_by_date.get(str(point.get("date") or ""), {})
        for window in windows:
            key = f"ma_{window}"
            row[key] = source.get(key)
        merged.append(row)
    return merged


def _get_company_price_daily_latest_date(*, company_name: str, ticker: str) -> Optional[date]:
    _ensure_company_price_daily_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX({COL_TRADE_DATE}) AS max_trade_date
                FROM {TBL_COMPANY_PRICE_DAILY}
                WHERE company_name = %s
                  AND {COL_TICKER} = %s
                """,
                (company_name, ticker),
            )
            row = cur.fetchone()
    if not row:
        return None
    return row.get("max_trade_date")


def _upsert_company_price_daily_points(
    *,
    company_name: str,
    ticker: str,
    points: List[Dict[str, Any]],
    source: str,
) -> None:
    if not points:
        return
    _ensure_company_price_daily_schema()
    now = datetime.now(ZoneInfo("UTC"))
    with get_connection() as conn:
        with conn.cursor() as cur:
            for point in points:
                d_text = str(point.get("date") or "").strip()
                if not d_text:
                    continue
                try:
                    trade_day = datetime.fromisoformat(d_text).date()
                except Exception:
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_PRICE_DAILY} (
                        company_name, {COL_TICKER}, {COL_TRADE_DATE},
                        open, high, low, close, adj_close, volume,
                        source, source_symbol, currency, fetched_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_name, {COL_TICKER}, {COL_TRADE_DATE})
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        adj_close = EXCLUDED.adj_close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source,
                        source_symbol = EXCLUDED.source_symbol,
                        currency = EXCLUDED.currency,
                        fetched_at = EXCLUDED.fetched_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        company_name,
                        ticker,
                        trade_day,
                        point.get("open"),
                        point.get("high"),
                        point.get("low"),
                        point.get("close"),
                        point.get("adj_close"),
                        point.get("volume"),
                        source,
                        ticker,
                        "USD",
                        now,
                        now,
                    ),
                )
        conn.commit()


def _trim_points_for_range(points: List[Dict[str, Any]], range_key: str) -> List[Dict[str, Any]]:
    if not points:
        return points
    # 1D/5D are already specific windows from providers.
    if range_key in {"1D", "5D"}:
        return points
    lookback_days = {
        "1M": 31,
        "3M": 93,
        "6M": 186,
        "8M": 248,
        "1Y": 366,
        "2Y": 366 * 2,
        "3Y": 366 * 3,
        "5Y": 366 * 5,
    }.get(range_key)
    if lookback_days is None:
        return points
    end = points[-1].get("date")
    try:
        end_date = datetime.fromisoformat(str(end)).date()
    except Exception:
        return points
    start_date = end_date - timedelta(days=lookback_days - 1)
    trimmed: List[Dict[str, Any]] = []
    for row in points:
        try:
            d = datetime.fromisoformat(str(row.get("date"))).date()
        except Exception:
            continue
        if d >= start_date:
            trimmed.append(row)
    return trimmed or points


def _fetch_stooq_daily_price_history(symbol: str) -> List[Dict[str, Any]]:
    token = str(symbol or "").strip().lower()
    if not token:
        return []
    if token.startswith("^") or ":" in token:
        return []
    stooq_symbol = token if "." in token else f"{token}.us"
    url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode({"s": stooq_symbol, "i": "d"})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            csv_text = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("Stooq price fetch failed: symbol=%s error=%s", symbol, exc)
        return []
    rows = [line.strip() for line in csv_text.splitlines() if line.strip()]
    if len(rows) <= 1:
        return []
    points: List[Dict[str, Any]] = []
    for line in rows[1:]:
        cols = line.split(",")
        if len(cols) < 6:
            continue
        day = cols[0].strip()
        try:
            dt = datetime.fromisoformat(day)
            open_v = float(cols[1]) if cols[1] else None
            high_v = float(cols[2]) if cols[2] else None
            low_v = float(cols[3]) if cols[3] else None
            close_v = float(cols[4]) if cols[4] else None
            vol_v = int(float(cols[5])) if cols[5] else None
        except Exception:
            continue
        if close_v is None:
            continue
        points.append(
            {
                "date": dt.date().isoformat(),
                "date_time": dt.replace(tzinfo=ZoneInfo("UTC")).isoformat(),
                "open": _round_num(open_v),
                "high": _round_num(high_v),
                "low": _round_num(low_v),
                "close": _round_num(close_v),
                "volume": _int_or_none(vol_v),
                "is_intraday": False,
            }
        )
    return points


def _attach_pct_change(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prev_close: Optional[float] = None
    out: List[Dict[str, Any]] = []
    for point in points:
        row = dict(point)
        close = row.get("close")
        if isinstance(close, (int, float)) and prev_close not in (None, 0):
            row["pct_change"] = round(((float(close) - float(prev_close)) / float(prev_close)) * 100.0, 4)
        else:
            row["pct_change"] = None
        if isinstance(close, (int, float)):
            prev_close = float(close)
        out.append(row)
    return out


def _select_critical_price_points(points: List[Dict[str, Any]], *, top_n: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for row in points:
        pct = row.get("pct_change")
        if not isinstance(pct, (int, float)):
            continue
        enriched = dict(row)
        if not enriched.get("date_time") and enriched.get("date"):
            try:
                dt = datetime.fromisoformat(str(enriched["date"]))
                enriched["date_time"] = datetime.combine(
                    dt.date(),
                    datetime.min.time(),
                    tzinfo=ZoneInfo("UTC"),
                ).isoformat()
            except ValueError:
                enriched["date_time"] = ""
        candidates.append(enriched)
    candidates.sort(key=lambda item: abs(float(item.get("pct_change") or 0.0)), reverse=True)
    return candidates[:max(1, min(int(top_n), 20))]


def _build_company_price_move_prompt(
    *,
    company_name: str,
    ticker: str,
    point: Dict[str, Any],
    range_key: str,
    output_language: str,
) -> str:
    from market_agent.services.company import get_company_daily_report, get_news_report
    from frontend.web._market_data import _fetch_market_news, _resolve_market_price_sections
    from frontend.web._market_analysis import _build_market_output_language_line

    point_date = str(point.get("date") or "")
    try:
        parsed_day = datetime.fromisoformat(point_date).date()
    except ValueError:
        parsed_day = datetime.utcnow().date()
    company_daily_context: List[Dict[str, Any]] = []
    for shift in (-1, 0, 1):
        day = parsed_day + timedelta(days=shift)
        report = get_company_daily_report(
            company_name,
            target_date=day,
            provider_name="openai",
            prompt_style="simple",
        )
        if report:
            company_daily_context.append(report)
    week_start = parsed_day - timedelta(days=parsed_day.weekday())
    week_end = week_start + timedelta(days=6)
    weekly = get_news_report(company_name, beginning_date=week_start, end_date=week_end)
    market_news = _fetch_market_news(limit=20, target_date=parsed_day)
    market_sections, _, _ = _resolve_market_price_sections(target_date=parsed_day)
    language_line = _build_market_output_language_line(output_language)
    payload = {
        "company_name": company_name,
        "ticker": ticker,
        "range_key": range_key,
        "point": {
            "date": point.get("date"),
            "date_time": point.get("date_time"),
            "close": point.get("close"),
            "pct_change": point.get("pct_change"),
            "volume": point.get("volume"),
            "open": point.get("open"),
            "high": point.get("high"),
            "low": point.get("low"),
        },
        "company_daily_reports": company_daily_context,
        "company_weekly_report": weekly,
        "market_news": market_news,
        "market_snapshot": market_sections,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Explain why {company_name} ({ticker}) moved like this at the selected price point.\n"
        "Use company news, market news, broader market snapshot, and price/volume context.\n"
        "If evidence is weak, clearly say uncertainty and what is missing.\n"
        "Keep explanation practical and decision-useful.\n"
        f"{language_line}"
        f"Context JSON:\n{payload_json}\n"
    )


def _ensure_company_price_daily_schema() -> None:
    ensure_database_schema()


def _ensure_company_price_move_analysis_schema() -> None:
    ensure_database_schema()


def _get_company_price_move_analysis(
    *,
    company_name: str,
    ticker: str,
    range_key: str,
    point_date_time: str,
    provider: str,
    prompt_style: str,
    output_language: str,
) -> Optional[Dict[str, Any]]:
    _ensure_company_price_move_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, company_name, ticker, {COL_RANGE_KEY}, {COL_POINT_DATE_TIME},
                    point_label, close_price, pct_change, volume,
                    provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                    output_text, updated_at, created_at
                FROM {TBL_COMPANY_PRICE_MOVE_ANALYSIS}
                WHERE company_name = %s
                  AND ticker = %s
                  AND {COL_RANGE_KEY} = %s
                  AND {COL_POINT_DATE_TIME} = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (
                    company_name,
                    ticker,
                    range_key,
                    point_date_time,
                    provider,
                    prompt_style,
                    output_language,
                ),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "ticker": row["ticker"],
        "range_key": row[COL_RANGE_KEY],
        "point_date_time": row[COL_POINT_DATE_TIME].isoformat(),
        "point_label": row["point_label"],
        "close_price": row["close_price"],
        "pct_change": row["pct_change"],
        "volume": row["volume"],
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "output_text": row["output_text"],
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _upsert_company_price_move_analysis(
    *,
    company_name: str,
    ticker: str,
    range_key: str,
    point_date_time: str,
    point_label: str,
    close_price: Optional[float],
    pct_change: Optional[float],
    volume: Optional[int],
    provider: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
    output_text: str,
) -> Dict[str, Any]:
    _ensure_company_price_move_analysis_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TBL_COMPANY_PRICE_MOVE_ANALYSIS} (
                    company_name, ticker, {COL_RANGE_KEY}, {COL_POINT_DATE_TIME},
                    point_label, close_price, pct_change, volume,
                    provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                    input_payload, output_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    company_name, ticker, {COL_RANGE_KEY}, {COL_POINT_DATE_TIME},
                    provider, prompt_style, {COL_OUTPUT_LANGUAGE}
                )
                DO UPDATE SET
                    point_label = EXCLUDED.point_label,
                    close_price = EXCLUDED.close_price,
                    pct_change = EXCLUDED.pct_change,
                    volume = EXCLUDED.volume,
                    model = EXCLUDED.model,
                    input_payload = EXCLUDED.input_payload,
                    output_text = EXCLUDED.output_text,
                    updated_at = NOW()
                RETURNING
                    id, company_name, ticker, {COL_RANGE_KEY}, {COL_POINT_DATE_TIME},
                    point_label, close_price, pct_change, volume,
                    provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                    output_text, updated_at, created_at
                """,
                (
                    company_name,
                    ticker,
                    range_key,
                    point_date_time,
                    point_label,
                    close_price,
                    pct_change,
                    volume,
                    provider,
                    model,
                    prompt_style,
                    output_language,
                    json.dumps(input_payload, ensure_ascii=False),
                    output_text,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return {
        "id": int(row["id"]),
        "company_name": row["company_name"],
        "ticker": row["ticker"],
        "range_key": row[COL_RANGE_KEY],
        "point_date_time": row[COL_POINT_DATE_TIME].isoformat(),
        "point_label": row["point_label"],
        "close_price": row["close_price"],
        "pct_change": row["pct_change"],
        "volume": row["volume"],
        "provider": row["provider"],
        "model": row["model"],
        "prompt_style": row["prompt_style"],
        "output_language": row[COL_OUTPUT_LANGUAGE],
        "output_text": row["output_text"],
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _round_num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except Exception:
        return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None
