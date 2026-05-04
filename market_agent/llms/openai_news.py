"""OpenAI-backed news provider."""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from market_agent.config.models import DEFAULT_OPENAI_MODEL
from market_agent.llms.interfaces import NewsProvider
from market_agent.llms.prompts import (
    build_fetch_news_analysis_prompt,
    build_news_analysis_prompt_simple,
    build_news_analysis_prompt_structured,
    build_news_filter_prompt,
    build_weekly_report_prompt,
)
from market_agent.llms.openai_analysis import chat_completion

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

DEFAULT_NEWS_MODEL = DEFAULT_OPENAI_MODEL
WEB_SEARCH_ENV_FLAG = "OPENAI_USE_WEB_SEARCH"
ANALYSIS_LOG_PREVIEW_MAX_CHARS = 4000
logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class OpenAINewsProvider(NewsProvider):
    api_key: str
    model: str = DEFAULT_NEWS_MODEL
    temperature: float = 0.2
    timeout_sec: int = 60
    use_web_search: bool = False
    name: str = "openai"

    def fetch_news(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        # OpenAI requires explicit web_search tool usage for online retrieval.
        # We always use web_search here regardless of `use_web_search` flag.
        if not self.use_web_search:
            logger.info(
                "OpenAI fetch_news forcing web_search: company=%s range=%s..%s",
                company_name,
                start_date,
                end_date,
            )
        return _fetch_news_with_web_search(
            api_key=self.api_key,
            model=self.model,
            company_name=company_name,
            start_date=start_date,
            end_date=end_date,
        )

    def generate_text(
        self,
        *,
        prompt: str,
    ) -> str:
        if self.use_web_search:
            return generate_text_with_web_search(
                api_key=self.api_key,
                model=self.model,
                prompt=prompt,
                timeout_sec=self.timeout_sec,
            )
        return chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[{"role": "user", "content": prompt}],
        )

    def fetch_weekly_report(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
        articles: Iterable[Dict[str, Any]],
        output_language: str = "en",
    ) -> Dict[str, Any]:
        prompt = _build_weekly_report_prompt(
            company_name,
            start_date,
            end_date,
            articles,
            output_language=output_language,
        )
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        payload = _safe_json(response)
        return payload if isinstance(payload, dict) else {}

    def analyze_news_items(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
        items: Iterable[Dict[str, Any]],
        analysis_prompt: str = "simple",
    ) -> List[Dict[str, Any]]:
        serialized = list(items)
        prompt = _build_analysis_prompt(
            company_name,
            start_date,
            end_date,
            serialized,
            analysis_prompt=analysis_prompt,
        )
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        selected_prompt = str(analysis_prompt or "simple").strip().lower()
        logger.info(
            "OpenAI analyze raw response: company=%s prompt=%s chars=%d preview=%s",
            company_name,
            selected_prompt,
            len(response),
            _preview_text(response, ANALYSIS_LOG_PREVIEW_MAX_CHARS),
        )
        payload = _safe_json(response)
        normalized = _normalize_news_items(payload)
        logger.info(
            "OpenAI analyze parsed response: company=%s prompt=%s items=%d",
            company_name,
            selected_prompt,
            len(normalized),
        )
        return _merge_analysis_items(serialized, normalized)

    def filter_news_items(
        self,
        *,
        company_name: str,
        items: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        serialized = list(items)
        titles = [str(item.get("news_title") or "").strip() for item in serialized]
        prompt = _build_filter_prompt(company_name, titles)
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        payload = _safe_json(response)
        return _merge_filter_items(
            [{"news_title": title} for title in titles],
            payload,
        )


def resolve_openai_news_provider(
    *,
    api_key: str | None = None,
    model: str = DEFAULT_NEWS_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
    use_web_search: bool | None = None,
) -> OpenAINewsProvider:
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise RuntimeError("OpenAI API key is required. Set OPENAI_API_KEY.")
    if use_web_search is None:
        use_web_search = _use_web_search()
    return OpenAINewsProvider(
        api_key=resolved_key,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
        use_web_search=use_web_search,
    )


def _use_web_search() -> bool:
    value = os.getenv(WEB_SEARCH_ENV_FLAG, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_news_prompt(company_name: str, start_date: str, end_date: str) -> str:
    return build_fetch_news_analysis_prompt(
        company_name,
        start_date,
        end_date,
    )


def _build_weekly_report_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    articles: Iterable[Dict[str, Any]],
    *,
    output_language: str = "en",
) -> str:
    return build_weekly_report_prompt(
        company_name,
        start_date,
        end_date,
        articles,
        output_language=output_language,
    )


def _build_analysis_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    items: List[Dict[str, Any]],
    *,
    analysis_prompt: str = "simple",
) -> str:
    selected = str(analysis_prompt or "simple").strip().lower()
    if selected == "simple":
        return build_news_analysis_prompt_simple(
            company_name,
            items,
        )
    return build_news_analysis_prompt_structured(
        company_name,
        start_date,
        end_date,
        items,
    )


def _build_filter_prompt(
    company_name: str,
    items: List[Any],
) -> str:
    return build_news_filter_prompt(company_name, items)


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        return []


def _normalize_news_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("articles"), list):
            return [item for item in payload["articles"] if isinstance(item, dict)]
    return []


