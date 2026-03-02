"""Gemini-backed news provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from market_agent.llms.news.interfaces import NewsProvider
from market_agent.llms.news.prompts import (
    build_news_analysis_prompt_simple,
    build_news_analysis_prompt_structured,
    build_news_filter_prompt,
    build_weekly_report_prompt,
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass(slots=True)
class GeminiNewsProvider(NewsProvider):
    api_key: str
    model: str = DEFAULT_GEMINI_MODEL
    temperature: float = 0.2
    timeout_sec: int = 60
    name: str = "gemini"

    def fetch_news(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Gemini fetch_news is not implemented; use source=openai/finnhub."
        )

    def generate_text(
        self,
        *,
        prompt: str,
    ) -> str:
        return _gemini_generate(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            prompt=prompt,
            use_google_search=True,
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
        prompt = build_weekly_report_prompt(
            company_name=company_name,
            start_date=start_date,
            end_date=end_date,
            articles=articles,
            output_language=output_language,
        )
        text = _gemini_generate(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            prompt=prompt,
            use_google_search=False,
        )
        payload = _safe_json(text)
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
        selected = str(analysis_prompt or "simple").strip().lower()
        if selected == "simple":
            prompt = build_news_analysis_prompt_simple(company_name, serialized)
        else:
            prompt = build_news_analysis_prompt_structured(
                company_name=company_name,
                start_date=start_date,
                end_date=end_date,
                items=serialized,
            )
        text = self.generate_text(prompt=prompt)
        parsed = _safe_json(text)
        normalized = _normalize_news_items(parsed)
        return _merge_analysis_items(serialized, normalized)

    def filter_news_items(
        self,
        *,
        company_name: str,
        items: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        serialized = list(items)
        titles = [str(item.get("news_title") or "").strip() for item in serialized]
        prompt = build_news_filter_prompt(company_name, titles)
        text = _gemini_generate(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            prompt=prompt,
            use_google_search=False,
        )
        parsed = _safe_json(text)
        return _merge_filter_items([{"news_title": title} for title in titles], parsed)


def resolve_gemini_news_provider(
    *,
    api_key: str | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = 60,
) -> GeminiNewsProvider:
    resolved_key = api_key or os.getenv("GEMINI_API_KEY")
    if not resolved_key:
        raise RuntimeError("Gemini API key is required. Set GEMINI_API_KEY.")
    return GeminiNewsProvider(
        api_key=resolved_key,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )


def _gemini_generate(
    *,
    api_key: str,
    model: str,
    temperature: float,
    timeout_sec: int,
    prompt: str,
    use_google_search: bool,
) -> str:
    url = (
        f"{GEMINI_API_BASE}/models/{urllib.parse.quote(model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if use_google_search:
        payload["tools"] = [{"google_search": {}}]

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini API connection error: {exc}") from exc

    candidates = response_payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini API returned no candidates.")
    first = candidates[0].get("content") or {}
    parts = first.get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini API returned empty content.")
    return text


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
    if isinstance(payload, dict) and isinstance(payload.get("articles"), list):
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
        if idx is None:
            merged.append(dict(analysis))
            continue
        for key, value in analysis.items():
            if key in immutable_fields:
                continue
            merged[idx][key] = value
    return merged


def _merge_filter_items(
    originals: List[Dict[str, Any]],
    filtered: Any,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = [dict(item) for item in originals]
    if not filtered:
        return merged
    if isinstance(filtered, list) and filtered and all(
        isinstance(entry, bool) for entry in filtered
    ):
        for idx, keep_value in enumerate(filtered):
            if idx >= len(merged):
                break
            merged[idx]["keep_for_company"] = bool(keep_value)
        return merged
    return merged


__all__ = ["GeminiNewsProvider", "resolve_gemini_news_provider", "DEFAULT_GEMINI_MODEL"]
