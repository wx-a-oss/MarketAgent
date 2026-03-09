"""Shared orchestration for company news and story updates."""

from __future__ import annotations

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
    get_company_story_warmup_state,
    list_company_story_states,
    list_watchlist_companies,
    refresh_company_news_for_range,
    refresh_company_story_states,
)


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
        "stories": stories,
        "ongoing_stories": ongoing,
        "finished_stories": finished,
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
    if warmup.get("job_state") != "completed":
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
        "story_stats": story_stats,
    }


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
