from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_agent.services.digest import (  # noqa: E402
    _md_to_html,
    _esc,
    _inline,
    build_market_digest_html,
    build_company_digest_html,
)


# ---------------------------------------------------------------------------
# _md_to_html unit tests
# ---------------------------------------------------------------------------


def test_md_to_html_returns_empty_for_none() -> None:
    assert _md_to_html(None) == ""
    assert _md_to_html("") == ""


def test_md_to_html_headers() -> None:
    assert "<h1>Title</h1>" in _md_to_html("# Title")
    assert "<h2>Sub</h2>" in _md_to_html("## Sub")
    assert "<h3>Third</h3>" in _md_to_html("### Third")


def test_md_to_html_bold_and_italic() -> None:
    result = _md_to_html("**bold** and *italic*")
    assert "<strong>bold</strong>" in result
    assert "<em>italic</em>" in result


def test_md_to_html_unordered_list() -> None:
    md = "- item one\n- item two\n- item three"
    result = _md_to_html(md)
    assert "<ul>" in result
    assert "</ul>" in result
    assert result.count("<li>") == 3


def test_md_to_html_ordered_list() -> None:
    md = "1. first\n2. second"
    result = _md_to_html(md)
    assert "<ol>" in result
    assert "</ol>" in result
    assert result.count("<li>") == 2


def test_md_to_html_mixed_content() -> None:
    md = "# Report\n\nSome text.\n\n- bullet one\n- bullet two\n\n## Section\n\nMore text."
    result = _md_to_html(md)
    assert "<h1>Report</h1>" in result
    assert "<p>Some text.</p>" in result
    assert "<ul>" in result
    assert "<h2>Section</h2>" in result
    assert "<p>More text.</p>" in result


def test_md_to_html_inline_code() -> None:
    result = _md_to_html("Use `foo()` here")
    assert "<code>foo()</code>" in result


def test_md_to_html_link() -> None:
    result = _md_to_html("[click](https://example.com)")
    assert 'href="https://example.com"' in result
    assert ">click</a>" in result


def test_md_to_html_escapes_html_entities() -> None:
    result = _md_to_html("A < B & C > D")
    assert "&lt;" in result
    assert "&amp;" in result
    assert "&gt;" in result


def test_md_to_html_list_closes_on_paragraph() -> None:
    md = "- item\n\nA paragraph."
    result = _md_to_html(md)
    assert "</ul>" in result
    idx_close = result.index("</ul>")
    idx_para = result.index("<p>A paragraph.</p>")
    assert idx_close < idx_para


# ---------------------------------------------------------------------------
# Digest builder tests (mock DB calls)
# ---------------------------------------------------------------------------


def test_build_market_digest_html_with_data(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_agent.workflows.market_news.get_market_daily_news_overview",
        lambda **kwargs: {
            "date": "2026-04-29",
            "raw_news": [],
            "summaries": [{"output_text": "## Summary\n\n- Point one\n- Point two"}],
            "clusters": [{"cluster_title": "AI Boom", "cluster_summary": "**Strong** growth in AI sector."}],
        },
    )
    monkeypatch.setattr(
        "market_agent.workflows.market_macro.list_market_macro_events",
        lambda **kwargs: [
            {"event_date_time": "2026-04-30T14:00", "event_name": "FOMC Rate Decision", "importance": "High", "actual_value": None, "consensus_value": "5.25%", "previous_value": "5.25%"},
        ],
    )
    html = build_market_digest_html(date(2026, 4, 29))
    assert "Market Digest" in html
    assert "<h2>Summary</h2>" in html
    assert "<li>Point one</li>" in html
    assert "<strong>Strong</strong>" in html
    assert "FOMC Rate Decision" in html
    assert "5.25%" in html


def test_build_market_digest_html_empty_data(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_agent.workflows.market_news.get_market_daily_news_overview",
        lambda **kwargs: {"date": "2026-04-29", "raw_news": [], "summaries": [], "clusters": []},
    )
    monkeypatch.setattr(
        "market_agent.workflows.market_macro.list_market_macro_events",
        lambda **kwargs: [],
    )
    html = build_market_digest_html(date(2026, 4, 29))
    assert "No summary available" in html
    assert "No macro events found" in html


def test_build_company_digest_html_with_data(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_agent.services.company.get_company_daily_report",
        lambda company_name, **kwargs: {"output_text": "# Nvidia Report\n\nStrong earnings beat."},
    )
    monkeypatch.setattr(
        "market_agent.services.company.list_company_daily_clusters",
        lambda company_name, **kwargs: [
            {"cluster_title": "GPU Demand", "cluster_summary": "- Data center growth\n- Gaming stable"},
        ],
    )
    html = build_company_digest_html("Nvidia", date(2026, 4, 29))
    assert "Nvidia Daily Report" in html
    assert "<h1>Nvidia Report</h1>" in html
    assert "<p>Strong earnings beat.</p>" in html
    assert "GPU Demand" in html
    assert "<li>Data center growth</li>" in html


def test_build_company_digest_html_no_report(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_agent.services.company.get_company_daily_report",
        lambda company_name, **kwargs: None,
    )
    monkeypatch.setattr(
        "market_agent.services.company.list_company_daily_clusters",
        lambda company_name, **kwargs: [],
    )
    html = build_company_digest_html("Nvidia", date(2026, 4, 29))
    assert "No daily report available" in html
