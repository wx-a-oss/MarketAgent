from __future__ import annotations

import re
import json
import os
import html
import time as pytime
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

from market_agent.analysis.company.news.db import ensure_database_schema, get_connection
from market_agent.config.models import DEFAULT_OPENAI_MODEL, DEFAULT_PROVIDER_MODELS, get_default_model
from frontend.common import StockFrontendClient
from market_agent.app import market_updates as market_updates_module
from frontend.web.calendar_page import render_calendar_page
from frontend.web.company_detail_page import render_company_detail_page
from frontend.web.company_page import render_company_page
from frontend.web.crypto_page import render_crypto_page
from frontend.web.global_page import render_global_page
from frontend.web.market_page import render_market_page
from frontend.web.notes_page import render_notes_page
from frontend.web.person_page import render_person_page
from frontend.web.shared_page import render_nav
from market_agent.app import (
    attach_news_to_market_story,
    create_market_story_from_news,
    generate_market_daily_report,
    get_market_daily_news_overview,
    get_market_story_overview,
    list_market_daily_clusters,
    list_company_earnings,
    list_market_macro_events,
    refresh_market_story_backlog,
    refresh_company_earnings,
    refresh_market_daily_clusters,
    refresh_market_macro_events,
    run_market_daily_update,
    start_market_story_warmup,
    update_market_story_priority,
    update_market_story_status,
    get_company_story_overview,
    rebuild_company_warmup,
    run_company_daily_update,
    start_company_daily_update,
    start_company_story_warmup,
)
from market_agent.analysis.company.news import (
    add_company_to_watchlist,
    delete_company_news,
    generate_weekly_report,
    generate_company_daily_report,
    generate_company_price_intelligence_run,
    generate_company_status_snapshot,
    get_company_news,
    list_company_daily_clusters,
    get_company_story_state,
    list_company_story_qa,
    list_company_price_intelligence_runs,
    list_company_story_updates,
    get_company_daily_report,
    get_company_profile,
    get_company_price_intelligence_run,
    get_company_status_snapshot,
    get_company_story_warmup_state,
    get_news_report,
    list_watchlist_company_rows,
    ensure_company_profile,
    filter_company_news_day,
    filter_company_news_item,
    refresh_company_daily_clusters,
    refresh_company_news_for_range,
    refresh_company_news_if_needed,
    remove_company_from_watchlist,
    set_company_ticker,
    ask_company_story_question,
    attach_news_to_company_story,
    create_company_story_from_news,
    create_user_note,
    merge_company_story_qa_answer,
    invalidate_user_note,
    summarize_company_news_day,
    summarize_company_news_item,
    update_company_story_priority,
    update_company_story_status,
    update_user_note,
    list_user_notes,
    list_user_note_tags,
)
from market_agent.app.background_jobs import (
    JobTracker,
    create_job,
    find_latest_job,
    get_job,
    mark_interrupted_jobs,
    run_job_async,
)
from market_agent.analysis import analyze_single_stock_sections
from market_agent.llms.news.registry import list_news_models
from market_agent.llms.openai import chat_completion
from market_agent.llms.registry import get_provider, list_models
from market_agent.schema_fields import (
    COL_HEADLINE,
    COL_EVENT_DATE_TIME,
    COL_INPUT_PAYLOAD,
    COL_MODEL,
    COL_NEWS_SOURCES,
    COL_NEWS_DATE,
    COL_NEWS_URL,
    COL_OUTPUT_LANGUAGE,
    COL_OUTPUT_TEXT,
    COL_PROMPT_STYLE,
    COL_PROVIDER,
    COL_PAYLOAD,
    COL_SNAPSHOT_DATE,
    COL_SOURCE,
    COL_SOURCE_TAG,
    COL_RANGE_KEY,
    COL_POINT_DATE_TIME,
    COL_TICKER,
    COL_TRADE_DATE,
    TBL_MARKET_NEWS_DAILY_SUMMARY,
    TBL_MARKET_NEWS_ITEM_ANALYSIS,
    TBL_MARKET_PRICE_DAILY_SNAPSHOT,
    TBL_MARKET_NEWS_RAW,
    TBL_MARKET_STORY_STATE,
    TBL_MARKET_STORY_UPDATE,
    TBL_MARKET_STORY_WARMUP_STATE,
    TBL_MARKET_STORY_EVENT,
    TBL_COMPANY_EARNINGS_EVENT,
    TBL_MARKET_MACRO_EVENT,
    TBL_COMPANY_PRICE_MOVE_ANALYSIS,
    TBL_COMPANY_PRICE_DAILY,
)

app = FastAPI(
    title="MarketAgent Web Frontend",
    description="Lightweight HTML frontend powered by the shared MarketAgent stock API.",
)
mark_interrupted_jobs()

client = StockFrontendClient()

MARKET_INDEX_CONFIG: List[Tuple[str, List[str], str]] = [
    ("S&P 500 ETF", ["SPY"], "US"),
    ("Nasdaq 100 ETF", ["QQQ"], "US"),
    ("Dow Jones ETF", ["DIA"], "US"),
    ("Russell 2000 ETF", ["IWM"], "US"),
    ("China ETF", ["MCHI"], "CN"),
    ("Korea ETF", ["EWY"], "KR"),
    ("Japan ETF", ["EWJ"], "JP"),
    ("Europe ETF", ["FEZ"], "EU"),
]


