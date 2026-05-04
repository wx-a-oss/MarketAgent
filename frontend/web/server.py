from __future__ import annotations

import logging
import json
import os
import time as pytime
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

from market_agent.config.models import (
    DEFAULT_COMPANY_OPENAI_MODEL,
    DEFAULT_MARKET_OPENAI_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_PROVIDER_MODELS,
    get_default_company_model,
    get_default_market_model,
    get_default_model,
)
from frontend.common import StockFrontendClient
from market_agent.workflows import market_updates as market_updates_module
from frontend.web.charts_page import render_charts_page
from frontend.web.earnings_page import render_earnings_page
from frontend.web.usage_page import render_usage_page
from frontend.web.company_detail_page import render_company_detail_page
from frontend.web.company_page import render_company_page
from frontend.web.crypto_page import render_crypto_page
from frontend.web.global_page import render_global_page
from frontend.web.market_page import render_market_page
from frontend.web.notes_page import render_notes_page
from frontend.web.person_page import render_person_page
from frontend.web.shared_page import render_nav
from market_agent.workflows import (
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
    resolve_market_macro_calendar_window,
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
from market_agent.services.company import (
    add_company_to_watchlist,
    delete_company_news,
    generate_weekly_report,
    generate_monthly_report,
    generate_company_daily_report,
    generate_company_price_intelligence_run,
    generate_company_status_snapshot,
    get_company_news,
    list_company_daily_clusters,
    get_company_watchlist_model,
    get_company_story_state,
    list_company_story_qa,
    list_company_price_intelligence_runs,
    list_company_story_updates,
    get_company_daily_report,
    get_company_profile,
    get_company_price_intelligence_run,
    get_company_status_snapshot,
    list_company_status_snapshots,
    get_company_story_warmup_state,
    get_news_report,
    list_company_chart_layout_rows,
    list_watchlist_company_rows,
    ensure_company_profile,
    filter_company_news_day,
    filter_company_news_item,
    refresh_company_daily_clusters,
    refresh_company_news_for_range,
    refresh_company_news_if_needed,
    remove_company_from_watchlist,
    save_company_chart_layout,
    set_company_ticker,
    ask_company_story_question,
)
from market_agent.utils.week import week_boundaries
from market_agent.services.company import (
    attach_news_to_company_story,
    create_company_story_from_news,
    create_user_note,
    merge_company_story_qa_answer,
    invalidate_user_note,
    summarize_company_news_day,
    summarize_company_news_item,
    update_company_story_priority,
    update_company_story_status,
    update_company_watchlist_model,
    update_user_note,
    list_user_notes,
    list_user_note_tags,
)
from market_agent.workflows.background_jobs import (
    JobTracker,
    create_job,
    find_latest_job,
    get_job,
    mark_interrupted_jobs,
    run_job_async,
)
from market_agent.services.stock.single_stock import analyze_single_stock_sections

# --- Extracted modules ---
from frontend.web._indicator_helpers import (
    _format_value,
    _serialize_indicator_value,
    _render_sections,
    _render_comparison_sections,
    _render_comparison_row,
    _format_value_cell,
    _group_indicators,
    _group_indicator_keys,
    _classify_indicator,
    _label_for_key,
    _to_title_camel,
    _shorten_label,
    _sort_key,
    _strip_time_tokens,
    _time_rank,
    _price_return_group_rank,
)
from frontend.web._market_data import (
    _fetch_market_bucket,
    _build_market_price_sections_live,
    _fetch_yahoo_index_rss_bucket,
    _fetch_yahoo_index_rss_item,
    _resolve_market_price_sections,
    _latest_settled_us_market_date,
    _previous_us_trading_day,
    _is_us_trading_day,
    _is_us_market_open_now,
    _is_us_market_day_closed_now,
    _resolve_market_quote,
    _fetch_market_news,
    _normalize_market_news_tag,
    _fetch_finnhub_market_news,
    _fetch_yahoo_rss_market_news,
    _fetch_direct_finnhub_quote,
    _fetch_yahoo_symbol_quote,
)
from frontend.web._market_data import (
    US_MARKET_TZ,
    MARKET_INDEX_CONFIG,
    MARKET_BOND_CONFIG,
    MARKET_COMMODITY_CONFIG,
    MARKET_CRYPTO_CONFIG,
)
from frontend.web._price_data import (
    _parse_ma_windows,
    _fetch_yahoo_daily_price_history,
    _fetch_finnhub_daily_price_history,
    _attach_moving_averages,
    _normalize_price_range_key,
    _price_range_config,
    _fetch_yahoo_price_history_by_range,
    _parse_yahoo_chart_payload,
    _fetch_price_points_for_range,
    _get_or_refresh_company_price_series,
    _pick_catchup_range,
    _start_date_for_range,
    _list_company_price_daily_points,
    _list_company_price_daily_points_all,
    _merge_trimmed_ma_points,
    _get_company_price_daily_latest_date,
    _upsert_company_price_daily_points,
    _trim_points_for_range,
    _fetch_stooq_daily_price_history,
    _attach_pct_change,
    _select_critical_price_points,
    _build_company_price_move_prompt,
    _ensure_company_price_daily_schema,
    _ensure_company_price_move_analysis_schema,
    _get_company_price_move_analysis,
    _upsert_company_price_move_analysis,
    _round_num,
    _int_or_none,
)
from frontend.web._market_analysis import (
    _ensure_market_price_snapshot_schema,
    _get_market_price_snapshot,
    _upsert_market_price_snapshot,
    _ensure_market_daily_summary_schema,
    _ensure_market_news_item_analysis_schema,
    _upsert_market_daily_summary,
    _upsert_market_news_item_analysis,
    _get_market_news_item_analyses,
    _get_market_daily_summaries,
    _ensure_market_price_analysis_schema,
    _parse_json_object_text,
    _normalize_market_prices_analysis_payload,
    _upsert_market_price_analysis,
    _get_market_price_analysis,
    _get_market_summary_dates,
    _build_market_news_summary_prompt,
    _build_market_prices_analysis_prompt,
    _build_market_prices_analysis_context,
    _generate_market_prices_analysis,
    _build_market_output_language_line,
    _build_market_single_news_prompt,
    _resolve_news_provider_for_model,
    _run_market_news_summary,
    _run_perplexity_text,
    _run_gemini_text,
    _group_news_items,
    _decode_news_content,
)

logger = logging.getLogger("uvicorn.error")
from market_agent.llms.news_registry import list_news_models
from market_agent.llms.registry import get_provider, list_models

app = FastAPI(
    title="MarketAgent Web Frontend",
    description="Lightweight HTML frontend powered by the shared MarketAgent stock API.",
)
mark_interrupted_jobs()

client = StockFrontendClient()

# MARKET_INDEX_CONFIG moved to _market_data.py


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


def _resolve_company_model(
    company_name: str,
    explicit_model: Optional[str],
    provider_name: str = "openai",
) -> str:
    selected = str(explicit_model or "").strip()
    if selected:
        return selected
    normalized_provider = str(provider_name or "openai").lower()
    if normalized_provider == "openai":
        return get_company_watchlist_model(company_name)
    return get_default_company_model(normalized_provider)


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
        "result_summary": "Calendar updated for the current month and next 2 months.",
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


def _run_market_prices_analysis_job(
    tracker: JobTracker,
    *,
    target_date: date,
    provider_name: str,
    model: str,
    output_language: str,
) -> Dict[str, Any]:
    tracker.mark_running(
        "generating_analysis",
        metrics={
            "target_date": target_date.isoformat(),
            "provider": provider_name,
            "model": model,
        },
    )
    analysis = _generate_market_prices_analysis(
        target_date=target_date,
        provider_name=provider_name,
        model=model,
        output_language=output_language,
        prompt_style="prices_v1",
    )
    output_json = analysis.get("output_json") if isinstance(analysis.get("output_json"), dict) else {}
    section_notes = output_json.get("section_notes") if isinstance(output_json.get("section_notes"), list) else []
    return {
        "result_summary": f"Market prices analysis generated for {target_date.isoformat()}",
        "metrics": {
            "target_date": target_date.isoformat(),
            "provider": provider_name,
            "model": model,
        },
        "counts": {
            "updated": 1,
            "section_note_count": len(section_notes),
        },
        "input_char_count": len(str(analysis.get("input_payload") or "")),
        "output_char_count": len(str(analysis.get("output_text") or "")),
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

# MARKET_BOND_CONFIG, MARKET_COMMODITY_CONFIG, MARKET_CRYPTO_CONFIG moved to _market_data.py

# US_MARKET_TZ moved to _market_data.py

MARKET_SUMMARY_DEFAULT_MODEL = dict(DEFAULT_PROVIDER_MODELS)


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
    return render_company_page(
        model_choices_by_provider=list_news_models(),
        default_company_model=DEFAULT_COMPANY_OPENAI_MODEL,
    )


@app.get("/charts", response_class=HTMLResponse)
async def charts_page() -> str:
    return render_charts_page()


@app.get("/earnings", response_class=HTMLResponse)
async def earnings_page() -> str:
    return render_earnings_page()


@app.get("/cost", response_class=HTMLResponse)
async def cost_page() -> str:
    return render_usage_page()



@app.get("/market", response_class=HTMLResponse)
async def market_page() -> str:
    market_today = datetime.now(US_MARKET_TZ).date().isoformat()
    return render_market_page(
        list_news_models(),
        default_date=market_today,
    )


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
        default_company_model=get_company_watchlist_model(company_name),
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


@app.get("/api/charts/layout")
async def get_charts_layout_api() -> Dict[str, Any]:
    companies = list_company_chart_layout_rows()
    return {
        "companies": companies,
        "company_names": [item["company_name"] for item in companies],
    }


@app.put("/api/charts/layout")
async def update_charts_layout_api(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    company_names = payload.get("company_names")
    if not isinstance(company_names, list):
        return {"error": "company_names must be a list"}
    if any(not isinstance(item, str) for item in company_names):
        return {"error": "company_names must contain only strings"}
    try:
        ordered = save_company_chart_layout(company_names)
    except ValueError as exc:
        return {"error": str(exc)}
    companies = list_company_chart_layout_rows()
    return {
        "ok": True,
        "company_names": ordered,
        "companies": companies,
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
    calendar_window: bool = Query(False),
) -> Dict[str, Any]:
    today = datetime.now().date()
    if calendar_window:
        start_date, end_date = resolve_market_macro_calendar_window()
        rows = list_market_macro_events(start_date=start_date, end_date=end_date, limit=500)
    elif lookback_days is None and lookahead_days is None:
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
    window_start, window_end = resolve_market_macro_calendar_window()
    rows = list_market_macro_events(
        start_date=window_start,
        end_date=window_end,
        limit=500,
    )
    return {"events": rows, "description": "Update the stored calendar for the current month and next 2 months.", **started}


@app.get("/api/market/prices/analysis")
async def get_market_prices_analysis_api(
    date: Optional[str] = Query(None),
    output_language: str = Query("zh-CN"),
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date() if date else datetime.now().date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    provider_name = provider or "openai"
    analysis = _get_market_price_analysis(
        analysis_date=target_date,
        provider=provider_name,
        prompt_style="prices_v1",
        output_language=output_language,
    )
    model_name = model or DEFAULT_MARKET_OPENAI_MODEL
    job = _safe_job(
        find_latest_job(
            job_key=_job_key("market_prices_analysis", target_date.isoformat(), provider_name, output_language, model_name),
            include_finished=True,
        )
    )
    return {"date": target_date.isoformat(), "analysis": analysis, "job": job}


@app.post("/api/market/prices/analysis/generate")
async def generate_market_prices_analysis_api(
    date: Optional[str] = Query(None),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        target_date = datetime.fromisoformat(date).date() if date else datetime.now().date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    provider_name = provider or "openai"
    model_name = model or DEFAULT_MARKET_OPENAI_MODEL
    analysis = _get_market_price_analysis(
        analysis_date=target_date,
        provider=provider_name,
        prompt_style="prices_v1",
        output_language=output_language,
    )
    started = _start_background_job(
        job_type="market_prices_analysis_generate",
        job_key=_job_key("market_prices_analysis", target_date.isoformat(), provider_name, output_language, model_name),
        provider=provider_name,
        model=model_name,
        output_language=output_language,
        prompt_style="prices_v1",
        target_date=target_date,
        worker=lambda tracker: _run_market_prices_analysis_job(
            tracker,
            target_date=target_date,
            provider_name=provider_name,
            model=model_name,
            output_language=output_language,
        ),
    )
    return {"date": target_date.isoformat(), "analysis": analysis, **started}


@app.post("/api/companies")
async def add_company(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    company_name = str(payload.get("company_name", "")).strip()
    selected_model = _resolve_company_model(company_name, payload.get("model"), "openai")
    if not company_name:
        return {"error": "company_name is required"}
    warmup = start_company_story_warmup(
        company_name,
        subscribe=True,
        provider_name="openai",
        model=selected_model,
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


@app.put("/api/company/{company_name}/llm-model")
async def update_company_llm_model_api(company_name: str, request: Request) -> Dict[str, Any]:
    payload = await request.json()
    try:
        row = update_company_watchlist_model(company_name, payload.get("model"))
    except ValueError as exc:
        return {"error": str(exc)}
    return {"ok": True, **row}


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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
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
            provider_name=selected_provider,
            model=selected_model,
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
    week_start, week_end = week_boundaries(selected)
    if selected_source == "openai":
        today = datetime.now().date()
        if week_end > today:
            week_end = today
    refresh_stats = refresh_company_news_for_range(
        company_name,
        start_date=week_start,
        end_date=week_end,
        source_name=selected_source,
        provider_name=selected_provider,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    try:
        selected = datetime.fromisoformat(week_date).date()
    except ValueError:
        return {"error": "week_date must be YYYY-MM-DD"}
    week_start, week_end = week_boundaries(selected)
    generate_weekly_report(
        company_name,
        start_date=week_start,
        end_date=week_end,
        output_language=output_language,
        provider_name=selected_provider,
        model=selected_model,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {"company": company_name, "groups": groups}


def _parse_month_window(month_value: str) -> Optional[tuple[date, date]]:
    text = str(month_value or "").strip()
    try:
        month_start = datetime.strptime(text, "%Y-%m").date()
    except ValueError:
        return None
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    return month_start, next_month - timedelta(days=1)


@app.get("/api/company/{company_name}/report/month")
async def get_company_monthly_report_api(
    company_name: str,
    month: str = Query(...),
    output_language: str = Query("zh-CN"),
) -> Dict[str, Any]:
    window = _parse_month_window(month)
    if not window:
        return {"error": "month must be YYYY-MM"}
    month_start, month_end = window
    report = get_news_report(company_name, beginning_date=month_start, end_date=month_end)
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {
        "company": company_name,
        "month": month,
        "report_start": month_start.isoformat(),
        "report_end": month_end.isoformat(),
        "report": report,
        "groups": groups,
    }


@app.post("/api/company/{company_name}/report/month")
async def generate_company_monthly_report_api(
    company_name: str,
    month: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    window = _parse_month_window(month)
    if not window:
        return {"error": "month must be YYYY-MM"}
    month_start, month_end = window
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    report = generate_monthly_report(
        company_name,
        month_start=month_start,
        month_end=month_end,
        output_language=output_language,
        provider_name=selected_provider,
        model=selected_model,
    )
    articles = get_company_news(company_name, output_language=output_language)
    groups = _group_news_items(company_name, articles)
    return {
        "company": company_name,
        "month": month,
        "report_start": month_start.isoformat(),
        "report_end": month_end.isoformat(),
        "report": report,
        "groups": groups,
    }


@app.post("/api/company/{company_name}/report/day")
async def generate_company_daily_report_api(
    company_name: str,
    date: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}
    stats = generate_company_daily_report(
        company_name,
        target_date=target_date,
        provider_name=selected_provider,
        model=selected_model,
        prompt_style="simple",
        output_language=output_language,
    )
    cluster_stats = refresh_company_daily_clusters(
        company_name,
        target_date=target_date,
        provider_name=selected_provider,
        model=selected_model,
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
    history = list_company_status_snapshots(
        company_name,
        provider_name=provider or "openai",
        prompt_style="simple",
        limit=10,
    )
    return {"company": company_name, "status": snapshot, "history_preview": history[:10]}


@app.get("/api/company/{company_name}/status/history")
async def list_company_status_history_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    history = list_company_status_snapshots(
        company_name,
        provider_name=provider or "openai",
        prompt_style="simple",
        limit=20,
    )
    return {"company": company_name, "snapshots": history}


@app.get("/api/company/{company_name}/status/{snapshot_id}")
async def get_company_status_snapshot_api(
    company_name: str,
    snapshot_id: int,
    prompt_style: str = Query("simple"),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    snapshot = get_company_status_snapshot(
        company_name,
        provider_name=provider or "openai",
        prompt_style="simple",
        snapshot_id=snapshot_id,
    )
    history = list_company_status_snapshots(
        company_name,
        provider_name=provider or "openai",
        prompt_style="simple",
        limit=10,
    )
    return {"company": company_name, "status": snapshot, "history_preview": history[:10]}


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
    selected_model = _resolve_company_model(company_name, model, provider_name)
    stats = _start_background_job(
        job_type="company_detailed_report",
        job_key=_job_key("detailed_report", company_name, provider_name, selected_model, output_language, max(30, int(window_days))),
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
    history = list_company_status_snapshots(
        company_name,
        provider_name=provider_name,
        prompt_style="simple",
        limit=10,
    )
    return {"company": company_name, "status": snapshot, "history_preview": history[:10], **stats}


@app.post("/api/company/{company_name}/price-intelligence/generate")
async def generate_company_price_intelligence_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, provider_name)
    stats = _start_background_job(
        job_type="company_price_intelligence",
        job_key=_job_key("price_intelligence", company_name, provider_name, selected_model, output_language),
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    stats = refresh_company_earnings(
        company_name,
        provider_name=selected_provider,
        model=selected_model,
        output_language=output_language,
    )
    return {"company": company_name, **stats}


# -- Earnings Report v2 (comprehensive LLM-driven) --

from market_agent.workflows.earnings_report import (
    fetch_earnings_report as _fetch_earnings_report,
    fetch_latest_earnings_report as _fetch_latest_earnings_report,
    refresh_earnings_report as _refresh_earnings_report,
    list_earnings_reports as _list_earnings_reports,
    get_earnings_report as _get_earnings_report,
    list_earnings_report_quarters as _list_earnings_report_quarters,
)


@app.get("/api/company/{company_name}/earnings/reports")
async def get_company_earnings_reports(
    company_name: str,
    limit: int = Query(12, ge=1, le=50),
) -> Dict[str, Any]:
    return {"company": company_name, "reports": _list_earnings_reports(company_name, limit=limit)}


@app.get("/api/company/{company_name}/earnings/reports/quarters")
async def get_company_earnings_report_quarters(
    company_name: str,
) -> Dict[str, Any]:
    return {"company": company_name, "quarters": _list_earnings_report_quarters(company_name)}


@app.post("/api/company/{company_name}/earnings/reports/fetch")
async def fetch_company_earnings_report(
    company_name: str,
    fiscal_year: str = Query(...),
    fiscal_quarter: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    result = _fetch_earnings_report(
        company_name,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        provider_name=selected_provider,
        model=selected_model,
        output_language=output_language,
    )
    return {"company": company_name, "report": result}


@app.post("/api/company/{company_name}/earnings/reports/fetch-latest")
async def fetch_company_latest_earnings_report(
    company_name: str,
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    result = _fetch_latest_earnings_report(
        company_name,
        provider_name=selected_provider,
        model=selected_model,
        output_language=output_language,
    )
    return {"company": company_name, "report": result}


@app.post("/api/company/{company_name}/earnings/reports/refresh")
async def refresh_company_earnings_report(
    company_name: str,
    fiscal_year: str = Query(...),
    fiscal_quarter: str = Query(...),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    result = _refresh_earnings_report(
        company_name,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        provider_name=selected_provider,
        model=selected_model,
        output_language=output_language,
    )
    return {"company": company_name, "report": result}


@app.get("/api/earnings/compare")
async def compare_earnings_reports(
    companies: str = Query(..., description="Comma-separated company names"),
    fiscal_year: Optional[str] = Query(None),
    fiscal_quarter: Optional[str] = Query(None),
) -> Dict[str, Any]:
    names = [n.strip() for n in companies.split(",") if n.strip()]
    results = {}
    for name in names:
        if fiscal_year and fiscal_quarter:
            report = _get_earnings_report(name, fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter)
            results[name] = report
        else:
            reports = _list_earnings_reports(name, limit=1)
            results[name] = reports[0] if reports else None
    return {"reports": results}


# -- LLM Usage Monitoring --

from market_agent.services.llm_usage import (
    get_usage_summary as _get_usage_summary,
    get_usage_by_company as _get_usage_by_company,
    get_usage_by_module as _get_usage_by_module,
    list_usage_requests as _list_usage_requests,
    get_daily_costs as _get_daily_costs,
)


@app.get("/api/llm-usage/summary")
async def llm_usage_summary(
    days: int = Query(7, ge=1, le=365),
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _get_usage_summary(days, target_date=date)


@app.get("/api/llm-usage/by-company")
async def llm_usage_by_company(
    days: int = Query(7, ge=1, le=365),
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return {"days": days, "companies": _get_usage_by_company(days, target_date=date)}


@app.get("/api/llm-usage/by-module")
async def llm_usage_by_module(
    days: int = Query(7, ge=1, le=365),
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return {"days": days, "modules": _get_usage_by_module(days, target_date=date)}


@app.get("/api/llm-usage/requests")
async def llm_usage_requests(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    company: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return {"days": days, "requests": _list_usage_requests(days, limit=limit, offset=offset, company=company, module=module, target_date=date)}


@app.get("/api/llm-usage/daily-costs")
async def llm_usage_daily_costs(
    days: int = Query(90, ge=1, le=365),
) -> Dict[str, Any]:
    return {"days": days, "daily": _get_daily_costs(days)}


@app.get("/api/company/{company_name}/stories")
async def get_company_stories_api(
    company_name: str,
    prompt_style: str = Query("simple"),
    output_language: str = Query("zh-CN"),
    model: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
) -> Dict[str, Any]:
    provider_name = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, provider_name)
    overview = get_company_story_overview(
        company_name,
        provider_name=provider_name,
        model=selected_model,
        prompt_style=prompt_style,
        output_language=output_language,
        start_warmup_if_needed=False,
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
    selected_model = _resolve_company_model(company_name, model, provider_name)
    result = _start_background_job(
        job_type="company_story_update",
        job_key=_job_key("company_story_update", company_name, provider_name, selected_model, prompt_style, output_language, window_days),
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
    selected_model = _resolve_company_model(company_name, model, provider_name)
    started = _start_background_job(
        job_type="company_story_rebuild_warmup",
        job_key=_job_key("company_story_rebuild", company_name, provider_name, selected_model, prompt_style, output_language),
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    story = create_company_story_from_news(
        company_name,
        target_date=target_date,
        story_title=str(payload.get("story_title") or "").strip(),
        news_item=payload.get("news_item") or {},
        provider_name=selected_provider,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    changed = attach_news_to_company_story(
        company_name,
        target_date=datetime.fromisoformat(str(payload.get("target_date"))).date(),
        story_key=story_key,
        news_item=payload.get("news_item") or {},
        provider_name=selected_provider,
        model=selected_model,
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
    selected_model = _resolve_company_model(company_name, model, provider_name)
    row = ask_company_story_question(
        company_name,
        story_key=story_key,
        question=question,
        provider_name=provider_name,
        model=selected_model,
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
    selected_model = _resolve_company_model(company_name, model, provider_name)
    row = merge_company_story_qa_answer(
        company_name,
        story_key=story_key,
        qa_id=qa_id,
        provider_name=provider_name,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    summarize_company_news_item(
        company_name,
        news_id=news_id,
        provider_name=selected_provider,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    result = filter_company_news_item(
        company_name,
        news_id=news_id,
        provider_name=selected_provider,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    stats = filter_company_news_day(
        company_name,
        target_date=target_date,
        limit=limit,
        provider_name=selected_provider,
        model=selected_model,
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
    selected_provider = provider or "openai"
    selected_model = _resolve_company_model(company_name, model, selected_provider)
    stats = generate_company_daily_report(
        company_name,
        target_date=target_date,
        provider_name=selected_provider,
        model=selected_model,
        prompt_style="simple",
        output_language=output_language,
    )
    cluster_stats = refresh_company_daily_clusters(
        company_name,
        target_date=target_date,
        provider_name=selected_provider,
        model=selected_model,
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


