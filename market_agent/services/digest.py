"""Build HTML email digest content for market and company reports."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from market_agent.utils.week import week_boundaries


# ---------------------------------------------------------------------------
# Shared HTML helpers
# ---------------------------------------------------------------------------

_STYLE = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1a1a1a; background: #f5f5f5; margin: 0; padding: 0; }
    .container { max-width: 680px; margin: 0 auto; padding: 24px 16px; }
    .card { background: #ffffff; border-radius: 8px; padding: 20px 24px; margin-bottom: 16px; border: 1px solid #e5e5e5; }
    h1 { font-size: 22px; margin: 0 0 4px; }
    h2 { font-size: 17px; margin: 20px 0 8px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 6px; }
    h3 { font-size: 15px; margin: 14px 0 6px; color: #444; }
    .subtitle { font-size: 13px; color: #888; margin-bottom: 16px; }
    .summary { line-height: 1.7; font-size: 14px; }
    .summary h1 { font-size: 18px; margin: 16px 0 6px; }
    .summary h2 { font-size: 16px; margin: 14px 0 6px; border: none; padding: 0; }
    .summary h3 { font-size: 14px; margin: 12px 0 4px; }
    .summary ul, .summary ol { padding-left: 20px; margin: 6px 0; }
    .summary li { margin-bottom: 4px; }
    .summary p { margin: 8px 0; }
    .summary strong { font-weight: 600; }
    .summary em { font-style: italic; }
    .summary code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
    .cluster { margin-bottom: 14px; }
    .cluster-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
    .cluster-summary { font-size: 13px; color: #444; line-height: 1.6; }
    table.macro { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
    table.macro th { text-align: left; padding: 6px 8px; background: #f9f9f9; border-bottom: 2px solid #ddd; font-weight: 600; }
    table.macro td { padding: 6px 8px; border-bottom: 1px solid #eee; }
    .no-data { color: #999; font-style: italic; font-size: 13px; }
    .footer { text-align: center; font-size: 11px; color: #aaa; margin-top: 24px; }
</style>
"""


