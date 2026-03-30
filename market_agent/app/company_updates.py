"""Shared orchestration for company news and story updates."""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from market_agent.analysis.company.news import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_SOURCE,
    DEFAULT_STORY_WARMUP_DAYS,
    DEFAULT_STORY_WARMUP_SLICE_DAYS,
    add_company_to_watchlist,
    ensure_company_profile,
    ensure_company_story_warmup_started,
    generate_company_daily_report,
    get_latest_company_story_update_date,
    get_company_story_warmup_state,
    is_company_story_warmup_invalid,
    list_company_story_states,
    rebuild_company_story_warmup,
    refresh_company_daily_clusters,
    list_watchlist_companies,
    refresh_company_news_for_range,
    refresh_company_story_states,
)
from market_agent.analysis.company.news.service import _upsert_story_warmup_state
from .market_updates import run_market_daily_update

_COMPANY_UPDATE_THREADS: Dict[str, threading.Thread] = {}
_COMPANY_UPDATE_THREADS_LOCK = threading.Lock()


def start_company_story_warmup(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = DEFAULT_STORY_WARMUP_DAYS,
    slice_days: int = DEFAULT_STORY_WARMUP_SLICE_DAYS,
    subscribe: bool = False,
) -> Dict[str, Any]:
    if subscribe:
        add_company_to_watchlist(company_name)
    ensure_company_profile(company_name)
    return ensure_company_story_warmup_started(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        warmup_days=warmup_days,
        slice_days=slice_days,
    )


def rebuild_company_warmup(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    warmup_days: int = DEFAULT_STORY_WARMUP_DAYS,
    slice_days: int = DEFAULT_STORY_WARMUP_SLICE_DAYS,
) -> Dict[str, Any]:
    ensure_company_profile(company_name)
    return rebuild_company_story_warmup(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        warmup_days=warmup_days,
        slice_days=slice_days,
    )


