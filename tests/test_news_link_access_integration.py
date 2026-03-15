from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pytest
from openai import OpenAI

from market_agent.analysis.company.news.db import get_connection

OPENAI_DEFAULT_MODEL = "gpt-5-mini"
PERPLEXITY_DEFAULT_MODEL = "sonar-pro"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
MIN_SECONDS_BETWEEN_CALLS = 1.0


@dataclass
class ProviderResult:
    provider: str
    model: str
    ok: bool
    link_access: str
    summary: str
    raw_response: str
    error: str
    elapsed_sec: float


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Missing required env var: {name}")
    return value


def _fetch_cases_from_db(*, limit: int, company_name: str | None, source: str | None) -> List[Dict[str, str]]:
    query = """
        SELECT
            company_name,
            news_title,
            content,
            source_link,
            source,
            news_date_time
        FROM company_news_raw
        WHERE source_link IS NOT NULL
          AND source_link <> ''
          AND news_title IS NOT NULL
          AND news_title <> ''
    """
    params: List[object] = []
    if company_name:
        query += " AND company_name = %s"
        params.append(company_name)
    if source:
        query += " AND source = %s"
        params.append(source)
    query += " ORDER BY news_date_time DESC, id DESC LIMIT %s"
    params.append(max(3, limit))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

    cases: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        link = str(row["source_link"] or "").strip()
        title = str(row["news_title"] or "").strip()
        if not link.startswith("http"):
            continue
        key = (title.lower(), link.lower())
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "company_name": str(row["company_name"] or "").strip(),
                "news_title": title,
                "source_link": link,
                "metadata_summary": str(row["content"] or "").strip(),
                "source": str(row["source"] or "").strip(),
            }
        )
    if not cases:
        pytest.skip("No usable raw news rows in DB.")
    return cases[:limit]


def _build_comparison_prompt(item: Dict[str, str]) -> str:
    return (
        "You are validating whether a model can access a source link and summarize the article.\n"
        f"Company: {item['company_name']}\n"
        f"Title: {item['news_title']}\n"
        f"Source Link: {item['source_link']}\n"
        f"Metadata Summary: {item['metadata_summary']}\n\n"
        "Instructions:\n"
        "1. Try to open/read the source link.\n"
        "2. If that fails, search web for same article and use best available coverage.\n"
        "3. Return plain text in this exact format:\n"
        "LINK_ACCESS: yes|no|unknown\n"
        "SUMMARY: 4-8 concise sentences with key facts and implications.\n"
        "QUALITY_NOTES: 2-4 short bullets about confidence/coverage gaps.\n"
        "Do not return JSON."
    )