def _safe_job(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not job:
        return None
    return {
        "job_id": job.get("job_id"),
        "job_type": job.get("job_type"),
        "job_key": job.get("job_key"),
        "status": job.get("status"),
        "current_stage": job.get("current_stage"),
        "elapsed_sec": job.get("elapsed_sec"),
        "result_summary": job.get("result_summary"),
        "error_text": job.get("error_text"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "updated_at": job.get("updated_at"),
        "provider": job.get("provider"),
        "model": job.get("model"),
        "output_language": job.get("output_language"),
        "prompt_style": job.get("prompt_style"),
        "target_entity": job.get("target_entity"),
        "target_date": job.get("target_date"),
        "window_start": job.get("window_start"),
        "window_end": job.get("window_end"),
        "input_char_count": job.get("input_char_count", 0),
        "input_item_count": job.get("input_item_count", 0),
        "output_char_count": job.get("output_char_count", 0),
        "metrics": job.get("metrics_json") or {},
        "final_counts": job.get("final_counts") or {},
        "stage_history": job.get("stage_history") or [],
    }


def _job_key(*parts: Any) -> str:
    normalized: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        normalized.append(text.lower())
    return "|".join(normalized)


def _start_background_job(
    *,
    job_type: str,
    job_key: str,
    provider: str = "",
    model: str = "",
    output_language: str = "",
    prompt_style: str = "",
    target_entity: str = "",
    target_date: Optional[date] = None,
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
    metadata: Optional[Dict[str, Any]] = None,
    worker: Any,
) -> Dict[str, Any]:
    created = create_job(
        job_type=job_type,
        job_key=job_key,
        provider=provider,
        model=model,
        output_language=output_language,
        prompt_style=prompt_style,
        target_entity=target_entity,
        target_date=target_date,
        window_start=window_start,
        window_end=window_end,
        metadata=metadata or {},
    )
    job = created.get("job") or {}
    if created.get("mode") == "started":
        run_job_async(int(job["job_id"]), worker)
    return {"mode": created.get("mode"), "job": _safe_job(job)}


def _wait_for_company_warmup(
    tracker: JobTracker,
    *,
    company_name: str,
    provider_name: str,
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    last_stage = ""
    while True:
        state = get_company_story_warmup_state(
            company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        stage = str(state.get("current_stage") or "idle")
        job_state = str(state.get("job_state") or "not_started")
        metrics = {
            "warmup_state": job_state,
            "warmup_stage": stage,
            "raw_fetched_count": int(state.get("raw_fetched_count") or 0),
            "raw_stored_count": int(state.get("raw_stored_count") or 0),
            "filtered_kept_count": int(state.get("filtered_kept_count") or 0),
            "ongoing_story_count": int(state.get("ongoing_story_count") or 0),
            "finished_story_count": int(state.get("finished_story_count") or 0),
        }
        if stage != last_stage:
            tracker.mark_running(stage or "idle", metrics=metrics)
            last_stage = stage
        else:
            tracker.update(stage=stage or "idle", metrics=metrics, counts=metrics)
        if job_state in {"completed", "failed", "partial"}:
            return state
        pytime.sleep(2.0)


def _run_market_daily_news_job(
    tracker: JobTracker,
    *,
    target_date: date,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    force_fetch: bool,
) -> Dict[str, Any]:
    current = get_market_daily_news_overview(
        target_date=target_date,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    today = datetime.now().date()
    has_existing_raw = bool(current.get("raw_news"))
    refresh_stats: Dict[str, Any]
    if target_date < today and has_existing_raw:
        refresh_stats = {
            "mode": "reuse_existing_raw_past_date",
            "fetched_total": 0,
            "stored_total": 0,
            "reused_existing_raw": True,
        }
    elif force_fetch or not has_existing_raw:
        tracker.mark_running("fetching_raw", metrics={"target_date": target_date.isoformat()})
        refresh_stats = market_updates_module.refresh_market_news_for_range(start_date=target_date, end_date=target_date)
    else:
        refresh_stats = {
            "mode": "reuse_existing_raw",
            "fetched_total": 0,
            "stored_total": 0,
            "reused_existing_raw": True,
        }
    tracker.mark_running("generating_report")
    daily_report_stats = generate_market_daily_report(
        target_date=target_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    tracker.mark_running("building_clusters")
    cluster_stats = refresh_market_daily_clusters(
        target_date=target_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {
        "result_summary": f"Daily news updated for {target_date.isoformat()}",
        "metrics": {
            "refresh_mode": refresh_stats.get("mode", ""),
            "target_date": target_date.isoformat(),
            "provider": provider_name,
            "model": model,
        },
        "counts": {
            "fetched_total": int(refresh_stats.get("fetched_total", 0) or 0),
            "stored_total": int(refresh_stats.get("stored_total", 0) or 0),
            "report_count": int(daily_report_stats.get("report_count", 0) or 0),
            "cluster_count": int(cluster_stats.get("cluster_count", 0) or 0),
            "reused_existing_raw": bool(refresh_stats.get("reused_existing_raw", False)),
        },
        "input_char_count": int(daily_report_stats.get("prompt_char_count", 0) or 0) + int(cluster_stats.get("prompt_char_count", 0) or 0),
        "input_item_count": int(daily_report_stats.get("input_item_count", 0) or 0) + int(cluster_stats.get("input_item_count", 0) or 0),
        "output_char_count": int(daily_report_stats.get("output_char_count", 0) or 0) + int(cluster_stats.get("output_char_count", 0) or 0),
    }


def _run_market_story_backlog_job(
    tracker: JobTracker,
    *,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    tracker.mark_running("routing_backlog")
    stats = refresh_market_story_backlog(
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if stats.get("no_op"):
        return {
            "result_summary": "No newer stored market clusters to route.",
            "metrics": {"no_op": True},
            "counts": stats,
            "input_char_count": int(stats.get("prompt_char_count", 0) or 0),
            "input_item_count": int(stats.get("input_item_count", 0) or 0),
            "output_char_count": int(stats.get("output_char_count", 0) or 0),
        }
    return {
        "result_summary": f"Market stories updated through {stats.get('last_backlog_date') or ''}",
        "metrics": {
            "first_backlog_date": stats.get("first_backlog_date", ""),
            "last_backlog_date": stats.get("last_backlog_date", ""),
        },
        "counts": stats,
        "input_char_count": int(stats.get("prompt_char_count", 0) or 0),
        "input_item_count": int(stats.get("input_item_count", 0) or 0),
        "output_char_count": int(stats.get("output_char_count", 0) or 0),
    }


def _run_market_macro_refresh_job(
    tracker: JobTracker,
    *,
    provider_name: str,
    model: str,
    output_language: str,
) -> Dict[str, Any]:
    tracker.mark_running("refreshing_calendar")
    stats = refresh_market_macro_events(
        provider_name=provider_name,
        model=model,
        output_language=output_language,
        extend_window=True,
    )
    return {
        "result_summary": "Calendar refreshed for the next 3 months.",
        "metrics": {
            "window_start": stats.get("window_start", ""),
            "window_end": stats.get("window_end", ""),
        },
        "counts": {
            "updated": int(stats.get("updated", 0) or 0),
            "event_count": int(stats.get("event_count", 0) or 0),
        },
        "input_item_count": int(stats.get("input_item_count", 0) or 0),
        "output_char_count": int(stats.get("output_char_count", 0) or 0),
    }


def _run_company_story_update_job(
    tracker: JobTracker,
    *,
    company_name: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    window_days: int,
) -> Dict[str, Any]:
    tracker.mark_running("running_update")
    result = run_company_daily_update(
        company_name,
        target_date=datetime.now().date(),
        source_name="finnhub",
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        story_window_days=window_days,
    )
    if str(result.get("mode") or "") == "warmup_started":
        state = _wait_for_company_warmup(
            tracker,
            company_name=company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        return {
            "result_summary": f"Company warm-up {state.get('job_state') or 'completed'}.",
            "metrics": {"mode": "warmup_started"},
            "counts": {
                "raw_fetched_count": int(state.get("raw_fetched_count", 0) or 0),
                "raw_stored_count": int(state.get("raw_stored_count", 0) or 0),
                "filtered_kept_count": int(state.get("filtered_kept_count", 0) or 0),
                "ongoing_story_count": int(state.get("ongoing_story_count", 0) or 0),
                "finished_story_count": int(state.get("finished_story_count", 0) or 0),
            },
        }
    return {
        "result_summary": f"Stories updated for {company_name}.",
        "metrics": {"mode": result.get("mode", "")},
        "counts": {
            "fetched_total": int((result.get("refresh_stats") or {}).get("fetched_total", 0) or 0),
            "stored_total": int((result.get("refresh_stats") or {}).get("stored_total", 0) or 0),
            "report_count": int((result.get("daily_report_stats") or {}).get("report_count", 0) or 0),
            "cluster_count": int((result.get("cluster_stats") or {}).get("cluster_count", 0) or 0),
            "updated_story_count": int((result.get("story_stats") or {}).get("updated_story_count", 0) or 0),
            "new_story_count": int((result.get("story_stats") or {}).get("new_story_count", 0) or 0),
        },
    }


def _run_company_rebuild_warmup_job(
    tracker: JobTracker,
    *,
    company_name: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
) -> Dict[str, Any]:
    tracker.mark_running("starting_rebuild")
    rebuild_company_warmup(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    state = _wait_for_company_warmup(
        tracker,
        company_name=company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {
        "result_summary": f"Warm-up {state.get('job_state') or 'completed'} for {company_name}.",
        "counts": {
            "raw_fetched_count": int(state.get("raw_fetched_count", 0) or 0),
            "raw_stored_count": int(state.get("raw_stored_count", 0) or 0),
            "filtered_kept_count": int(state.get("filtered_kept_count", 0) or 0),
            "ongoing_story_count": int(state.get("ongoing_story_count", 0) or 0),
            "finished_story_count": int(state.get("finished_story_count", 0) or 0),
        },
    }


def _run_price_intelligence_job(
    tracker: JobTracker,
    *,
    company_name: str,
    provider_name: str,
    model: str,
    output_language: str,
) -> Dict[str, Any]:
    tracker.mark_running("building_price_intelligence")
    stats = generate_company_price_intelligence_run(
        company_name,
        provider_name=provider_name,
        model=model,
        output_language=output_language,
    )
    return {
        "result_summary": f"Price intelligence generated for {company_name}.",
        "counts": {
            "daily_report_count": int(stats.get("daily_report_count", 0) or 0),
            "raw_news_count": int(stats.get("raw_news_count", 0) or 0),
            "run_id": int(stats.get("run_id", 0) or 0),
        },
        "input_char_count": int(stats.get("prompt_char_count", 0) or 0),
        "input_item_count": int(stats.get("input_item_count", 0) or 0),
        "output_char_count": int(stats.get("output_char_count", 0) or 0),
        "metrics": {"elapsed_sec": float(stats.get("elapsed_sec", 0.0) or 0.0)},
    }


def _run_detailed_report_job(
    tracker: JobTracker,
    *,
    company_name: str,
    provider_name: str,
    model: str,
    output_language: str,
    window_days: int,
) -> Dict[str, Any]:
    tracker.mark_running("building_detailed_report")
    stats = generate_company_status_snapshot(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style="simple",
        output_language=output_language,
        window_days=window_days,
        timeout_sec=240,
    )
    return {
        "result_summary": f"Detailed report generated for {company_name}.",
        "counts": {
            "daily_report_count": int(stats.get("daily_report_count", 0) or 0),
            "raw_news_count": int(stats.get("raw_news_count", 0) or 0),
        },
        "input_char_count": int(stats.get("prompt_char_count", 0) or 0),
        "input_item_count": int(stats.get("input_item_count", 0) or 0),
        "output_char_count": int(stats.get("output_char_count", 0) or 0),
        "metrics": {"elapsed_sec": float(stats.get("elapsed_sec", 0.0) or 0.0)},
    }

MARKET_BOND_CONFIG: List[Tuple[str, List[str]]] = [
    # Yield symbols first; ETF proxies as fallback.
    ("US 2Y Yield", ["US02Y", "US2Y", "SHY"]),
    ("US 10Y Yield", ["US10Y", "^TNX", "IEF"]),
    ("US 30Y Yield", ["US30Y", "^TYX", "TLT"]),
]

MARKET_COMMODITY_CONFIG: List[Tuple[str, List[str]]] = [
    ("Gold", ["OANDA:XAU_USD", "GLD"]),
    ("Silver", ["OANDA:XAG_USD", "SLV"]),
    ("Crude Oil", ["OANDA:BCO_USD", "USO"]),
]

MARKET_CRYPTO_CONFIG: List[Tuple[str, List[str]]] = [
    ("Bitcoin", ["BINANCE:BTCUSDT", "COINBASE:BTC-USD", "BTCUSD", "BITO"]),
    ("Ethereum", ["BINANCE:ETHUSDT", "COINBASE:ETH-USD", "ETHUSD", "ETHA"]),
]

MARKET_SUMMARY_DEFAULT_MODEL = dict(DEFAULT_PROVIDER_MODELS)

US_MARKET_TZ = ZoneInfo("America/New_York")


@app.post("/analysis")
async def analyze(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    symbols = payload.get("symbols") or []
    model = payload.get("model") or "gpt-4o-mini"
    provider_name = payload.get("provider") or "openai"
    if not isinstance(symbols, list):
        return {"error": "symbols must be a list"}

    results: Dict[str, Any] = {}
    provider = get_provider(provider_name, model=model)
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        snapshot = client.query(symbol)
        results[symbol] = analyze_single_stock_sections(
            snapshot,
            provider=provider,
        )
    return {"provider": provider_name, "model": model, "results": results}


@app.get("/", response_class=HTMLResponse)
async def index(
    symbol: Optional[str] = Query(
        None, description="Ticker symbols to query (e.g. AAPL, MSFT)"
    ),
) -> str:
    symbol_value = (symbol or "").strip().upper()
    symbols = [item.strip().upper() for item in symbol_value.split(",") if item.strip()]
    error_message = None
    stocks: List[Tuple[str, Optional[Dict[str, object]], Optional[Any]]] = []
    missing_symbols: List[str] = []
    if symbols:
        for item in symbols:
            try:
                snapshot = client.query(item)
                data = snapshot.base.as_dict()
                if len(data) <= 1:
                    missing_symbols.append(item)
                stocks.append((item, data, snapshot))
            except Exception as exc:
                error_message = str(exc)
                stocks.append((item, None, None))

    valid_stocks = [
        (symbol, data, snapshot)
        for symbol, data, snapshot in stocks
        if data is not None and len(data) > 1 and snapshot is not None
    ]
    sections_html = (
        _render_comparison_sections(valid_stocks)
        if valid_stocks
        else ""
    )

    base_section = (
        f"""
            {sections_html}
        """
        if stocks
        else """
            <section class="card">
                <h2>Indicators</h2>
                <p class="muted">Add a stock using the + button to fetch indicators.</p>
            </section>
        """
    )

    return f"""
        <html>
            <head>
                <title>MarketAgent – Stock Indicators</title>
                <style>
                    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap");
                    body {{ font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                                        "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
                           margin: 2rem; background: #f5f5f5; line-height: 1.65; color: #111; }}
                    nav {{ background: white; border-radius: 0.75rem; padding: 0.75rem 1.25rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); max-width: 960px; margin: 0 auto 1.5rem; }}
                    nav a {{ margin-right: 1rem; text-decoration: none; color: #1f2937; font-weight: 600; font-size: 0.95rem; letter-spacing: 0.01em; }}
                    nav a.active {{ color: #2563eb; }}
                    .container {{ max-width: 960px; margin: 0 auto; padding: 0 1rem; display: grid; gap: 1.5rem; }}
                    .card {{ background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
                    h1, h2 {{ margin-top: 0; }}
                    .comparison-wrap {{ overflow-x: auto; }}
                    .comparison-wrap::-webkit-scrollbar {{ height: 8px; }}
                    .comparison-wrap::-webkit-scrollbar-thumb {{ background: #e2e8f0; border-radius: 999px; }}
                    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
                    .comparison-table {{ width: max-content; min-width: 100%; }}
                    .comparison-table th:first-child,
                    .comparison-table td:first-child {{
                        border-right: 2px solid #e5e7eb;
                        padding-right: 0;
                        background: #f8fafc;
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }}
                    .comparison-table th, .comparison-table td {{
                        overflow-wrap: anywhere;
                        word-break: break-word;
                        white-space: normal;
                        vertical-align: top;
                    }}
                    .comparison-table td {{ padding-left: 0.5rem; }}
                    .comparison-wrap .comparison-table {{ margin: 0 auto; }}
                    th, td {{ padding: 0.4rem 0.35rem; text-align: left; border-bottom: 1px solid #eee; line-height: 1.65; }}
                    th {{ width: 40%; color: #555; }}
                    .muted {{ color: #888; }}
                    form {{ display: flex; gap: 0.5rem; }}
                    input[type="text"] {{ flex: 1; padding: 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }}
                    button {{ padding: 0.65rem 1.2rem; border: none; border-radius: 0.5rem; background: #2563eb; color: white; cursor: pointer; }}
                    button:hover {{ background: #1d4ed8; }}
                    label {{ display: flex; align-items: center; gap: 0.5rem; }}
                    #symbol-list {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }}
                    .chip {{ display: inline-flex; align-items: center; gap: 0.35rem; background: #eef2ff; color: #1e3a8a; padding: 0.3rem 0.6rem; border-radius: 999px; font-size: 0.9rem; }}
                    .chip .remove {{
                        background: #fee2e2;
                        color: #b91c1c;
                        border: 1px solid #fecaca;
                        border-radius: 999px;
                        cursor: pointer;
                        font-size: 0.72rem;
                        font-weight: 700;
                        padding: 0.12rem 0.42rem;
                        line-height: 1.1;
                    }}
                    .chip .remove:hover {{ background: #fecaca; color: #991b1b; }}
                    #add-symbol {{ width: 3rem; padding: 0.65rem 0; font-weight: bold; }}
                    .analysis-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-top: 1rem; }}
                    .analysis-card {{ border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 0.75rem; background: #f9fafb; }}
                    .analysis-card h3 {{ margin: 0 0 0.5rem; font-size: 1rem; }}
                    .analysis-card ul {{ padding-left: 1.1rem; margin: 0.35rem 0; }}
                    .analysis-controls {{ display: flex; gap: 0.5rem; align-items: center; margin-top: 0.75rem; flex-wrap: wrap; }}
                    select {{ padding: 0.5rem 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }}
                    #analyze-button {{ background: #16a34a; }}
                    #analyze-button:hover {{ background: #15803d; }}
                    #analysis-status {{ color: #666; font-size: 0.9rem; }}
                </style>
            </head>
            <body class="report">
                {render_nav("stock")}
                <div class="container">
                    <section class="card">
                        <h1>Stock Ticker</h1>
                        <form method="get">
                            <input type="text" id="symbol-input" value="" placeholder="Add ticker (e.g. AAPL)" />
                            <button type="button" id="add-symbol">+</button>
                        </form>
                        <div id="symbol-list" data-symbols="{symbol_value}"></div>
                        <div class="analysis-controls">
                            <label for="model-select">Model</label>
                            <select id="model-select">
                                {''.join(f'<option value="{model}">{model}</option>' for model in list_models().get("openai", []))}
                            </select>
                            <button type="button" id="analyze-button">Generate Analysis</button>
                            <span id="analysis-status"></span>
                        </div>
                    </section>
                    {f'<section class="card"><p class="muted">Note: {error_message}</p></section>' if error_message else ''}
                    {f'<section class="card"><p class="muted">Ticker not found: {", ".join(missing_symbols)}</p></section>' if missing_symbols else ''}
                    {base_section}
                </div>
                <script>
                    const listContainer = document.getElementById("symbol-list");
                    const input = document.getElementById("symbol-input");
                    const addButton = document.getElementById("add-symbol");
                    const analyzeButton = document.getElementById("analyze-button");
                    const modelSelect = document.getElementById("model-select");
                    const analysisStatus = document.getElementById("analysis-status");
                    const symbols = (listContainer.dataset.symbols || "")
                        .split(",")
                        .map((item) => item.trim().toUpperCase())
                        .filter((item) => item);

                    function renderList() {{
                        if (!symbols.length) {{
                            listContainer.innerHTML = '<p class="muted">No stocks selected yet.</p>';
                            return;
                        }}
                        listContainer.innerHTML = symbols
                            .map(
                                (symbol) =>
                                    `<span class="chip">${{symbol}}<button class="remove" data-symbol="${{symbol}}" aria-label="Remove ${{symbol}}">Remove</button></span>`
                            )
                            .join("");
                        listContainer.querySelectorAll("button.remove").forEach((button) => {{
                            button.addEventListener("click", () => {{
                                const symbol = button.dataset.symbol;
                                const index = symbols.indexOf(symbol);
                                if (index >= 0) {{
                                    symbols.splice(index, 1);
                                    updateQuery();
                                }}
                            }});
                        }});
                    }}

                    function updateQuery() {{
                        const next = symbols.join(",");
                        const url = new URL(window.location.href);
                        if (next) {{
                            url.searchParams.set("symbol", next);
                        }} else {{
                            url.searchParams.delete("symbol");
                        }}
                        window.location.href = url.toString();
                    }}

                    addButton.addEventListener("click", () => {{
                        const raw = input.value.trim();
                        if (!raw) {{
                            return;
                        }}
                        raw.split(",").forEach((value) => {{
                            const symbol = value.trim().toUpperCase();
                            if (symbol && !symbols.includes(symbol)) {{
                                symbols.push(symbol);
                            }}
                        }});
                        input.value = "";
                        updateQuery();
                    }});

                    input.addEventListener("keydown", (event) => {{
                        if (event.key === "Enter") {{
                            event.preventDefault();
                            addButton.click();
                        }}
                    }});

                    if (analyzeButton) {{
                        analyzeButton.addEventListener("click", async () => {{
                            if (!symbols.length) {{
                                return;
                            }}
                            analysisStatus.textContent = "Running analysis...";
                            try {{
                                const response = await fetch("/analysis", {{
                                    method: "POST",
                                    headers: {{
                                        "Content-Type": "application/json",
                                    }},
                                    body: JSON.stringify({{
                                        symbols: symbols,
                                        model: modelSelect ? modelSelect.value : "gpt-4o-mini",
                                    }}),
                                }});
                                if (!response.ok) {{
                                    throw new Error(`Analysis failed: ${{response.status}}`);
                                }}
                                const payload = await response.json();
                                renderAnalysis(payload);
                                analysisStatus.textContent = "Analysis complete.";
                            }} catch (error) {{
                                analysisStatus.textContent = "Analysis failed.";
                                console.error(error);
                            }}
                        }});
                    }}

                    renderList();
                
                    function renderAnalysis(payload) {{
                        const results = payload.results || {{}};
                        document.querySelectorAll("[data-analysis-section]").forEach((node) => {{
                            const section = node.dataset.analysisSection;
                            const cards = [];
                            Object.entries(results).forEach(([symbol, analysis]) => {{
                                const sectionResult = analysis.sections?.[section];
                                if (!sectionResult) {{
                                    return;
                                }}
                                cards.push(`
                                    <div class="analysis-card">
                                        <h3>${{symbol}}</h3>
                                        <div><strong>Summary:</strong> ${{sectionResult.summary || "No summary provided."}}</div>
                                        ${{renderList("Highlights", sectionResult.highlights)}}
                                        ${{renderList("Risks", sectionResult.risks)}}
                                        ${{renderList("Questions", sectionResult.questions)}}
                                    </div>
                                `);
                            }});
                            node.innerHTML = cards.join("");
                        }});
                    }}

                    function renderList(title, items) {{
                        if (!items || !items.length) {{
                            return "";
                        }}
                        const rows = items.map((item) => `<li>${{item}}</li>`).join("");
                        return `<div><strong>${{title}}:</strong><ul>${{rows}}</ul></div>`;
                    }}

                    function resizeComparisonTables() {{
                        document.querySelectorAll(".comparison-table").forEach((table) => {{
                            const labelCells = table.querySelectorAll("tr > th:first-child");
                            let maxWidth = 0;
                            const labelCol = table.querySelector("col.label-col");
                            const valueCols = table.querySelectorAll("col.value-col");
                            if (!labelCol || !valueCols.length) {{
                                return;
                            }}
                            labelCol.style.width = "auto";
                            valueCols.forEach((col) => {{
                                col.style.width = "auto";
                            }});
                            table.style.width = "max-content";
                            labelCells.forEach((cell) => {{
                                maxWidth = Math.max(maxWidth, cell.scrollWidth);
                            }});
                            const container = table.parentElement;
                            const containerWidth = container ? container.clientWidth : table.clientWidth;
                            const maxLabelWidth = 260;
                            const labelWidth = Math.min(maxWidth, maxLabelWidth);
                            const minValueWidth = 120;
                            const requiredWidth = labelWidth + minValueWidth * valueCols.length;
                            const tableWidth = Math.max(containerWidth, requiredWidth);
                            table.style.width = `${{tableWidth}}px`;
                            labelCol.style.width = `${{labelWidth}}px`;
                            const valueWidth = Math.max((tableWidth - labelWidth) / valueCols.length, minValueWidth);
                            valueCols.forEach((col) => {{
                                col.style.width = `${{valueWidth}}px`;
                            }});
                        }});
                    }}

                    window.addEventListener("load", resizeComparisonTables);
                    window.addEventListener("resize", resizeComparisonTables);
                </script>
                {f'<script>window.addEventListener("load", () => {{ alert("Ticker not found: {", ".join(missing_symbols)}"); }});</script>' if missing_symbols else ''}
            </body>
        </html>
    """


@app.get("/company", response_class=HTMLResponse)
async def company() -> str:
    return render_company_page()


@app.get("/market", response_class=HTMLResponse)
async def market_page() -> str:
    market_today = datetime.now(US_MARKET_TZ).date().isoformat()
    return render_market_page(
        list_news_models(),
        default_date=market_today,
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page() -> str:
    return render_calendar_page()


@app.get("/person", response_class=HTMLResponse)
async def person() -> str:
    return render_person_page()


@app.get("/global", response_class=HTMLResponse)
async def global_page() -> str:
    return render_global_page()


@app.get("/crypto", response_class=HTMLResponse)
async def crypto_page() -> str:
    return render_crypto_page()


@app.get("/capital", response_class=HTMLResponse)
async def capital_page() -> str:
    return render_crypto_page()


@app.get("/company/{company_name}", response_class=HTMLResponse)
async def company_detail(company_name: str) -> str:
    return render_company_detail_page(
        company_name,
        model_choices_by_provider=list_news_models(),
        indicator_models=list_models().get("openai", []),
    )


@app.get("/notes", response_class=HTMLResponse)
async def notes_page() -> str:
    return render_notes_page()


@app.get("/api/companies")
async def list_companies() -> Dict[str, Any]:
    companies = list_watchlist_company_rows()
    return {
        "companies": companies,
        "company_names": [item["company_name"] for item in companies],
    }


@app.get("/api/notes")
async def get_notes_api(tag: Optional[str] = Query(None)) -> Dict[str, Any]:
    return {
        "notes": list_user_notes(tag=tag),
        "tag": (tag or "").strip(),
    }


@app.get("/api/notes/tags")
async def get_note_tags_api() -> Dict[str, Any]:
    return {"tags": list_user_note_tags()}


@app.get("/api/jobs/by-key")
async def get_job_by_key_api(job_key: str = Query(...), include_finished: bool = Query(True)) -> Dict[str, Any]:
    job = _safe_job(find_latest_job(job_key=job_key, include_finished=include_finished))
    return {"job": job}


@app.get("/api/jobs/{job_id}")
async def get_job_api(job_id: int) -> Dict[str, Any]:
    job = _safe_job(get_job(int(job_id)))
    if not job:
        return {"error": "job not found"}
    return {"job": job}


@app.post("/api/notes")
async def create_note_api(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    try:
        note = create_user_note(
            title=payload.get("title"),
            body_markdown=payload.get("body"),
            tags=payload.get("tags"),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"note": note}


@app.put("/api/notes/{note_id}")
async def update_note_api(note_id: int, request: Request) -> Dict[str, Any]:
    payload = await request.json()
    try:
        note = update_user_note(
            int(note_id),
            title=payload.get("title"),
            body_markdown=payload.get("body"),
            tags=payload.get("tags"),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except KeyError:
        return {"error": "note not found"}
    return {"note": note}


@app.post("/api/notes/{note_id}/invalidate")
async def invalidate_note_api(note_id: int, request: Request) -> Dict[str, Any]:
    payload = await request.json()
    try:
        note = invalidate_user_note(int(note_id), reason=payload.get("reason"))
    except KeyError:
        return {"error": "note not found"}
    return {"note": note}


@app.get("/api/market/overview")
async def market_overview(
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    market_today = datetime.now(US_MARKET_TZ).date()
    try:
        target_date = (
            datetime.fromisoformat(date).date()
            if date
            else market_today
        )
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    if target_date > market_today:
        return {"error": "date cannot be in the future"}
    try:
        news_items = _fetch_market_news(target_date=target_date)
        # Keep news date independent from price date.
        # Weekend "today" should still show today's news, but prices come from last settled trading day.
        price_target_date = target_date
        if not _is_us_trading_day(target_date):
            price_target_date = _previous_us_trading_day(target_date)
        elif target_date == market_today and _is_us_market_open_now():
            # During market hours, latest settled daily snapshot is previous trading day.
            price_target_date = _previous_us_trading_day(target_date)
        sections, price_source, snapshot_exists = _resolve_market_price_sections(
            target_date=price_target_date,
        )
        section_map = {str(section.get("key") or ""): section.get("items") or [] for section in sections}
        return {
            "sections": sections,
            "indexes": section_map.get("indexes", []),
            "bonds": section_map.get("bonds", []),
            "commodities": section_map.get("commodities", []),
            "crypto": section_map.get("crypto", []),
            "news": news_items,
            "news_count": len(news_items),
            "date": target_date.isoformat(),
            "price_date": price_target_date.isoformat(),
            "price_data_source": price_source,
            "price_snapshot_exists": bool(snapshot_exists),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/market/news/summaries")
async def market_news_summaries(
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = (
            datetime.fromisoformat(date).date()
            if date
            else datetime.now().date()
        )
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    summaries = _get_market_daily_summaries(target_date)
    return {"date": target_date.isoformat(), "summaries": summaries}


@app.get("/api/market/daily-news")
async def market_daily_news(
    date: Optional[str] = Query(None),
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date() if date else datetime.now().date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    return get_market_daily_news_overview(
        target_date=target_date,
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )


@app.post("/api/market/daily-news/refresh")
async def refresh_market_daily_news(
    date: Optional[str] = Query(None),
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    force_fetch: bool = Query(False),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date() if date else datetime.now().date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    current = get_market_daily_news_overview(
        target_date=target_date,
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    job_key = _job_key("market_daily_news", target_date.isoformat(), provider_name, prompt_style, output_language, str(bool(force_fetch)))
    started = _start_background_job(
        job_type="market_daily_news_refresh",
        job_key=job_key,
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style=prompt_style,
        target_date=target_date,
        metadata={"force_fetch": bool(force_fetch)},
        worker=lambda tracker: _run_market_daily_news_job(
            tracker,
            target_date=target_date,
            provider_name=provider_name,
            model=selected_model,
            prompt_style=prompt_style,
            output_language=output_language,
            force_fetch=force_fetch,
        ),
    )
    return {**current, **started}


@app.get("/api/market/news/summary-dates")
async def market_news_summary_dates(
    lookback_days: int = Query(365, ge=1, le=3650),
) -> Dict[str, Any]:
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=max(1, int(lookback_days)) - 1)
    return {
        "dates": _get_market_summary_dates(start_date=start_date, end_date=end_date),
    }


@app.post("/api/market/news/summarize")
async def summarize_market_news(
    date: Optional[str] = Query(None),
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    try:
        target_date = (
            datetime.fromisoformat(date).date()
            if date
            else datetime.now().date()
        )
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    selected_prompt = str(prompt_style or "simple").strip().lower()
    if selected_prompt not in {"simple", "structured"}:
        return {"error": "prompt_style must be simple or structured"}
    news_items = _fetch_market_news(target_date=target_date)
    if not news_items:
        return {"error": "No market news to summarize"}
    prompt = _build_market_news_summary_prompt(
        news_items,
        prompt_style=selected_prompt,
        output_language=output_language,
    )
    source_values = sorted(
        {
            str(item.get("source_tag") or "").strip().lower()
            for item in news_items
            if str(item.get("source_tag") or "").strip()
        }
    )
    run_results: List[Dict[str, Any]] = []
    providers_to_run = ["openai", "perplexity", "gemini"]
    for idx, provider_name in enumerate(providers_to_run):
        selected_model = MARKET_SUMMARY_DEFAULT_MODEL.get(provider_name, DEFAULT_OPENAI_MODEL)
        started = pytime.perf_counter()
        try:
            summary_text = _run_market_news_summary(
                provider=provider_name,
                model=selected_model,
                prompt=prompt,
            )
            created = _upsert_market_daily_summary(
                summary_date=target_date,
                provider=provider_name,
                model=selected_model,
                prompt_style=selected_prompt,
                news_sources=",".join(source_values),
                input_payload={"news": news_items, "prompt": prompt},
                output_text=summary_text,
            )
            run_results.append(
                {
                    "provider": provider_name,
                    "model": selected_model,
                    "ok": True,
                    "elapsed_sec": round(pytime.perf_counter() - started, 2),
                    "saved": created,
                }
            )
        except Exception as exc:
            run_results.append(
                {
                    "provider": provider_name,
                    "model": selected_model,
                    "ok": False,
                    "error": str(exc),
                    "elapsed_sec": round(pytime.perf_counter() - started, 2),
                }
            )
        if idx < len(providers_to_run) - 1:
            pytime.sleep(1.0)
    summaries = _get_market_daily_summaries(target_date)
    return {
        "date": target_date.isoformat(),
        "run_results": run_results,
        "summaries": summaries,
    }


@app.get("/api/market/news/item-analyses")
async def market_news_item_analyses(
    date: str = Query(...),
    model: str = Query(DEFAULT_OPENAI_MODEL),
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    rows = _get_market_news_item_analyses(
        news_date=target_date,
        model=model,
        output_language=output_language,
    )
    return {"date": target_date.isoformat(), "model": model, "analyses": rows}


@app.post("/api/market/news/item-analyze")
async def analyze_market_news_item(
    request: Request,
    model: str = Query(DEFAULT_OPENAI_MODEL),
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    payload = await request.json()
    date_text = str(payload.get("date") or "").strip()
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    headline = str(item.get("headline") or "").strip()
    news_url = str(item.get("url") or "").strip()
    source = str(item.get("source") or "").strip()
    source_tag = str(item.get("source_tag") or "").strip().lower()
    summary = str(item.get("summary") or "").strip()
    datetime_text = str(item.get("datetime_text") or "").strip()
    if not date_text:
        return {"error": "date is required"}
    if not headline or not news_url:
        return {"error": "item.headline and item.url are required"}
    try:
        news_date = datetime.fromisoformat(date_text).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}

    provider = _resolve_news_provider_for_model(model)
    prompt = _build_market_single_news_prompt(
        item={
            "headline": headline,
            "url": news_url,
            "source": source,
            "source_tag": source_tag,
            "summary": summary,
            "datetime_text": datetime_text,
        },
        output_language=output_language,
    )
    analyzed_text = _run_market_news_summary(
        provider=provider,
        model=model,
        prompt=prompt,
    )
    row = _upsert_market_news_item_analysis(
        news_date=news_date,
        news_url=news_url,
        headline=headline,
        source=source,
        source_tag=source_tag,
        provider=provider,
        model=model,
        output_language=output_language,
        prompt_style="simple",
        input_payload={"item": item, "prompt": prompt},
        output_text=analyzed_text,
    )
    return {"ok": True, "analysis": row}


@app.get("/api/market/stories")
async def market_stories(
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return get_market_story_overview(
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )


@app.post("/api/market/stories/refresh")
async def refresh_market_stories(
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    job_key = _job_key("market_stories", provider_name, prompt_style, output_language)
    result = _start_background_job(
        job_type="market_story_backfill",
        job_key=job_key,
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style=prompt_style,
        worker=lambda tracker: _run_market_story_backlog_job(
            tracker,
            provider_name=provider_name,
            model=selected_model,
            prompt_style=prompt_style,
            output_language=output_language,
        ),
    )
    overview = get_market_story_overview(
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {**overview, **result}


@app.post("/api/market/stories/warmup")
async def warmup_market_stories(
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    warmup = start_market_story_warmup(
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    overview = get_market_story_overview(
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {**overview, "warmup": warmup}


@app.post("/api/market/stories/{story_key}/close")
async def close_market_story(
    story_key: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_market_story_status(
        story_key=story_key,
        story_status="closed",
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed}


@app.post("/api/market/stories/{story_key}/reopen")
async def reopen_market_story(
    story_key: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_market_story_status(
        story_key=story_key,
        story_status="ongoing",
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed}


@app.post("/api/market/stories/{story_key}/priority")
async def set_market_story_priority_api(
    story_key: str,
    priority: str = Query("high"),
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_market_story_priority(
        story_key=story_key,
        priority=priority,
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed}


@app.post("/api/market/stories/create-from-news")
async def create_market_story_from_news_api(
    request: Request,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    payload = await request.json()
    date_text = str(payload.get("date") or "").strip()
    story_title = str(payload.get("story_title") or "").strip()
    news_item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    try:
        target_date = datetime.fromisoformat(date_text).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    story = create_market_story_from_news(
        target_date=target_date,
        story_title=story_title,
        news_item=news_item,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"story": story}


@app.post("/api/market/stories/{story_key}/attach-news")
async def attach_market_news_to_story_api(
    story_key: str,
    request: Request,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    payload = await request.json()
    date_text = str(payload.get("date") or "").strip()
    news_item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    try:
        target_date = datetime.fromisoformat(date_text).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    ok = attach_news_to_market_story(
        target_date=target_date,
        story_key=story_key,
        news_item=news_item,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": ok}


@app.get("/api/market/macro")
async def get_market_macro_api(
    lookback_days: Optional[int] = Query(None, ge=0, le=3650),
    lookahead_days: Optional[int] = Query(None, ge=0, le=3650),
) -> Dict[str, Any]:
    today = datetime.now().date()
    if lookback_days is None and lookahead_days is None:
        rows = list_market_macro_events(start_date=None, end_date=None, limit=2000)
        if rows:
            start_date = min(datetime.fromisoformat(str(item["event_date_time"]).replace("Z", "+00:00")).date() for item in rows if item.get("event_date_time"))
            end_date = max(datetime.fromisoformat(str(item["event_date_time"]).replace("Z", "+00:00")).date() for item in rows if item.get("event_date_time"))
        else:
            start_date = today
            end_date = today
    else:
        start_date = today - timedelta(days=max(0, int(lookback_days or 0)))
        end_date = today + timedelta(days=max(0, int(lookahead_days or 0)))
        rows = list_market_macro_events(start_date=start_date, end_date=end_date, limit=2000)
    return {"events": rows, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}


@app.post("/api/market/macro/refresh")
async def refresh_market_macro_api(
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    started = _start_background_job(
        job_type="market_macro_refresh",
        job_key=_job_key("market_macro", provider_name, output_language),
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        worker=lambda tracker: _run_market_macro_refresh_job(
            tracker,
            provider_name=provider_name,
            model=selected_model,
            output_language=output_language,
        ),
    )
    rows = list_market_macro_events(start_date=None, end_date=None, limit=2000)
    return {"events": rows, "description": "Refresh the stored calendar for the next 3 months.", **started}


@app.post("/api/companies")
async def add_company(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    company_name = str(payload.get("company_name", "")).strip()
    if not company_name:
        return {"error": "company_name is required"}
    warmup = start_company_story_warmup(
        company_name,
        subscribe=True,
        provider_name="openai",
        model=DEFAULT_OPENAI_MODEL,
        prompt_style="simple",
        output_language="zh-CN",
    )
    return {"ok": True, "warmup": warmup}


@app.delete("/api/companies/{company_name}")
async def remove_company(company_name: str) -> Dict[str, Any]:
    remove_company_from_watchlist(company_name)
    return {"ok": True}


@app.put("/api/company/{company_name}/ticker")
async def update_company_ticker(company_name: str, request: Request) -> Dict[str, Any]:
    payload = await request.json()
    ticker = payload.get("ticker")
    if ticker is not None and not isinstance(ticker, str):
        return {"error": "ticker must be a string or null"}
    try:
        profile = set_company_ticker(company_name, ticker)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "ok": True,
        "company_name": company_name,
        "ticker": profile.get("ticker") if profile else None,
    }


@app.get("/api/company/{company_name}/news")
async def company_news(
    company_name: str,
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    ensure_company_profile(company_name)
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups}


@app.post("/api/company/{company_name}/refresh")
async def refresh_company_news(
    company_name: str,
    week_date: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    before_count = len(get_company_news(company_name, output_language=output_language))
    selected_source = source or "openai"
    if start_date or end_date:
        if not start_date or not end_date:
            return {"error": "start_date and end_date are required"}
        try:
            start = datetime.fromisoformat(start_date).date()
            end = datetime.fromisoformat(end_date).date()
        except ValueError:
            return {"error": "start_date and end_date must be YYYY-MM-DD"}
        if selected_source == "openai":
            today = datetime.now().date()
            if end > today:
                end = today
        refresh_stats = refresh_company_news_for_range(
            company_name,
            start_date=start,
            end_date=end,
            source_name=selected_source,
            provider_name=provider or "openai",
            model=model or DEFAULT_OPENAI_MODEL,
        )
        articles = get_company_news(company_name, output_language=output_language)
        groups = _group_news_items(company_name, articles)
        added_count = max(0, len(articles) - before_count)
        return {
            "company": company_name,
            "groups": groups,
            "added_count": added_count,
            "fetched_total": int(refresh_stats.get("fetched_total", 0)),
            "filtered_out": int(refresh_stats.get("filtered_out", 0)),
            "elapsed_sec": float(refresh_stats.get("elapsed_sec", 0.0)),
        }

    # Backward-compatible fallback for older UI using week_date only.
    selected = None
    if week_date:
        try:
            selected = datetime.fromisoformat(week_date).date()
        except ValueError:
            return {"error": "week_date must be YYYY-MM-DD"}
    if selected is None:
        selected = datetime.now().date()
    week_start = selected - timedelta(days=selected.weekday())
    week_end = week_start + timedelta(days=6)
    if selected_source == "openai":
        today = datetime.now().date()
        if week_end > today:
            week_end = today
    refresh_stats = refresh_company_news_for_range(
        company_name,
        start_date=week_start,
        end_date=week_end,
        source_name=selected_source,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    added_count = max(0, len(articles) - before_count)
    return {
        "company": company_name,
        "groups": groups,
        "added_count": added_count,
        "fetched_total": int(refresh_stats.get("fetched_total", 0)),
        "filtered_out": int(refresh_stats.get("filtered_out", 0)),
        "elapsed_sec": float(refresh_stats.get("elapsed_sec", 0.0)),
    }


@app.post("/api/company/{company_name}/report")
async def generate_company_report(
    company_name: str,
    week_date: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        selected = datetime.fromisoformat(week_date).date()
    except ValueError:
        return {"error": "week_date must be YYYY-MM-DD"}
    week_start = selected - timedelta(days=selected.weekday())
    week_end = week_start + timedelta(days=6)
    generate_weekly_report(
        company_name,
        start_date=week_start,
        end_date=week_end,
        output_language=output_language,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups}


@app.post("/api/company/{company_name}/report/day")
async def generate_company_daily_report_api(
    company_name: str,
    date: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    stats = generate_company_daily_report(
        company_name,
        target_date=target_date,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style="simple",
        output_language=output_language,
    )
    cluster_stats = refresh_company_daily_clusters(
        company_name,
        target_date=target_date,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style="simple",
        output_language=output_language,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups, "cluster_stats": cluster_stats, **stats}


@app.get("/api/company/{company_name}/status")
async def get_company_status_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    snapshot = get_company_status_snapshot(
        company_name,
        provider_name=provider or "openai",
        prompt_style="simple",
    )
    return {"company": company_name, "status": snapshot}


@app.get("/api/company/{company_name}/price-intelligence")
async def get_company_price_intelligence_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    run = get_company_price_intelligence_run(company_name)
    history = list_company_price_intelligence_runs(company_name, limit=10)
    previous_run_summary = history[1] if len(history) > 1 else None
    return {"company": company_name, "run": run, "previous_run_summary": previous_run_summary, "history_preview": history[:10]}


@app.post("/api/company/{company_name}/status/generate")
async def generate_company_status_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    window_days: int = Query(21),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    stats = _start_background_job(
        job_type="company_detailed_report",
        job_key=_job_key("detailed_report", company_name, provider_name, output_language, max(30, int(window_days))),
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style="simple",
        target_entity=company_name,
        worker=lambda tracker: _run_detailed_report_job(
            tracker,
            company_name=company_name,
            provider_name=provider_name,
            model=selected_model,
            output_language=output_language,
            window_days=max(30, int(window_days)),
        ),
    )
    snapshot = get_company_status_snapshot(
        company_name,
        provider_name=provider_name,
        prompt_style="simple",
    )
    return {"company": company_name, "status": snapshot, **stats}


@app.post("/api/company/{company_name}/price-intelligence/generate")
async def generate_company_price_intelligence_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    stats = _start_background_job(
        job_type="company_price_intelligence",
        job_key=_job_key("price_intelligence", company_name, provider_name, output_language),
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style="simple",
        target_entity=company_name,
        worker=lambda tracker: _run_price_intelligence_job(
            tracker,
            company_name=company_name,
            provider_name=provider_name,
            model=selected_model,
            output_language=output_language,
        ),
    )
    run = get_company_price_intelligence_run(company_name)
    history = list_company_price_intelligence_runs(company_name, limit=10)
    previous_run_summary = history[1] if len(history) > 1 else None
    return {"company": company_name, "run": run, "previous_run_summary": previous_run_summary, "history_preview": history[:10], **stats}


@app.get("/api/company/{company_name}/price-intelligence/history")
async def get_company_price_intelligence_history_api(company_name: str, limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    return {"company": company_name, "runs": list_company_price_intelligence_runs(company_name, limit=limit)}


@app.get("/api/company/{company_name}/price-intelligence/{run_id}")
async def get_company_price_intelligence_run_api(company_name: str, run_id: int) -> Dict[str, Any]:
    run = get_company_price_intelligence_run(company_name, run_id=run_id)
    if not run:
        return {"error": "run not found"}
    history = list_company_price_intelligence_runs(company_name, limit=20)
    previous = None
    for idx, item in enumerate(history):
        if int(item.get("id") or 0) == int(run_id):
            previous = history[idx + 1] if idx + 1 < len(history) else None
            break
    return {"company": company_name, "run": run, "previous_run_summary": previous, "history_preview": history[:10]}


@app.get("/api/company/{company_name}/earnings")
async def get_company_earnings_api(
    company_name: str,
    refresh: bool = Query(False),
) -> Dict[str, Any]:
    if refresh:
        refresh_company_earnings(company_name)
    return {"company": company_name, "events": list_company_earnings(company_name)}


@app.post("/api/company/{company_name}/earnings/refresh")
async def refresh_company_earnings_api(
    company_name: str,
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    stats = refresh_company_earnings(
        company_name,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        output_language=output_language,
    )
    return {"company": company_name, **stats}


@app.get("/api/company/{company_name}/stories")
async def get_company_stories_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    overview = get_company_story_overview(
        company_name,
        provider_name=provider_name,
        model=DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return overview


@app.post("/api/company/{company_name}/stories/refresh")
async def refresh_company_stories_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    window_days: int = Query(21),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    result = _start_background_job(
        job_type="company_story_update",
        job_key=_job_key("company_story_update", company_name, provider_name, prompt_style, output_language, window_days),
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style=prompt_style,
        target_entity=company_name,
        worker=lambda tracker: _run_company_story_update_job(
            tracker,
            company_name=company_name,
            provider_name=provider_name,
            model=selected_model,
            prompt_style=prompt_style,
            output_language=output_language,
            window_days=window_days,
        ),
    )
    overview = get_company_story_overview(
        company_name,
        provider_name=provider_name,
        model=selected_model,
        prompt_style=prompt_style,
        output_language=output_language,
        start_warmup_if_needed=False,
    )
    return {**overview, **result}


@app.post("/api/company/{company_name}/stories/rebuild-warmup")
async def rebuild_company_story_warmup_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = model or DEFAULT_OPENAI_MODEL
    started = _start_background_job(
        job_type="company_story_rebuild_warmup",
        job_key=_job_key("company_story_rebuild", company_name, provider_name, prompt_style, output_language),
        provider=provider_name,
        model=selected_model,
        output_language=output_language,
        prompt_style=prompt_style,
        target_entity=company_name,
        worker=lambda tracker: _run_company_rebuild_warmup_job(
            tracker,
            company_name=company_name,
            provider_name=provider_name,
            model=selected_model,
            prompt_style=prompt_style,
            output_language=output_language,
        ),
    )
    overview = get_company_story_overview(
        company_name,
        provider_name=provider_name,
        model=selected_model,
        prompt_style=prompt_style,
        output_language=output_language,
        start_warmup_if_needed=False,
    )
    return {**overview, **started}


@app.get("/api/company/{company_name}/stories/{story_key}")
async def get_company_story_detail_api(
    company_name: str,
    story_key: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    story = get_company_story_state(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not story:
        return {"error": "story not found"}
    updates = list_company_story_updates(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=10,
    )
    qa = list_company_story_qa(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=10,
    )
    return {"company": company_name, "story": story, "updates": updates, "qa": qa}


@app.post("/api/company/{company_name}/stories/{story_key}/close")
async def close_company_story_api(
    company_name: str,
    story_key: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_company_story_status(
        company_name,
        story_key=story_key,
        story_status="finished",
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed, "story_key": story_key, "story_status": "finished"}


@app.post("/api/company/{company_name}/stories/{story_key}/reopen")
async def reopen_company_story_api(
    company_name: str,
    story_key: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_company_story_status(
        company_name,
        story_key=story_key,
        story_status="ongoing",
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed, "story_key": story_key, "story_status": "ongoing"}


@app.post("/api/company/{company_name}/stories/{story_key}/priority")
async def update_company_story_priority_api(
    company_name: str,
    story_key: str,
    priority: str = Query("high"),
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    changed = update_company_story_priority(
        company_name,
        story_key=story_key,
        priority=priority,
        provider_name=provider or "openai",
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed, "story_key": story_key, "priority": priority}


@app.post("/api/company/{company_name}/stories/create-from-news")
async def create_company_story_from_news_api(
    company_name: str,
    request: Request,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    payload = await request.json()
    target_date = datetime.fromisoformat(str(payload.get("target_date"))).date()
    story = create_company_story_from_news(
        company_name,
        target_date=target_date,
        story_title=str(payload.get("story_title") or "").strip(),
        news_item=payload.get("news_item") or {},
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not story:
        return {"error": "failed to create story"}
    return {"company": company_name, "story": story}


@app.post("/api/company/{company_name}/stories/{story_key}/attach-news")
async def attach_news_to_company_story_api(
    company_name: str,
    story_key: str,
    request: Request,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    payload = await request.json()
    changed = attach_news_to_company_story(
        company_name,
        target_date=datetime.fromisoformat(str(payload.get("target_date"))).date(),
        story_key=story_key,
        news_item=payload.get("news_item") or {},
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {"ok": changed, "story_key": story_key}


@app.post("/api/company/{company_name}/stories/{story_key}/ask")
async def ask_company_story_api(
    company_name: str,
    story_key: str,
    request: Request,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    payload = await request.json()
    question = str(payload.get("question") or "").strip()
    if not question:
        return {"error": "question is required"}
    provider_name = provider or "openai"
    row = ask_company_story_question(
        company_name,
        story_key=story_key,
        question=question,
        provider_name=provider_name,
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not row:
        return {"error": "story not found or question invalid"}
    qa = list_company_story_qa(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=10,
    )
    return {"company": company_name, "story_key": story_key, "qa": qa, "last_answer": row}


@app.post("/api/company/{company_name}/stories/{story_key}/qa/{qa_id}/merge")
async def merge_company_story_qa_api(
    company_name: str,
    story_key: str,
    qa_id: int,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    row = merge_company_story_qa_answer(
        company_name,
        story_key=story_key,
        qa_id=qa_id,
        provider_name=provider_name,
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if not row:
        return {"error": "story or Q&A row not found, or merge failed"}
    story = get_company_story_state(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    updates = list_company_story_updates(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=10,
    )
    qa = list_company_story_qa(
        company_name,
        story_key=story_key,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
        limit=10,
    )
    return {
        "company": company_name,
        "story_key": story_key,
        "story": story,
        "updates": updates,
        "qa": qa,
        "merged_story": row,
    }


@app.get("/api/company/{company_name}/price/history")
async def get_company_price_history_api(
    company_name: str,
    years: int = Query(1, ge=1, le=5),
    ma_windows: str = Query("20,50,200"),
    ticker: Optional[str] = Query(None),
) -> Dict[str, Any]:
    resolved_ticker = (ticker or "").strip().upper()
    if not resolved_ticker:
        profile = get_company_profile(company_name) or ensure_company_profile(company_name)
        if profile:
            resolved_ticker = str(
                profile.get("ticker")
                or profile.get("symbol")
                or profile.get("displaySymbol")
                or ""
            ).strip().upper()
    if not resolved_ticker:
        return {"error": "ticker not found; set ticker for this company first"}

    windows = _parse_ma_windows(ma_windows)
    history = _fetch_yahoo_daily_price_history(resolved_ticker, years=years)
    source_name = "yahoo_finance_chart"
    if not history:
        api_key = os.getenv("FINNHUB_API_KEY", "").strip()
        if api_key:
            history = _fetch_finnhub_daily_price_history(
                resolved_ticker,
                years=years,
                api_key=api_key,
            )
            source_name = "finnhub_stock_candle"
    if not history:
        return {
            "company": company_name,
            "ticker": resolved_ticker,
            "years": years,
            "ma_windows": windows,
            "points": [],
            "error": "no daily price history returned",
        }
    points = _attach_moving_averages(history, windows=windows)
    return {
        "company": company_name,
        "ticker": resolved_ticker,
        "years": years,
        "ma_windows": windows,
        "point_count": len(points),
        "source": source_name,
        "points": points,
    }


@app.get("/api/company/{company_name}/indicators")
async def get_company_indicators_api(
    company_name: str,
    ticker: Optional[str] = Query(None),
) -> Dict[str, Any]:
    resolved_ticker = (ticker or "").strip().upper()
    if not resolved_ticker:
        profile = get_company_profile(company_name) or ensure_company_profile(company_name)
        if profile:
            resolved_ticker = str(
                profile.get("ticker")
                or profile.get("symbol")
                or profile.get("displaySymbol")
                or ""
            ).strip().upper()
    if not resolved_ticker:
        return {"error": "ticker not found; set ticker for this company first"}
    try:
        snapshot = client.query(resolved_ticker)
    except Exception as exc:
        return {"error": f"failed to fetch indicators: {exc}"}
    base = snapshot.base.as_dict()
    grouped = _group_indicators(base)
    sections = [
        {
            "name": section_name,
            "rows": [{"label": label, "value": _serialize_indicator_value(value)} for label, value in rows],
        }
        for section_name, rows in grouped
    ]
    return {
        "company": company_name,
        "ticker": resolved_ticker,
        "sections": sections,
    }


@app.post("/api/company/{company_name}/indicators/analyze")
async def analyze_company_indicators_api(
    company_name: str,
    ticker: Optional[str] = Query(None),
    model: str = Query("gpt-4o-mini"),
    provider: str = Query("openai"),
) -> Dict[str, Any]:
    resolved_ticker = (ticker or "").strip().upper()
    if not resolved_ticker:
        profile = get_company_profile(company_name) or ensure_company_profile(company_name)
        if profile:
            resolved_ticker = str(
                profile.get("ticker")
                or profile.get("symbol")
                or profile.get("displaySymbol")
                or ""
            ).strip().upper()
    if not resolved_ticker:
        return {"error": "ticker not found; set ticker for this company first"}
    try:
        snapshot = client.query(resolved_ticker)
        llm_provider = get_provider(provider, model=model)
        result = analyze_single_stock_sections(
            snapshot,
            provider=llm_provider,
        )
    except Exception as exc:
        return {"error": f"failed to analyze indicators: {exc}"}
    return {
        "company": company_name,
        "ticker": resolved_ticker,
        "provider": provider,
        "model": model,
        "analysis": result,
    }


@app.get("/api/company/{company_name}/stock/series")
async def get_company_stock_series_api(
    company_name: str,
    range_key: str = Query("1Y"),
    ma_windows: str = Query("20,50,200"),
    ticker: Optional[str] = Query(None),
) -> Dict[str, Any]:
    resolved_ticker = (ticker or "").strip().upper()
    if not resolved_ticker:
        profile = get_company_profile(company_name) or ensure_company_profile(company_name)
        if profile:
            resolved_ticker = str(
                profile.get("ticker")
                or profile.get("symbol")
                or profile.get("displaySymbol")
                or ""
            ).strip().upper()
    if not resolved_ticker:
        return {"error": "ticker not found; set ticker for this company first"}
    normalized_range = _normalize_price_range_key(range_key)
    windows = _parse_ma_windows(ma_windows)
    points = _get_or_refresh_company_price_series(
        company_name=company_name,
        ticker=resolved_ticker,
        range_key=normalized_range,
    )
    if not points:
        return {
            "company": company_name,
            "ticker": resolved_ticker,
            "range_key": normalized_range,
            "ma_windows": windows,
            "points": [],
            "error": "no price series returned",
        }
    full_points = _list_company_price_daily_points_all(
        company_name=company_name,
        ticker=resolved_ticker,
    )
    ma_base_points = full_points or points
    ma_enriched_full = _attach_moving_averages(ma_base_points, windows=windows)
    enriched = _merge_trimmed_ma_points(
        visible_points=points,
        ma_points=ma_enriched_full,
        windows=windows,
    )
    enriched = _attach_pct_change(enriched)
    return {
        "company": company_name,
        "ticker": resolved_ticker,
        "range_key": normalized_range,
        "ma_windows": windows,
        "point_count": len(enriched),
        "points": enriched,
    }


@app.post("/api/company/{company_name}/stock/moves/analyze")
async def analyze_company_stock_moves_api(
    company_name: str,
    range_key: str = Query("1Y"),
    top_n: int = Query(8),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
) -> Dict[str, Any]:
    resolved_ticker = (ticker or "").strip().upper()
    if not resolved_ticker:
        profile = get_company_profile(company_name) or ensure_company_profile(company_name)
        if profile:
            resolved_ticker = str(
                profile.get("ticker")
                or profile.get("symbol")
                or profile.get("displaySymbol")
                or ""
            ).strip().upper()
    if not resolved_ticker:
        return {"error": "ticker not found; set ticker for this company first"}
    normalized_range = _normalize_price_range_key(range_key)
    points = _get_or_refresh_company_price_series(
        company_name=company_name,
        ticker=resolved_ticker,
        range_key=normalized_range,
    )
    if not points:
        return {"error": "no price series returned"}
    points = _attach_pct_change(points)
    candidates = _select_critical_price_points(points, top_n=max(1, min(int(top_n), 20)))
    if not candidates:
        return {"analyses": [], "count": 0}
    provider_name = provider or "openai"
    model_name = model or DEFAULT_OPENAI_MODEL
    results: List[Dict[str, Any]] = []
    for idx, point in enumerate(candidates):
        point_time = str(point.get("date_time") or "").strip()
        if not point_time:
            continue
        existing = _get_company_price_move_analysis(
            company_name=company_name,
            ticker=resolved_ticker,
            range_key=normalized_range,
            point_date_time=point_time,
            provider=provider_name,
            prompt_style="simple",
            output_language=output_language,
        )
        if existing:
            results.append(existing)
            continue
        prompt = _build_company_price_move_prompt(
            company_name=company_name,
            ticker=resolved_ticker,
            point=point,
            range_key=normalized_range,
            output_language=output_language,
        )
        output_text = _run_market_news_summary(
            provider=provider_name,
            model=model_name,
            prompt=prompt,
        )
        row = _upsert_company_price_move_analysis(
            company_name=company_name,
            ticker=resolved_ticker,
            range_key=normalized_range,
            point_date_time=point_time,
            point_label=point["date"],
            close_price=point["close"],
            pct_change=point.get("pct_change"),
            volume=point.get("volume"),
            provider=provider_name,
            model=model_name,
            prompt_style="simple",
            output_language=output_language,
            input_payload={"prompt": prompt, "point": point},
            output_text=output_text,
        )
        results.append(row)
        if idx < len(candidates) - 1:
            pytime.sleep(1.0)
    return {
        "company": company_name,
        "ticker": resolved_ticker,
        "range_key": normalized_range,
        "count": len(results),
        "analyses": results,
    }


@app.delete("/api/company/{company_name}/news/{news_id}")
async def delete_company_news_item(
    company_name: str,
    news_id: int,
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    delete_company_news(company_name, news_id=news_id)
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups}


@app.post("/api/company/{company_name}/news/{news_id}/summarize")
async def summarize_company_news(
    company_name: str,
    news_id: int,
    analysis_prompt: Optional[str] = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    summarize_company_news_item(
        company_name,
        news_id=news_id,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        analysis_prompt=(analysis_prompt or "simple"),
        output_language=output_language,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups}


@app.post("/api/company/{company_name}/news/{news_id}/filter")
async def filter_company_news(
    company_name: str,
    news_id: int,
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    result = filter_company_news_item(
        company_name,
        news_id=news_id,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups, "filter_result": result}


@app.post("/api/company/{company_name}/news/filter/day")
@app.post("/api/company/{company_name}/news/day/filter")
async def filter_company_news_for_day(
    company_name: str,
    date: str = Query(...),
    limit: int = Query(5),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    stats = filter_company_news_day(
        company_name,
        target_date=target_date,
        limit=limit,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {
        "company": company_name,
        "groups": groups,
        "processed_count": stats.get("processed", 0),
        "kept_count": stats.get("kept", 0),
        "dropped_count": stats.get("dropped", 0),
        "elapsed_sec": stats.get("elapsed_sec", 0.0),
    }


@app.post("/api/company/{company_name}/news/summarize/day")
@app.post("/api/company/{company_name}/news/day/summarize")
async def summarize_company_news_for_day(
    company_name: str,
    date: str = Query(...),
    limit: int = Query(5),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    stats = generate_company_daily_report(
        company_name,
        target_date=target_date,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style="simple",
        output_language=output_language,
    )
    cluster_stats = refresh_company_daily_clusters(
        company_name,
        target_date=target_date,
        provider_name=provider or "openai",
        model=model or DEFAULT_OPENAI_MODEL,
        prompt_style="simple",
        output_language=output_language,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {
        "company": company_name,
        "groups": groups,
        "processed_count": stats.get("item_count", 0),
        "analyzed_count": 1 if stats.get("generated") else 0,
        "cluster_count": cluster_stats.get("cluster_count", 0),
        "dropped_count": 0,
        "elapsed_sec": stats.get("elapsed_sec", 0.0),
    }


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _serialize_indicator_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _serialize_indicator_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_indicator_value(v) for v in value]
    return value


def _render_sections(data: Dict[str, object]) -> str:
    grouped = _group_indicators(data)
    return "".join(
        f"""
            <section class="card">
                <h2>{section}</h2>
                <table>
                    {''.join(f'<tr><th>{label}</th><td>{_format_value(value)}</td></tr>' for label, value in rows)}
                </table>
            </section>
        """
        for section, rows in grouped
    )


def _render_comparison_sections(
    stocks: List[Tuple[str, Dict[str, object], Any]],
) -> str:
    grouped = _group_indicator_keys(stocks)
    return "".join(
        f"""
            <section class="card">
                <h2>{section}</h2>
                <div class="comparison-wrap">
                    <table class="comparison-table">
                        <colgroup>
                            <col class="label-col" />
                            {''.join('<col class="value-col" />' for _ in stocks)}
                        </colgroup>
                        <tr>
                            <th>Stock</th>
                            {''.join(f'<th>{symbol}</th>' for symbol, _, _ in stocks)}
                        </tr>
                        {''.join(_render_comparison_row(label, key, stocks) for label, key in rows)}
                    </table>
                </div>
                <div class="analysis-grid" data-analysis-section="{section}"></div>
            </section>
        """
        for section, rows in grouped
    )


def _render_comparison_row(
    label: str,
    key: str,
    stocks: List[Tuple[str, Dict[str, object], Any]],
) -> str:
    cells = "".join(
        f"<td>{_format_value_cell(data.get(key))}</td>" for _, data, _ in stocks
    )
    return f"<tr><th title=\"{label}\">{label}</th>{cells}</tr>"




def _format_value_cell(value: object) -> str:
    if isinstance(value, dict):
        lines = "".join(
            f"<div>{subkey}: {_format_value(subvalue)}</div>"
            for subkey, subvalue in value.items()
        )
        return lines or "-"
    return _format_value(value)


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
    if str(quote.get("close_price") or "").strip() in {"", "-", "—"}:
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
        "close_price": str(quote.get("close_price") or "—"),
        "price_change_pct": str(quote.get("price_change_pct") or "—"),
        "quote_timestamp": quote.get("quote_timestamp"),
        "label": label,
        "country_code": country_code,
        "headline": headline,
        "headline_url": link,
        "headline_time": dt_text,
    }


def _resolve_market_price_sections(*, target_date: date) -> tuple[List[Dict[str, Any]], str, bool]:
    snapshot = _get_market_price_snapshot(target_date)
    snapshot_exists = snapshot is not None
    today = datetime.now(US_MARKET_TZ).date()

    if target_date < today:
        if snapshot:
            return snapshot.get("sections", []), "snapshot", True
        # Backfill the latest settled trading day once if snapshot is missing.
        # This avoids repeated "missing + fallback" for the most recent close.
        settled = _latest_settled_us_market_date()
        if target_date == settled and _is_us_trading_day(target_date):
            live_sections = _build_market_price_sections_live()
            _upsert_market_price_snapshot(target_date, {"sections": live_sections})
            return live_sections, "snapshot_backfilled_from_live", True
        # For older missing dates, keep explicit missing status.
        return [], "snapshot_missing", False

    # target_date == today
    if _is_us_market_open_now():
        return _build_market_price_sections_live(), "live_market_hours", snapshot_exists

    if snapshot:
        return snapshot.get("sections", []), "snapshot", True

    live_sections = _build_market_price_sections_live()
    if _is_us_trading_day(target_date) and _is_us_market_day_closed_now():
        _upsert_market_price_snapshot(target_date, {"sections": live_sections})
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
                "price_change_pct": str(base.get("price_change_pct", "—")),
                "quote_timestamp": base.get("quote_timestamp"),
            }
        except Exception:
            continue
    return {
        "symbol": symbols[0] if symbols else "",
        "close_price": "—",
        "price_change_pct": "—",
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
    pct_text = f"{pct:+.2f}%" if pct is not None else "—"
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

    pct_text = "—"
    if previous not in (None, 0):
        try:
            pct = ((latest - float(previous)) / float(previous)) * 100.0
            pct_text = f"{pct:+.2f}%"
        except Exception:
            pct_text = "—"

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
        except Exception:
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
            return points
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
    except Exception:
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
    daily: Dict[date, List[Dict[str, Any]]] = {}
    weekly: Dict[date, List[Dict[str, Any]]] = {}
    today = datetime.now().date()

    for article in articles:
        news_date = article.news_date_time.date()
        week_start = news_date - timedelta(days=news_date.weekday())
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

    groups: List[Dict[str, Any]] = []
    added_weeks: set[date] = set()
    for day in sorted(daily.keys(), reverse=True):
        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
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


def _group_indicators(data: Dict[str, object]) -> List[Tuple[str, List[Tuple[str, object]]]]:
    sections: Dict[str, List[Tuple[str, object]]] = {}
    for key, value in data.items():
        if key == "symbol":
            continue
        section = _classify_indicator(key)
        sections.setdefault(section, []).append((key, value))

    ordered_sections = [
        "Quote",
        "Price & Returns",
        "Volume & Liquidity",
        "Valuation",
        "Profitability & Margins",
        "Growth",
        "Cash Flow",
        "Balance Sheet",
        "Per-Share",
        "Leverage & Coverage",
    ]

    grouped: List[Tuple[str, List[Tuple[str, object]]]] = []
    for section in ordered_sections:
        rows = sections.get(section)
        if not rows:
            continue
        rows.sort(key=lambda item: _sort_key(item[0]))
        grouped.append((section, [(_label_for_key(k), v) for k, v in rows]))
    return grouped


def _group_indicator_keys(
    stocks: List[Tuple[str, Dict[str, object], Any]]
) -> List[Tuple[str, List[Tuple[str, str]]]]:
    sections: Dict[str, List[str]] = {}
    for _, data, _ in stocks:
        for key in data.keys():
            if key == "symbol":
                continue
            section = _classify_indicator(key)
            sections.setdefault(section, [])
            if key not in sections[section]:
                sections[section].append(key)

    ordered_sections = [
        "Quote",
        "Price & Returns",
        "Volume & Liquidity",
        "Valuation",
        "Profitability & Margins",
        "Growth",
        "Cash Flow",
        "Balance Sheet",
        "Per-Share",
        "Leverage & Coverage",
        "3rd Party Recommendation",
    ]

    grouped: List[Tuple[str, List[Tuple[str, str]]]] = []
    for section in ordered_sections:
        keys = sections.get(section)
        if not keys:
            continue
        keys.sort(key=_sort_key)
        grouped.append((section, [(_label_for_key(k), k) for k in keys]))
    return grouped




def _classify_indicator(key: str) -> str:
    lower_key = key.lower()

    if key == "quote_timestamp":
        return "Quote"
    if key == "previous_close":
        return "Price & Returns"

    if any(token in lower_key for token in ("volume", "liquidity")):
        return "Volume & Liquidity"

    if key in {"beta", "moving_averages", "rsi", "macd"}:
        return "Price & Returns"

    if any(token in lower_key for token in ("price", "return", "weekhigh", "weeklow")):
        return "Price & Returns"

    if any(token in lower_key for token in ("marketcap", "enterprisevalue", "ev", "pe")):
        return "Valuation"
    if lower_key.startswith("eps"):
        return "Valuation"

    if any(token in lower_key for token in ("margin", "profit", "operatingmargin")):
        if "growth" in lower_key:
            return "Growth"
        return "Profitability & Margins"

    if any(token in lower_key for token in ("growth", "cagr", "yoy")):
        return "Growth"

    if any(token in lower_key for token in ("cashflow", "free_cash_flow", "capex")):
        return "Cash Flow"

    if any(token in lower_key for token in ("cash", "debt", "equity", "bookvalue")):
        return "Balance Sheet"

    if "pershare" in lower_key:
        return "Per-Share"

    if any(token in lower_key for token in ("ratio", "coverage")):
        return "Leverage & Coverage"

    if any(token in lower_key for token in ("recommendation",)):
        return "Price & Returns"

    return "Price & Returns"


def _label_for_key(key: str) -> str:
    overrides = {
        "3MonthAvgDailyReturnStdDev": "3MoAvgDailyReturnVolStdDev",
        "recommendation": "FinnhubRecommendation",
        "recommendation_counts": "FinnhubRecommendationCounts",
        "focfCagr5Y": "FreeOperatingCashFlowCagr5Y",
        "tbvCagr5Y": "TangibleBookValueCagr5Y",
    }
    label = overrides.get(key, _to_title_camel(key))
    max_len = len(overrides["3MonthAvgDailyReturnStdDev"])
    if len(label) > max_len:
        label = _shorten_label(label, max_len)
    return label


def _to_title_camel(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", value)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    parts = [part for part in spaced.split() if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _shorten_label(label: str, max_len: int) -> str:
    replacements = [
        ("Average", "Avg"),
        ("Quarterly", "Qtr"),
        ("Annual", "Ann"),
        ("Revenue", "Rev"),
        ("Profit", "Prof"),
        ("Operating", "Op"),
        ("Interest", "Int"),
        ("Coverage", "Cov"),
        ("Current", "Curr"),
        ("Relative", "Rel"),
        ("Volatility", "Vol"),
        ("Return", "Ret"),
        ("CashFlow", "CF"),
        ("PerShare", "PerShr"),
        ("Employee", "Emp"),
        ("Share", "Shr"),
        ("LongTerm", "LT"),
        ("Total", "Tot"),
        ("Equity", "Eq"),
        ("Debt", "Debt"),
        ("Tangible", "Tang"),
        ("BookValue", "BV"),
    ]
    shortened = label
    for old, new in replacements:
        if len(shortened) <= max_len:
            break
        shortened = shortened.replace(old, new)
    if len(shortened) > max_len:
        shortened = shortened[: max_len - 1] + "…"
    return shortened


def _sort_key(key: str) -> Tuple[str, int, str]:
    priority = {
        "quote_timestamp": -100,
        "open_price": -90,
        "high_price": -89,
        "low_price": -88,
        "close_price": -87,
        "previous_close": -86,
        "price_change_pct": -85,
        "volume": -84,
        "turnover_rate": -83,
        "market_cap": -82,
    }
    if key in priority:
        return ("", priority[key], key.lower())
    category_rank = _price_return_group_rank(key)
    base_key = _strip_time_tokens(key)
    return (f"{category_rank:02d}-{base_key.lower()}", _time_rank(key), key.lower())


def _strip_time_tokens(key: str) -> str:
    prefixes = ("5Day", "10Day", "13Week", "26Week", "52Week", "3Month", "4Week")
    for prefix in prefixes:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    suffixes = (
        "TTM",
        "Annual",
        "Quarterly",
        "5Y",
        "3Y",
        "Yoy",
        "YTD",
        "Ytd",
        "4Week",
        "13Week",
        "26Week",
        "52Week",
    )
    for suffix in suffixes:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    return key


def _time_rank(key: str) -> int:
    prefix_ranks = {
        "5Day": 5,
        "10Day": 10,
        "4Week": 28,
        "13Week": 91,
        "26Week": 182,
        "3Month": 90,
        "52Week": 364,
    }
    for prefix, rank in prefix_ranks.items():
        if key.startswith(prefix):
            return rank
    suffix_ranks = {
        "4Week": 28,
        "13Week": 91,
        "26Week": 182,
        "52Week": 364,
        "Quarterly": 800,
        "Yoy": 820,
        "TTM": 900,
        "Annual": 1000,
        "3Y": 1200,
        "5Y": 1500,
        "YTD": 600,
        "Ytd": 600,
    }
    for suffix, rank in suffix_ranks.items():
        if key.endswith(suffix):
            return rank
    if re.search(r"monthtodate", key, re.IGNORECASE):
        return 550
    if re.search(r"yeartodate", key, re.IGNORECASE):
        return 600
    return 0


def _price_return_group_rank(key: str) -> int:
    lower_key = key.lower()
    if "return" in lower_key or "pricerelativetosp500" in lower_key:
        return 2
    if any(token in lower_key for token in ("price", "weekhigh", "weeklow", "highdate", "lowdate")):
        return 1
    return 3