def _merge_analysis_items(
    originals: List[Dict[str, Any]],
    analyses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not analyses:
        return originals

    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    merged: List[Dict[str, Any]] = [dict(item) for item in originals]
    by_title_date: Dict[tuple[str, str], int] = {}
    by_title: Dict[str, int] = {}

    for idx, item in enumerate(originals):
        title = _norm(item.get("news_title"))
        dt = _norm(item.get("news_date_time"))
        if title:
            by_title[title] = idx
            by_title_date[(title, dt)] = idx

    immutable_fields = {
        "news_date_time",
        "news_title",
        "original_content",
        "news_source",
        "news_source_link",
    }
    for analysis in analyses:
        title = _norm(analysis.get("news_title"))
        dt = _norm(analysis.get("news_date_time"))
        idx = by_title_date.get((title, dt))
        if idx is None:
            idx = by_title.get(title)
        if idx is not None:
            for key, value in analysis.items():
                if key in immutable_fields:
                    continue
                merged[idx][key] = value
        else:
            merged.append(dict(analysis))

    return merged


def _merge_filter_items(
    originals: List[Dict[str, Any]],
    filtered: Any,
) -> List[Dict[str, Any]]:
    if not filtered:
        return originals

    merged: List[Dict[str, Any]] = [dict(item) for item in originals]
    if isinstance(filtered, list) and filtered and all(
        isinstance(entry, bool) for entry in filtered
    ):
        for idx, keep_value in enumerate(filtered):
            if idx >= len(merged):
                break
            merged[idx]["keep_for_company"] = bool(keep_value)
        return merged

    if not isinstance(filtered, list):
        return merged

    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    by_title: Dict[str, int] = {}
    for idx, item in enumerate(originals):
        title = _norm(item.get("news_title"))
        if title:
            by_title[title] = idx

    for decision in filtered:
        if not isinstance(decision, dict):
            continue
        title = _norm(decision.get("news_title"))
        idx = by_title.get(title)
        if idx is None:
            continue
        merged[idx]["keep_for_company"] = decision.get("keep_for_company")
    return merged


def _build_web_search_prompt(
    company_name: str, start_date: str, end_date: str
) -> str:
    return build_fetch_news_analysis_prompt(
        company_name,
        start_date,
        end_date,
    )


def _build_web_search_fallback_prompt(
    company_name: str, start_date: str, end_date: str
) -> str:
    return (
        _build_web_search_prompt(company_name, start_date, end_date)
        + "If initial retrieval is sparse, run additional web searches with alternate keywords "
        + "(company alias, ticker, earnings, guidance, product, legal, regulation, analyst, M&A) "
        + "and return all materially relevant items found in this date range.\n"
    )


def _dedupe_news_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        title = str(item.get("news_title") or "").strip().lower()
        news_dt = str(item.get("news_date_time") or "").strip().lower()
        link = str(item.get("news_source_link") or "").strip().lower()
        key = (title, news_dt, link)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _preview_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated {len(text) - max_chars} chars]"


def _run_web_search_once(
    *,
    client: OpenAI,
    model: str,
    prompt: str,
) -> List[Dict[str, Any]]:
    response = client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    output_text = getattr(response, "output_text", "")
    return _normalize_news_items(_safe_json(output_text))


def generate_text_with_web_search(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_sec: int = 120,
) -> str:
    import time as _time
    if OpenAI is None:
        raise RuntimeError("openai package is required for web_search tool usage.")
    started = _time.perf_counter()
    client = OpenAI(api_key=api_key, timeout=timeout_sec, max_retries=0)
    response = client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    elapsed_ms = int((_time.perf_counter() - started) * 1000)
    output_text = getattr(response, "output_text", "") or ""
    usage = getattr(response, "usage", None)
    try:
        from market_agent.llms.usage_context import get_usage_context
        from market_agent.services.llm_usage import log_llm_usage
        ctx = get_usage_context()
        pt = getattr(usage, "input_tokens", None) if usage else None
        ct = getattr(usage, "output_tokens", None) if usage else None
        log_llm_usage(
            provider="openai", model=model, **ctx,
            prompt_tokens=pt,
            completion_tokens=ct,
            input_char_count=len(prompt),
            output_char_count=len(output_text),
            response_time_ms=elapsed_ms,
            used_web_search=True,
        )
    except Exception:
        pass
    return output_text


def _fetch_news_with_web_search(
    *,
    api_key: str,
    model: str,
    company_name: str,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    if OpenAI is None:
        raise RuntimeError("openai package is required for web_search tool usage.")
    client = OpenAI(api_key=api_key, max_retries=0)
    prompt = _build_web_search_prompt(company_name, start_date, end_date)
    logger.info(
        "OpenAI web_search fetch start: company=%s range=%s..%s",
        company_name,
        start_date,
        end_date,
    )
    first_pass = _run_web_search_once(client=client, model=model, prompt=prompt)
    merged = list(first_pass)
    logger.info(
        "OpenAI web_search fetch pass1: company=%s items=%d",
        company_name,
        len(first_pass),
    )
    if len(first_pass) < 3:
        fallback_prompt = _build_web_search_fallback_prompt(
            company_name, start_date, end_date
        )
        second_pass = _run_web_search_once(
            client=client,
            model=model,
            prompt=fallback_prompt,
        )
        merged.extend(second_pass)
        logger.info(
            "OpenAI web_search fetch pass2: company=%s items=%d",
            company_name,
            len(second_pass),
        )
    deduped = _dedupe_news_items(_normalize_news_items(merged))
    logger.info(
        "OpenAI web_search fetch done: company=%s items=%d",
        company_name,
        len(deduped),
    )
    return deduped


__all__ = ["OpenAINewsProvider", "resolve_openai_news_provider", "DEFAULT_NEWS_MODEL"]
