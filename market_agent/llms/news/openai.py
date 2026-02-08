"""OpenAI-backed news provider."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from market_agent.llms.news.interfaces import NewsProvider
from market_agent.llms.openai import chat_completion

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

DEFAULT_NEWS_MODEL = "gpt-5.2"
WEB_SEARCH_ENV_FLAG = "OPENAI_USE_WEB_SEARCH"


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
        if self.use_web_search:
            return _fetch_news_with_web_search(
                api_key=self.api_key,
                model=self.model,
                company_name=company_name,
                start_date=start_date,
                end_date=end_date,
            )
        prompt = _build_news_prompt(company_name, start_date, end_date)
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": prompt},
            ],
        )
        return _normalize_news_items(_safe_json(response))

    def fetch_weekly_report(
        self,
        *,
        company_name: str,
        start_date: str,
        end_date: str,
        articles: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt = _build_weekly_report_prompt(
            company_name, start_date, end_date, articles
        )
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON."},
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
    ) -> List[Dict[str, Any]]:
        serialized = list(items)
        prompt = _build_analysis_prompt(company_name, start_date, end_date, serialized)
        response = chat_completion(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": prompt},
            ],
        )
        payload = _safe_json(response)
        return _merge_analysis_items(serialized, _normalize_news_items(payload))


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


def _system_prompt() -> str:
    return (
        "You are a financial news analyst. Return ONLY valid JSON. "
        "The response must be a JSON array of objects with keys: "
        "news_date_time, news_title, original_content, summary, facts, "
        "viewpoint, bias, reasoning, short_term_impact, long_term_impact, "
        "uncertainties, priced_in, insider_signals, trends, sentiment, "
        "news_source, news_source_link."
    )


def _build_news_prompt(company_name: str, start_date: str, end_date: str) -> str:
    return (
        "Please retrieve all news related to {company} from {begin} to {end}. "
        "For each article, provide:\n"
        "The news title\n"
        "The original content (concise factual excerpt)\n"
        "A concise summary of the content\n"
        "Key objective facts\n"
        "The author's subjective viewpoint (if any)\n"
        "The author's subjective bias (if any)\n"
        "Logical analysis and whether the reasoning is sound\n"
        "Short-term impact\n"
        "Long-term impact\n"
        "Major uncertainties involved\n"
        "An assessment of how much of this information is likely already priced into the stock\n"
        "Any potential insider signals or implications inferred from the news\n"
        "Possible future trends for the stock\n"
        "Whether the news is bullish or bearish for the stock\n"
    ).format(
        company=company_name,
        begin=start_date,
        end=end_date,
    )


def _build_weekly_report_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    articles: Iterable[Dict[str, Any]],
) -> str:
    serialized = list(articles)
    return (
        "You are compiling a weekly news report for {company} covering {begin} to {end}.\n"
        "Use the news items below as the ONLY source of truth.\n"
        "Return a JSON object with these keys, each value must be an array of bullet points:\n"
        "summary, facts, viewpoint, bias, reasoning, short_term_impact, long_term_impact, "
        "uncertainties, priced_in, insider_signals, trends, sentiment.\n"
        "Do not omit any section. Use concise bullet points.\n"
        "News items JSON:\n{items}\n"
    ).format(
        company=company_name,
        begin=start_date,
        end=end_date,
        items=json.dumps(serialized),
    )


def _build_analysis_prompt(
    company_name: str,
    start_date: str,
    end_date: str,
    items: List[Dict[str, Any]],
) -> str:
    return (
        "Analyze the news items for {company} from {begin} to {end}.\n"
        "Return ONLY a JSON array with the same length and order as the input.\n"
        "Each object must include: summary, facts, viewpoint, bias, reasoning, "
        "short_term_impact, long_term_impact, uncertainties, priced_in, "
        "insider_signals, trends, sentiment.\n"
        "Input items JSON:\n{items}\n"
    ).format(
        company=company_name,
        begin=start_date,
        end=end_date,
        items=json.dumps(items),
    )


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
    if len(analyses) != len(originals):
        return originals
    merged: List[Dict[str, Any]] = []
    for original, analysis in zip(originals, analyses):
        combined = dict(original)
        combined.update(analysis)
        merged.append(combined)
    return merged


def _build_web_search_prompt(
    company_name: str, start_date: str, end_date: str
) -> str:
    return (
        "Find the most important news from {begin} to {end} about {company}.\n"
        "Return ONLY a JSON array of objects. Each object must include:\n"
        "news_date_time (ISO 8601 date or datetime)\n"
        "news_title\n"
        "original_content (concise factual excerpt)\n"
        "summary\n"
        "facts\n"
        "viewpoint\n"
        "bias\n"
        "reasoning\n"
        "short_term_impact\n"
        "long_term_impact\n"
        "uncertainties\n"
        "priced_in\n"
        "insider_signals\n"
        "trends\n"
        "sentiment\n"
        "news_source\n"
        "news_source_link\n"
        "Requirements:\n"
        "- 5–10 items max\n"
        "- include date + source link per item\n"
        "- dedupe repeats\n"
        "- explain why it matters\n"
    ).format(
        company=company_name,
        begin=start_date,
        end=end_date,
    )


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
    client = OpenAI(api_key=api_key)
    prompt = _build_web_search_prompt(company_name, start_date, end_date)
    response = client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    output_text = getattr(response, "output_text", "")
    return _normalize_news_items(_safe_json(output_text))


__all__ = ["OpenAINewsProvider", "resolve_openai_news_provider", "DEFAULT_NEWS_MODEL"]