def _parse_model_output(text: str) -> tuple[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return "unknown", ""
    link_access = "unknown"
    summary = cleaned
    for line in cleaned.splitlines():
        lower = line.lower().strip()
        if lower.startswith("link_access:"):
            value = lower.split(":", 1)[1].strip()
            if value in {"yes", "no", "unknown"}:
                link_access = value
    if "SUMMARY:" in cleaned:
        summary = cleaned.split("SUMMARY:", 1)[1].strip()
    return link_access, summary


def _throttle(provider_name: str, last_call_at: Dict[str, float]) -> None:
    previous = last_call_at.get(provider_name, 0.0)
    now = time.perf_counter()
    elapsed = now - previous
    if previous > 0 and elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    last_call_at[provider_name] = time.perf_counter()


def _run_openai(*, item: Dict[str, str], model: str, api_key: str) -> ProviderResult:
    client = OpenAI(api_key=api_key)
    prompt = _build_comparison_prompt(item)
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            tools=[{"type": "web_search"}],
        )
        raw = (getattr(response, "output_text", "") or "").strip()
        link_access, summary = _parse_model_output(raw)
        return ProviderResult(
            provider="openai",
            model=model,
            ok=bool(summary),
            link_access=link_access,
            summary=summary,
            raw_response=raw,
            error="",
            elapsed_sec=round(time.perf_counter() - started, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(
            provider="openai",
            model=model,
            ok=False,
            link_access="unknown",
            summary="",
            raw_response="",
            error=str(exc),
            elapsed_sec=round(time.perf_counter() - started, 2),
        )


def _run_perplexity(*, item: Dict[str, str], model: str, api_key: str) -> ProviderResult:
    prompt = _build_comparison_prompt(item)
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        PERPLEXITY_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices") or []
        message = choices[0].get("message") if choices else {}
        raw = str((message or {}).get("content") or "").strip()
        link_access, summary = _parse_model_output(raw)
        return ProviderResult(
            provider="perplexity",
            model=model,
            ok=bool(summary),
            link_access=link_access,
            summary=summary,
            raw_response=raw,
            error="",
            elapsed_sec=round(time.perf_counter() - started, 2),
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return ProviderResult(
            provider="perplexity",
            model=model,
            ok=False,
            link_access="unknown",
            summary="",
            raw_response="",
            error=f"HTTP {exc.code}: {detail}",
            elapsed_sec=round(time.perf_counter() - started, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(
            provider="perplexity",
            model=model,
            ok=False,
            link_access="unknown",
            summary="",
            raw_response="",
            error=str(exc),
            elapsed_sec=round(time.perf_counter() - started, 2),
        )


def _run_gemini(*, item: Dict[str, str], model: str, api_key: str) -> ProviderResult:
    prompt = _build_comparison_prompt(item)
    url = (
        f"{GEMINI_API_BASE}/models/{urllib.parse.quote(model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
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
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        candidates = payload.get("candidates") or []
        content = candidates[0].get("content") if candidates else {}
        parts = (content or {}).get("parts") or []
        raw = "".join(str(part.get("text") or "") for part in parts).strip()
        link_access, summary = _parse_model_output(raw)
        return ProviderResult(
            provider="gemini",
            model=model,
            ok=bool(summary),
            link_access=link_access,
            summary=summary,
            raw_response=raw,
            error="",
            elapsed_sec=round(time.perf_counter() - started, 2),
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return ProviderResult(
            provider="gemini",
            model=model,
            ok=False,
            link_access="unknown",
            summary="",
            raw_response="",
            error=f"HTTP {exc.code}: {detail}",
            elapsed_sec=round(time.perf_counter() - started, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(
            provider="gemini",
            model=model,
            ok=False,
            link_access="unknown",
            summary="",
            raw_response="",
            error=str(exc),
            elapsed_sec=round(time.perf_counter() - started, 2),
        )


def _trim(text: str, max_chars: int = 1200) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]} ... [truncated]"


def _write_report(
    *,
    report_path: Path,
    cases: List[Dict[str, str]],
    by_case_results: List[List[ProviderResult]],
) -> None:
    lines: List[str] = []
    lines.append("# News Link Access Comparison Report")
    lines.append("")
    lines.append(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Cases: {len(cases)}")
    lines.append("")

    provider_totals: Dict[str, Dict[str, int]] = {}
    for case_results in by_case_results:
        for result in case_results:
            bucket = provider_totals.setdefault(
                result.provider, {"ok": 0, "link_yes": 0, "errors": 0}
            )
            if result.ok:
                bucket["ok"] += 1
            if result.link_access == "yes":
                bucket["link_yes"] += 1
            if result.error:
                bucket["errors"] += 1

    lines.append("## Provider Summary")
    lines.append("")
    lines.append("| Provider | Success | LINK_ACCESS=yes | Errors |")
    lines.append("|---|---:|---:|---:|")
    for provider_name in ["openai", "perplexity", "gemini"]:
        totals = provider_totals.get(provider_name, {"ok": 0, "link_yes": 0, "errors": 0})
        lines.append(
            f"| {provider_name} | {totals['ok']} | {totals['link_yes']} | {totals['errors']} |"
        )
    lines.append("")

    for idx, (item, case_results) in enumerate(zip(cases, by_case_results), start=1):
        lines.append(f"## Case {idx}")
        lines.append("")
        lines.append(f"- Company: {item['company_name']}")
        lines.append(f"- Source: {item['source']}")
        lines.append(f"- Title: {item['news_title']}")
        lines.append(f"- Link: {item['source_link']}")
        lines.append("")
        for result in case_results:
            lines.append(
                f"### {result.provider} ({result.model}) | ok={result.ok} "
                f"| link_access={result.link_access} | elapsed={result.elapsed_sec}s"
            )
            lines.append("")
            if result.error:
                lines.append(f"Error: {result.error}")
                lines.append("")
            lines.append("Summary:")
            lines.append("")
            lines.append(_trim(result.summary, 1500) or "(empty)")
            lines.append("")
            lines.append("Raw response preview:")
            lines.append("")
            lines.append("```text")
            lines.append(_trim(result.raw_response, 2500) or "(empty)")
            lines.append("```")
            lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.integration
def test_news_link_access_report_across_openai_perplexity_gemini() -> None:
    """
    Pull multiple raw news rows from DB and compare 3 providers on the same links.
    A markdown report is generated for side-by-side review.
    """
    openai_key = _required_env("OPENAI_API_KEY")
    perplexity_key = _required_env("PERPLEXITY_API_KEY")
    gemini_key = _required_env("GEMINI_API_KEY")

    sample_size = int(os.getenv("NEWS_TEST_SAMPLE_SIZE", "5"))
    company_filter = os.getenv("NEWS_TEST_COMPANY", "").strip() or None
    source_filter = os.getenv("NEWS_TEST_SOURCE", "finnhub").strip() or None
    report_path = Path(
        os.getenv(
            "NEWS_TEST_REPORT_PATH",
            "tests/output/news_link_access_report.md",
        )
    )

    openai_model = os.getenv("OPENAI_TEST_MODEL", OPENAI_DEFAULT_MODEL).strip() or OPENAI_DEFAULT_MODEL
    perplexity_model = (
        os.getenv("PERPLEXITY_TEST_MODEL", PERPLEXITY_DEFAULT_MODEL).strip()
        or PERPLEXITY_DEFAULT_MODEL
    )
    gemini_model = os.getenv("GEMINI_TEST_MODEL", GEMINI_DEFAULT_MODEL).strip() or GEMINI_DEFAULT_MODEL

    cases = _fetch_cases_from_db(
        limit=max(3, sample_size),
        company_name=company_filter,
        source=source_filter,
    )
    last_call_at: Dict[str, float] = {}
    by_case_results: List[List[ProviderResult]] = []

    for item in cases:
        case_results: List[ProviderResult] = []

        _throttle("openai", last_call_at)
        case_results.append(
            _run_openai(item=item, model=openai_model, api_key=openai_key)
        )

        _throttle("perplexity", last_call_at)
        case_results.append(
            _run_perplexity(item=item, model=perplexity_model, api_key=perplexity_key)
        )

        _throttle("gemini", last_call_at)
        case_results.append(
            _run_gemini(item=item, model=gemini_model, api_key=gemini_key)
        )

        by_case_results.append(case_results)

    _write_report(
        report_path=report_path,
        cases=cases,
        by_case_results=by_case_results,
    )

    total_success = sum(
        1 for case_results in by_case_results for result in case_results if result.ok
    )
    assert total_success > 0, (
        f"No successful provider responses. See report: {report_path}"
    )
