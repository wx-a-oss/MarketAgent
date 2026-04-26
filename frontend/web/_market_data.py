"""Market quotes, news, and trading-day logic.

Extracted from server.py — no logic changes.
"""
from __future__ import annotations

import html
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from frontend.common import StockFrontendClient

logger = logging.getLogger("uvicorn.error")

client = StockFrontendClient()

MARKET_INDEX_CONFIG: List[Tuple[str, List[str], str]] = [
    ("S&P 500 ETF", ["SPY"], "US"),
    ("Nasdaq 100 ETF", ["QQQ"], "US"),
    ("Dow Jones ETF", ["DIA"], "US"),
    ("Russell 2000 ETF", ["IWM"], "US"),
    ("UK ETF", ["EWU"], "UK"),
    ("Germany ETF", ["EWG"], "DE"),
    ("China ETF", ["MCHI"], "CN"),
    ("Hong Kong ETF", ["EWH"], "HK"),
    ("Korea ETF", ["EWY"], "KR"),
    ("Japan ETF", ["EWJ"], "JP"),
    ("Europe ETF", ["FEZ"], "EU"),
    ("India ETF", ["INDA"], "IN"),
    ("Taiwan ETF", ["EWT"], "TW"),
]

MARKET_BOND_CONFIG: List[Tuple[str, List[str]]] = [
    # Yield symbols first; ETF proxies as fallback.
    ("US 2Y Yield", ["US02Y", "US2Y", "SHY"]),
    ("US 10Y Yield", ["US10Y", "^TNX", "IEF"]),
    ("US 30Y Yield", ["US30Y", "^TYX", "TLT"]),
]

MARKET_COMMODITY_CONFIG: List[Tuple[str, List[str]]] = [
    ("Gold", ["OANDA:XAU_USD", "GLD"]),
    ("Silver", ["OANDA:XAG_USD", "SLV"]),
    ("WTI Crude", ["NYMEX:CL1!", "USO"]),
    ("Brent Crude", ["OANDA:BCO_USD", "BNO"]),
    ("US Oil Fund", ["USO"]),
    ("Copper", ["COMEX:HG1!", "CPER"]),
]

MARKET_CRYPTO_CONFIG: List[Tuple[str, List[str]]] = [
    ("Bitcoin", ["BINANCE:BTCUSDT", "COINBASE:BTC-USD", "BTCUSD", "BITO"]),
    ("Ethereum", ["BINANCE:ETHUSDT", "COINBASE:ETH-USD", "ETHUSD", "ETHA"]),
]

US_MARKET_TZ = ZoneInfo("America/New_York")