def _html_wrap(title: str, subtitle: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{_STYLE}</head>
<body><div class="container">
<div class="card"><h1>{title}</h1><div class="subtitle">{subtitle}</div></div>
{body}
<div class="footer">MarketAgent Daily Digest</div>
</div></body></html>"""


def _esc(text: str | None) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_html(text: str | None) -> str:
    """Convert markdown text to HTML. Handles headers, bold, italic, lists, code, links."""
    if not text:
        return ""
    text = _esc(text)
    lines = text.split("\n")
    html_lines: list[str] = []
    in_list: str | None = None  # "ul" or "ol"

    for line in lines:
        stripped = line.strip()

        # Close list if line doesn't continue it
        if in_list and not re.match(r"^[-*] |^\d+\. ", stripped) and stripped:
            html_lines.append(f"</{in_list}>")
            in_list = None

        # Headers
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            html_lines.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue

        # Unordered list
        m = re.match(r"^[-*]\s+(.*)", stripped)
        if m:
            if in_list != "ul":
                if in_list:
                    html_lines.append(f"</{in_list}>")
                html_lines.append("<ul>")
                in_list = "ul"
            html_lines.append(f"<li>{_inline(m.group(1))}</li>")
            continue

        # Ordered list
        m = re.match(r"^\d+\.\s+(.*)", stripped)
        if m:
            if in_list != "ol":
                if in_list:
                    html_lines.append(f"</{in_list}>")
                html_lines.append("<ol>")
                in_list = "ol"
            html_lines.append(f"<li>{_inline(m.group(1))}</li>")
            continue

        # Blank line
        if not stripped:
            if in_list:
                html_lines.append(f"</{in_list}>")
                in_list = None
            continue

        # Regular paragraph
        html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append(f"</{in_list}>")

    return "\n".join(html_lines)


def _inline(text: str) -> str:
    """Convert inline markdown: bold, italic, code, links."""
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" style="color:#2563eb">\1</a>', text)
    return text


# ---------------------------------------------------------------------------
# Market digest
# ---------------------------------------------------------------------------

def build_market_digest_html(
    target_date: date,
    output_language: str = "zh-CN",
) -> str:
    from market_agent.workflows.market_news import get_market_daily_news_overview
    from market_agent.workflows.market_macro import list_market_macro_events

    overview = get_market_daily_news_overview(
        target_date=target_date,
        output_language=output_language,
    )

    parts: list[str] = []

    summaries = overview.get("summaries") or []
    if summaries:
        latest = summaries[-1]
        parts.append(f'<div class="card"><h2>Daily Analysis</h2><div class="summary">{_md_to_html(latest.get("output_text", ""))}</div></div>')
    else:
        parts.append('<div class="card"><h2>Daily Analysis</h2><p class="no-data">No summary available.</p></div>')

    clusters = overview.get("clusters") or []
    if clusters:
        cluster_html = ""
        for c in clusters:
            cluster_html += f'<div class="cluster"><div class="cluster-title">{_esc(c.get("cluster_title", ""))}</div><div class="cluster-summary">{_md_to_html(c.get("cluster_summary", ""))}</div></div>'
        parts.append(f'<div class="card"><h2>News Clusters</h2>{cluster_html}</div>')

    week_start, _ = week_boundaries(target_date)
    next_week_end = week_start + timedelta(days=13)
    events = list_market_macro_events(start_date=week_start, end_date=next_week_end)
    parts.append(_build_macro_table(events, week_start, next_week_end))

    subtitle = target_date.isoformat()
    return _html_wrap("Market Digest", subtitle, "\n".join(parts))


def _build_macro_table(events: List[Dict[str, Any]], start: date, end: date) -> str:
    if not events:
        return f'<div class="card"><h2>Macro Calendar ({start.isoformat()} ~ {end.isoformat()})</h2><p class="no-data">No macro events found.</p></div>'
    rows = ""
    for ev in events:
        dt = str(ev.get("event_date_time") or "")[:16]
        name = _esc(ev.get("event_name"))
        actual = _esc(ev.get("actual_value")) or "—"
        consensus = _esc(ev.get("consensus_value")) or "—"
        previous = _esc(ev.get("previous_value")) or "—"
        importance = _esc(ev.get("importance")) or ""
        rows += f"<tr><td>{dt}</td><td>{name}</td><td>{importance}</td><td>{actual}</td><td>{consensus}</td><td>{previous}</td></tr>\n"
    return f"""<div class="card"><h2>Macro Calendar ({start.isoformat()} ~ {end.isoformat()})</h2>
<table class="macro"><thead><tr><th>Date</th><th>Event</th><th>Importance</th><th>Actual</th><th>Consensus</th><th>Previous</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


# ---------------------------------------------------------------------------
# Company digest
# ---------------------------------------------------------------------------

def build_company_digest_html(
    company_name: str,
    target_date: date,
    output_language: str = "zh-CN",
) -> str:
    from market_agent.services.company import (
        get_company_daily_report,
        list_company_daily_clusters,
    )

    parts: list[str] = []

    report = get_company_daily_report(company_name, report_date=target_date)
    if report and report.get("output_text"):
        parts.append(f'<div class="card"><h2>Daily Report</h2><div class="summary">{_md_to_html(report["output_text"])}</div></div>')
    else:
        parts.append('<div class="card"><h2>Daily Report</h2><p class="no-data">No daily report available.</p></div>')

    clusters = list_company_daily_clusters(
        company_name,
        target_date=target_date,
        output_language=output_language,
    )
    if clusters:
        cluster_html = ""
        for c in clusters:
            cluster_html += f'<div class="cluster"><div class="cluster-title">{_esc(c.get("cluster_title", ""))}</div><div class="cluster-summary">{_md_to_html(c.get("cluster_summary", ""))}</div></div>'
        parts.append(f'<div class="card"><h2>News Clusters</h2>{cluster_html}</div>')

    subtitle = f"{company_name} — {target_date.isoformat()}"
    return _html_wrap(f"{company_name} Daily Report", subtitle, "\n".join(parts))


# ---------------------------------------------------------------------------
# Consolidated digest (single email with LLM summary)
# ---------------------------------------------------------------------------

def build_consolidated_digest_html(
    target_date: date,
    *,
    company_names: list[str],
    output_language: str = "zh-CN",
) -> str:
    from market_agent.workflows.market_news import get_market_daily_news_overview
    from market_agent.workflows.market_macro import list_market_macro_events
    from market_agent.services.company import (
        get_company_daily_report,
        list_company_daily_clusters,
    )
    from market_agent.llms.news_registry import get_news_provider
    from market_agent.llms.usage_context import usage_context
    from market_agent.config.models import DEFAULT_MARKET_OPENAI_MODEL

    # Gather all raw data
    overview = get_market_daily_news_overview(target_date=target_date, output_language=output_language)
    market_summary = ""
    summaries = overview.get("summaries") or []
    if summaries:
        market_summary = summaries[-1].get("output_text", "")
    market_clusters = overview.get("clusters") or []

    week_start, _ = week_boundaries(target_date)
    next_week_end = week_start + timedelta(days=13)
    macro_events = list_market_macro_events(start_date=week_start, end_date=next_week_end)

    company_data: list[dict] = []
    for name in company_names:
        report = get_company_daily_report(name, report_date=target_date)
        clusters = list_company_daily_clusters(name, target_date=target_date, output_language=output_language)
        company_data.append({
            "company": name,
            "daily_report": (report or {}).get("output_text", ""),
            "clusters": [{"title": c.get("cluster_title", ""), "summary": c.get("cluster_summary", "")} for c in clusters],
        })

    # Build context for LLM
    context_parts = [f"Date: {target_date.isoformat()}"]
    if market_summary:
        context_parts.append(f"## Market Daily Summary\n{market_summary}")
    if market_clusters:
        cluster_text = "\n".join([f"- {c.get('cluster_title', '')}: {c.get('cluster_summary', '')}" for c in market_clusters])
        context_parts.append(f"## Market News Clusters\n{cluster_text}")
    if macro_events:
        macro_text = "\n".join([f"- {e.get('event_date_time', '')[:10]} {e.get('event_name', '')} (importance: {e.get('importance', 'N/A')})" for e in macro_events[:15]])
        context_parts.append(f"## Macro Events (this week + next)\n{macro_text}")
    for cd in company_data:
        if cd["daily_report"] or cd["clusters"]:
            parts = []
            if cd["daily_report"]:
                parts.append(cd["daily_report"])
            if cd["clusters"]:
                parts.append("\n".join([f"- {c['title']}: {c['summary']}" for c in cd["clusters"]]))
            context_parts.append(f"## {cd['company']} Daily News\n" + "\n".join(parts))

    full_context = "\n\n".join(context_parts)

    lang_instruction = "Output in Simplified Chinese. Keep company names, tickers, and numbers in English." if output_language != "en" else "Output in English."

    prompt = (
        "You are a senior market analyst writing a daily briefing email.\n"
        "Based on the following data, produce a concise executive briefing with:\n\n"
        "1. **Market Summary** — 3-5 bullet points of today's most important market developments, ranked by impact\n"
        "2. **Macro Calendar** — any high-importance events this week/next week (skip if none)\n"
        "3. **Company Updates** — for each company, 2-4 bullet points of the most impactful news/developments, ranked by importance\n"
        "4. **Key Risks & Watchlist** — anything that needs attention or follow-up\n\n"
        "Rules:\n"
        "- Rank everything by importance — most impactful items first\n"
        "- Be concise — bullet points, not paragraphs\n"
        "- Flag anything with outsized potential impact with [HIGH IMPACT]\n"
        "- Skip items with no real news value\n"
        f"- {lang_instruction}\n\n"
        "Format as markdown.\n\n"
        f"---\n\n{full_context}"
    )

    # Call LLM to summarize
    provider = get_news_provider("openai", model=DEFAULT_MARKET_OPENAI_MODEL, timeout_sec=120)
    with usage_context("daily_briefing_email", module="market"):
        briefing_text = provider.generate_text(prompt=prompt)

    # Build HTML
    briefing_html = _md_to_html(briefing_text)
    parts_html = [f'<div class="card"><div class="summary">{briefing_html}</div></div>']

    return _html_wrap("Daily Briefing", target_date.isoformat(), "\n".join(parts_html))
