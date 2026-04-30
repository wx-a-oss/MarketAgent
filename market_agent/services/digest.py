"""Build HTML email digest content for market and company reports."""

from __future__ import annotations

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
    .summary { line-height: 1.7; font-size: 14px; white-space: pre-wrap; }
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
        parts.append(f'<div class="card"><h2>Daily Analysis</h2><div class="summary">{_esc(latest.get("output_text", ""))}</div></div>')
    else:
        parts.append('<div class="card"><h2>Daily Analysis</h2><p class="no-data">No summary available.</p></div>')

    clusters = overview.get("clusters") or []
    if clusters:
        cluster_html = ""
        for c in clusters:
            cluster_html += f'<div class="cluster"><div class="cluster-title">{_esc(c.get("cluster_title", ""))}</div><div class="cluster-summary">{_esc(c.get("cluster_summary", ""))}</div></div>'
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
        parts.append(f'<div class="card"><h2>Daily Report</h2><div class="summary">{_esc(report["output_text"])}</div></div>')
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
            cluster_html += f'<div class="cluster"><div class="cluster-title">{_esc(c.get("cluster_title", ""))}</div><div class="cluster-summary">{_esc(c.get("cluster_summary", ""))}</div></div>'
        parts.append(f'<div class="card"><h2>News Clusters</h2>{cluster_html}</div>')

    subtitle = f"{company_name} — {target_date.isoformat()}"
    return _html_wrap(f"{company_name} Daily Report", subtitle, "\n".join(parts))