def _fetch_market_bucket(
    config: List[Tuple[str, List[str]]] | List[Tuple[str, List[str], str]]
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for entry in config:
        label = entry[0]
        symbols = entry[1]
        country_code = entry[2] if len(entry) >= 3 else None
        quote = _resolve_market_quote(symbols)
        quote["label"] = label
        if country_code:
            quote["country_code"] = country_code
        items.append(quote)
    return items


def _build_market_price_sections_live() -> List[Dict[str, Any]]:
    index_items = _fetch_market_bucket(MARKET_INDEX_CONFIG)
    return [
        {
            "key": "indexes",
            "label": "Indexes",
            "items": index_items,
        },
        {
            "key": "bonds",
            "label": "Bond Rates",
            "items": _fetch_market_bucket(MARKET_BOND_CONFIG),
        },
        {
            "key": "commodities",
            "label": "Commodities",
            "items": _fetch_market_bucket(MARKET_COMMODITY_CONFIG),
        },
        {
            "key": "crypto",
            "label": "Crypto (BTC, ETH)",
            "items": _fetch_market_bucket(MARKET_CRYPTO_CONFIG),
        },
    ]


def _fetch_yahoo_index_rss_bucket(
    config: List[Tuple[str, str, str]]
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for label, symbol, country_code in config:
        items.append(
            _fetch_yahoo_index_rss_item(
                label=label,
                symbol=symbol,
                country_code=country_code,
            )
        )
    return items


def _fetch_yahoo_index_rss_item(
    *,
    label: str,
    symbol: str,
    country_code: str,
) -> Dict[str, Any]:
    # Prefer real quote sources first; RSS is only for headline metadata.
    quote = _resolve_market_quote([symbol])
    if str(quote.get("close_price") or "").strip() in {"", "-", "\u2014"}:
        yahoo_quote = _fetch_yahoo_symbol_quote(symbol)
        if yahoo_quote:
            quote = yahoo_quote

    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?"
        + urllib.parse.urlencode({"s": symbol, "region": "US", "lang": "en-US"})
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    headline = ""
    link = ""
    dt_text = ""
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        root = ElementTree.fromstring(payload)
        first = root.find("./channel/item")
        if first is not None:
            headline = (first.findtext("title") or "").strip()
            link = (first.findtext("link") or "").strip()
            pub_date_raw = (first.findtext("pubDate") or "").strip()
            if pub_date_raw:
                try:
                    parsed = parsedate_to_datetime(pub_date_raw)
                    dt_text = parsed.strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    dt_text = ""
    except Exception:
        headline = ""
        link = ""
        dt_text = ""

    return {
        "symbol": str(quote.get("symbol") or symbol),
        "close_price": str(quote.get("close_price") or "\u2014"),
        "price_change_pct": str(quote.get("price_change_pct") or "\u2014"),
        "quote_timestamp": quote.get("quote_timestamp"),
        "label": label,
        "country_code": country_code,
        "headline": headline,
        "headline_url": link,
        "headline_time": dt_text,
    }


def _resolve_market_price_sections(*, target_date: date) -> tuple[List[Dict[str, Any]], str, bool]:
    # Look up via server module namespace so monkeypatch in tests works correctly.
    import frontend.web.server as _srv
    snapshot = _srv._get_market_price_snapshot(target_date)
    snapshot_exists = snapshot is not None
    today = datetime.now(US_MARKET_TZ).date()

    if target_date < today:
        if snapshot:
            return snapshot.get("sections", []), "snapshot", True
        settled = _latest_settled_us_market_date()
        if target_date == settled and _srv._is_us_trading_day(target_date):
            live_sections = _srv._build_market_price_sections_live()
            _srv._upsert_market_price_snapshot(target_date, {"sections": live_sections})
            return live_sections, "snapshot_backfilled_from_live", True
        return [], "snapshot_missing", False

    if _srv._is_us_market_open_now():
        return _srv._build_market_price_sections_live(), "live_market_hours", snapshot_exists

    if snapshot:
        return snapshot.get("sections", []), "snapshot", True

    live_sections = _srv._build_market_price_sections_live()
    if _srv._is_us_trading_day(target_date) and _srv._is_us_market_day_closed_now():
        _srv._upsert_market_price_snapshot(target_date, {"sections": live_sections})
        return live_sections, "live_persisted_snapshot", True
    return live_sections, "live", False


def _latest_settled_us_market_date() -> date:
    now = datetime.now(US_MARKET_TZ)
    if now.weekday() >= 5:
        # Weekend: latest settled day is Friday.
        days_back = now.weekday() - 4
        return (now - timedelta(days=days_back)).date()
    minutes = now.hour * 60 + now.minute
    market_open = 9 * 60 + 30
    market_close = 16 * 60
    if minutes < market_open:
        # Before open on a weekday: latest settled is previous trading day.
        prev = now - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev.date()
    if minutes >= market_close:
        # After close: today is settled.
        return now.date()
    # During market hours: latest settled is previous trading day.
    prev = now - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev.date()


def _previous_us_trading_day(day: date) -> date:
    dt = datetime.combine(day, datetime.min.time(), tzinfo=US_MARKET_TZ) - timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.date()


def _is_us_trading_day(day: date) -> bool:
    return day.weekday() < 5


def _is_us_market_open_now() -> bool:
    now = datetime.now(US_MARKET_TZ)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return (9 * 60 + 30) <= minutes <= (16 * 60)


def _is_us_market_day_closed_now() -> bool:
    now = datetime.now(US_MARKET_TZ)
    if now.weekday() >= 5:
        return True
    minutes = now.hour * 60 + now.minute
    return minutes > (16 * 60)


def _resolve_market_quote(symbols: List[str]) -> Dict[str, Any]:
    # Use direct Finnhub quote endpoint for broader symbol support (indexes, yields, crypto pairs).
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if api_key:
        for symbol in symbols:
            direct = _fetch_direct_finnhub_quote(symbol, api_key=api_key)
            if direct:
                return direct
    for symbol in symbols:
        try:
            snapshot = client.query(symbol, include_analysis=False)
            base = snapshot.base.as_dict()
            close_price = base.get("close_price")
            if close_price in (None, "", "-"):
                continue
            return {
                "symbol": symbol,
                "close_price": str(close_price),
                "price_change_pct": str(base.get("price_change_pct", "\u2014")),
                "quote_timestamp": base.get("quote_timestamp"),
            }
        except Exception:
            continue
    return {
        "symbol": symbols[0] if symbols else "",
        "close_price": "\u2014",
        "price_change_pct": "\u2014",
        "quote_timestamp": None,
    }


def _fetch_market_news(
    limit: Optional[int] = None,
    *,
    target_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    per_source_limit = limit if limit is not None else 200
    merged.extend(
        _fetch_finnhub_market_news(
            limit=per_source_limit,
            target_date=target_date,
        )
    )
    merged.extend(
        _fetch_yahoo_rss_market_news(
            limit=per_source_limit,
            target_date=target_date,
        )
    )
    if not merged:
        return []
    # Dedupe by URL first, fallback to title.
    deduped: List[Dict[str, Any]] = []
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    for item in merged:
        url = str(item.get("url") or "").strip().lower()
        title = str(item.get("headline") or "").strip().lower()
        if url and url in seen_url:
            continue
        if not url and title and title in seen_title:
            continue
        if url:
            seen_url.add(url)
        if title:
            seen_title.add(title)
        normalized_tag = _normalize_market_news_tag(item)
        item["source_tag"] = normalized_tag
        deduped.append(item)
    # Keep most recent first when datetime_text not parseable just preserve source order.
    return deduped[:limit] if limit is not None else deduped


def _normalize_market_news_tag(item: Dict[str, Any]) -> str:
    raw_tag = str(item.get("source_tag") or "").strip().lower()
    source = str(item.get("source") or "").strip().lower()
    url = str(item.get("url") or "").strip().lower()
    combined = " ".join(part for part in (raw_tag, source, url) if part)
    if "yahoo" in combined:
        return "yahoo"
    if "finnhub" in combined:
        return "finnhub"
    return ""


def _fetch_finnhub_market_news(
    limit: int = 12,
    *,
    target_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return []
    url = (
        "https://finnhub.io/api/v1/news?"
        + urllib.parse.urlencode({"category": "general", "token": api_key})
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    target = target_date or datetime.now().date()
    selected_items: List[Dict[str, Any]] = []
    fallback_items: List[Dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("headline") or "").strip()
        source = str(row.get("source") or "").strip()
        link = str(row.get("url") or "").strip()
        dt_value = row.get("datetime")
        if not headline or not link:
            continue
        dt_text = ""
        try:
            if dt_value:
                dt = datetime.fromtimestamp(int(dt_value))
                dt_text = dt.strftime("%b %d, %Y %I:%M %p")
        except Exception:
            dt_text = ""
        item_payload = {
            "headline": headline,
            "source": source,
            "source_tag": "finnhub",
            "url": link,
            "datetime_text": dt_text,
            "summary": str(row.get("summary") or "").strip(),
        }
        fallback_items.append(item_payload)
        if dt_value:
            try:
                dt = datetime.fromtimestamp(int(dt_value))
                if dt.date() == target:
                    selected_items.append(item_payload)
            except Exception:
                pass
        if target_date is None:
            if len(fallback_items) >= limit * 2:
                break
        elif len(selected_items) >= limit:
            break
    if target_date is None:
        items = selected_items if selected_items else fallback_items
        return items[:limit]
    return selected_items[:limit]


def _fetch_yahoo_rss_market_news(
    limit: int = 12,
    *,
    target_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    url = "https://news.yahoo.com/rss/finance"
    request = urllib.request.Request(
        url,
        headers={
            # Yahoo RSS often blocks default urllib user-agent with 429.
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        root = ElementTree.fromstring(payload)
    except Exception:
        return []
    target = target_date or datetime.now().date()
    selected_items: List[Dict[str, Any]] = []
    fallback_items: List[Dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = html.unescape((item.findtext("description") or "").strip())
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        source_text = (item.findtext("source") or "").strip() or "Yahoo Finance"
        if not title or not link:
            continue
        dt_text = ""
        try:
            if pub_date_raw:
                parsed = parsedate_to_datetime(pub_date_raw)
                dt_text = parsed.strftime("%b %d, %Y %I:%M %p")
        except Exception:
            dt_text = ""
        item_payload = {
            "headline": title,
            "source": source_text,
            "source_tag": "yahoo",
            "url": link,
            "datetime_text": dt_text,
            "summary": description,
        }
        fallback_items.append(item_payload)
        if pub_date_raw:
            try:
                parsed = parsedate_to_datetime(pub_date_raw)
                if parsed.date() == target:
                    selected_items.append(item_payload)
            except Exception:
                pass
        if target_date is None:
            if len(fallback_items) >= limit * 2:
                break
        elif len(selected_items) >= limit:
            break
    if target_date is None:
        items = selected_items if selected_items else fallback_items
        return items[:limit]
    return selected_items[:limit]


def _fetch_direct_finnhub_quote(symbol: str, *, api_key: str) -> Optional[Dict[str, Any]]:
    url = (
        "https://finnhub.io/api/v1/quote?"
        + urllib.parse.urlencode({"symbol": symbol, "token": api_key})
    )
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    current = payload.get("c")
    if current in (None, 0):
        return None
    prev_close = payload.get("pc")
    pct = None
    try:
        if prev_close not in (None, 0):
            pct = ((float(current) - float(prev_close)) / float(prev_close)) * 100.0
    except Exception:
        pct = None
    pct_text = f"{pct:+.2f}%" if pct is not None else "\u2014"
    return {
        "symbol": symbol,
        "close_price": f"{float(current):.2f}",
        "price_change_pct": pct_text,
        "quote_timestamp": payload.get("t"),
    }


def _fetch_yahoo_symbol_quote(symbol: str) -> Optional[Dict[str, Any]]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?"
        + urllib.parse.urlencode(
            {
                "interval": "1d",
                "range": "5d",
                "includeAdjustedClose": "false",
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
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results:
        return None
    result = results[0] or {}
    meta = result.get("meta") if isinstance(result, dict) else {}
    indicators = result.get("indicators") if isinstance(result, dict) else {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else []
    quote = quotes[0] if isinstance(quotes, list) and quotes else {}
    closes = quote.get("close") if isinstance(quote, dict) else []
    timestamps = result.get("timestamp") if isinstance(result, dict) else []
    if not isinstance(closes, list):
        closes = []
    if not isinstance(timestamps, list):
        timestamps = []

    valid_closes: List[float] = []
    for value in closes:
        try:
            if value is None:
                continue
            valid_closes.append(float(value))
        except Exception:
            continue
    if not valid_closes:
        return None

    latest = valid_closes[-1]
    previous = valid_closes[-2] if len(valid_closes) >= 2 else None
    if previous in (None, 0):
        prev_close_meta = meta.get("previousClose") if isinstance(meta, dict) else None
        try:
            previous = float(prev_close_meta) if prev_close_meta not in (None, 0, "") else None
        except Exception:
            previous = None

    pct_text = "\u2014"
    if previous not in (None, 0):
        try:
            pct = ((latest - float(previous)) / float(previous)) * 100.0
            pct_text = f"{pct:+.2f}%"
        except Exception:
            pct_text = "\u2014"

    quote_ts = None
    if timestamps:
        try:
            quote_ts = int(timestamps[-1])
        except Exception:
            quote_ts = None

    return {
        "symbol": str(meta.get("symbol") or symbol),
        "close_price": f"{latest:.2f}",
        "price_change_pct": pct_text,
        "quote_timestamp": quote_ts,
    }


# --- Snapshot DB helpers used by _resolve_market_price_sections ---
# These are imported from _market_analysis.py at the function level to avoid
# circular imports. They are re-exported here so callers within this module work.

def _get_market_price_snapshot(snapshot_date: date) -> Optional[Dict[str, Any]]:
    from frontend.web._market_analysis import _get_market_price_snapshot as _impl
    return _impl(snapshot_date)


def _upsert_market_price_snapshot(snapshot_date: date, payload: Dict[str, Any]) -> None:
    from frontend.web._market_analysis import _upsert_market_price_snapshot as _impl
    _impl(snapshot_date, payload)