def get_company_story_overview(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    start_warmup_if_needed: bool = True,
) -> Dict[str, Any]:
    if start_warmup_if_needed:
        warmup = start_company_story_warmup(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
    else:
        warmup = get_company_story_warmup_state(
            company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
    latest_story_date = get_latest_company_story_update_date(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    stories = list_company_story_states(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    ongoing = [
        story
        for story in stories
        if str(story.get("story_status") or "").strip().lower()
        not in {"resolved", "finished", "closed"}
    ]
    finished = [
        story
        for story in stories
        if str(story.get("story_status") or "").strip().lower()
        in {"resolved", "finished", "closed"}
    ]
    return {
        "company": company_name,
        "warmup": warmup,
        "latest_story_date": latest_story_date,
        "stories": stories,
        "ongoing_stories": ongoing,
        "finished_stories": finished,
    }


def start_company_daily_update(
    company_name: str,
    *,
    target_date: Optional[date] = None,
    source_name: str = "finnhub",
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    story_window_days: int = 21,
) -> Dict[str, Any]:
    ensure_company_profile(company_name)
    run_date = target_date or datetime.now(timezone.utc).date()
    warmup = get_company_story_warmup_state(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if warmup.get("job_state") != "completed" or is_company_story_warmup_invalid(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    ):
        warmup = start_company_story_warmup(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        return {
            "company_name": company_name,
            "target_date": run_date.isoformat(),
            "mode": "warmup_started",
            "warmup": warmup,
        }
    key = f"{company_name.lower()}|{provider_name}|{prompt_style}|{output_language}"
    with _COMPANY_UPDATE_THREADS_LOCK:
        existing = _COMPANY_UPDATE_THREADS.get(key)
        if existing and existing.is_alive():
            current = get_company_story_warmup_state(
                company_name,
                provider_name=provider_name,
                prompt_style=prompt_style,
                output_language=output_language,
            )
            return {
                "company_name": company_name,
                "target_date": run_date.isoformat(),
                "mode": "refresh_running",
                "warmup": current,
            }
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "running",
                "current_stage": "fetching_raw",
                "window_days": max(1, int(story_window_days)),
                "slice_days": 1,
                "analysis_started": False,
                "analysis_completed": False,
                "raw_fetched_count": 0,
                "raw_stored_count": 0,
                "filtered_kept_count": 0,
                "last_error": "",
                "failed_stage": "",
                "started_at": datetime.now(timezone.utc),
                "completed_at": None,
            },
        )
        thread = threading.Thread(
            target=_run_company_daily_update_job,
            kwargs={
                "company_name": company_name,
                "target_date": run_date,
                "source_name": source_name,
                "provider_name": provider_name,
                "model": model,
                "prompt_style": prompt_style,
                "output_language": output_language,
                "story_window_days": story_window_days,
            },
            daemon=True,
            name=f"company-update-{company_name}",
        )
        _COMPANY_UPDATE_THREADS[key] = thread
        thread.start()
    warmup = get_company_story_warmup_state(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    return {
        "company_name": company_name,
        "target_date": run_date.isoformat(),
        "mode": "refresh_started",
        "warmup": warmup,
    }


def run_company_daily_update(
    company_name: str,
    *,
    target_date: Optional[date] = None,
    source_name: str = "finnhub",
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    story_window_days: int = 21,
) -> Dict[str, Any]:
    ensure_company_profile(company_name)
    run_date = target_date or datetime.now(timezone.utc).date()
    warmup = get_company_story_warmup_state(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    if warmup.get("job_state") != "completed" or is_company_story_warmup_invalid(
        company_name,
        provider_name=provider_name,
        prompt_style=prompt_style,
        output_language=output_language,
    ):
        warmup = start_company_story_warmup(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        return {
            "company_name": company_name,
            "target_date": run_date.isoformat(),
            "mode": "warmup_started",
            "warmup": warmup,
        }

    refresh_stats = refresh_company_news_for_range(
        company_name,
        start_date=run_date,
        end_date=run_date,
        source_name=source_name,
        provider_name=provider_name,
        model=model,
    )
    daily_report_stats = generate_company_daily_report(
        company_name,
        target_date=run_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    cluster_stats = refresh_company_daily_clusters(
        company_name,
        target_date=run_date,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
    )
    story_stats = refresh_company_story_states(
        company_name,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        window_days=story_window_days,
    )
    return {
        "company_name": company_name,
        "target_date": run_date.isoformat(),
        "mode": "daily_update",
        "refresh_stats": refresh_stats,
        "daily_report_stats": daily_report_stats,
        "cluster_stats": cluster_stats,
        "story_stats": story_stats,
    }


def _run_company_daily_update_job(
    *,
    company_name: str,
    target_date: date,
    source_name: str,
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    story_window_days: int,
) -> None:
    key = f"{company_name.lower()}|{provider_name}|{prompt_style}|{output_language}"
    try:
        ensure_company_profile(company_name)
        refresh_stats = refresh_company_news_for_range(
            company_name,
            start_date=target_date,
            end_date=target_date,
            source_name=source_name,
            provider_name=provider_name,
            model=model,
        )
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "running",
                "current_stage": "fetching_raw",
                "window_days": max(1, int(story_window_days)),
                "slice_days": 1,
                "analysis_started": False,
                "analysis_completed": False,
                "raw_fetched_count": int(refresh_stats.get("fetched_total", 0)),
                "raw_stored_count": int(refresh_stats.get("stored_total", 0) or refresh_stats.get("fetched_total", 0)),
                "filtered_kept_count": int(refresh_stats.get("filtered_kept_count", 0)),
                "last_error": "",
                "failed_stage": "",
                "completed_at": None,
            },
        )
        generate_company_daily_report(
            company_name,
            target_date=target_date,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        refresh_company_daily_clusters(
            company_name,
            target_date=target_date,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "analyzing",
                "current_stage": "analyzing_stories",
                "window_days": max(1, int(story_window_days)),
                "slice_days": 1,
                "analysis_started": True,
                "analysis_completed": False,
                "last_error": "",
                "failed_stage": "",
                "completed_at": None,
            },
        )
        refresh_company_story_states(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            window_days=story_window_days,
        )
        stories = list_company_story_states(
            company_name,
            provider_name=provider_name,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        ongoing_count = sum(
            1
            for story in stories
            if str(story.get("story_status") or "").strip().lower()
            not in {"resolved", "finished", "closed"}
        )
        finished_count = len(stories) - ongoing_count
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "completed",
                "current_stage": "done",
                "window_days": max(1, int(story_window_days)),
                "slice_days": 1,
                "analysis_started": True,
                "analysis_completed": True,
                "ongoing_story_count": ongoing_count,
                "finished_story_count": finished_count,
                "last_error": "",
                "failed_stage": "",
                "completed_at": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:
        _upsert_story_warmup_state(
            company_name,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
            updates={
                "job_state": "failed",
                "current_stage": "idle",
                "window_days": max(1, int(story_window_days)),
                "slice_days": 1,
                "analysis_started": True,
                "analysis_completed": False,
                "last_error": str(exc),
                "failed_stage": "daily_update",
                "completed_at": datetime.now(timezone.utc),
            },
        )
    finally:
        with _COMPANY_UPDATE_THREADS_LOCK:
            _COMPANY_UPDATE_THREADS.pop(key, None)


def run_daily_updates_for_watchlist(
    *,
    target_date: Optional[date] = None,
    source_name: str = "finnhub",
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    story_window_days: int = 21,
    companies: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    names = companies or list_watchlist_companies()
    results: List[Dict[str, Any]] = []
    try:
        market_result = run_market_daily_update(
            target_date=target_date,
            provider_name=provider_name,
            model=model,
            prompt_style=prompt_style,
            output_language=output_language,
        )
        market_result["ok"] = True
    except Exception as exc:  # pragma: no cover
        market_result = {
            "scope": "market",
            "target_date": (target_date or datetime.now(timezone.utc).date()).isoformat(),
            "ok": False,
            "error": str(exc),
        }
    results.append({"scope": "market", **market_result})
    for company_name in names:
        try:
            result = run_company_daily_update(
                company_name,
                target_date=target_date,
                source_name=source_name,
                provider_name=provider_name,
                model=model,
                prompt_style=prompt_style,
                output_language=output_language,
                story_window_days=story_window_days,
            )
            result["ok"] = True
        except Exception as exc:  # pragma: no cover - worker should continue on failure
            result = {
                "company_name": company_name,
                "target_date": (target_date or datetime.now(timezone.utc).date()).isoformat(),
                "ok": False,
                "error": str(exc),
            }
        results.append(result)
    return results
