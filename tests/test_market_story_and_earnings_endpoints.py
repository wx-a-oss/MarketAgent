from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.calendar_page import render_calendar_page  # noqa: E402
from frontend.web.company_detail_page import render_company_detail_page  # noqa: E402
from frontend.web.market_page import render_market_page  # noqa: E402
from frontend.web.notes_page import render_notes_page  # noqa: E402
from frontend.web.server import app  # noqa: E402
from market_agent.app.company_updates import run_daily_updates_for_watchlist  # noqa: E402
from market_agent.app import market_updates  # noqa: E402
from market_agent.analysis.company.news import service as company_news_service  # noqa: E402
from market_agent.analysis.stock.single_stock import analyze_single_stock_sections  # noqa: E402


def test_market_stories_endpoint_returns_groups(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_market_story_overview",
        lambda provider_name="openai", prompt_style="simple", output_language="zh-CN": {
            "warmup": {"job_state": "completed", "ongoing_story_count": 1, "finished_story_count": 1},
            "ongoing_stories": [{"story_title": "Rates repricing", "happened_text": "- A", "happening_text": "- B", "next_text": "- C"}],
            "finished_stories": [{"story_title": "Past election overhang", "happened_text": "- A", "happening_text": "- B", "next_text": "- C"}],
        },
    )
    client = TestClient(app)
    response = client.get("/api/market/stories")
    assert response.status_code == 200
    payload = response.json()
    assert payload["warmup"]["job_state"] == "completed"
    assert len(payload["ongoing_stories"]) == 1
    assert len(payload["finished_stories"]) == 1


def test_market_stories_warmup_endpoint_returns_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.start_market_story_warmup",
        lambda **kwargs: {"job_state": "running", "current_stage": "fetching_raw"},
    )
    monkeypatch.setattr(
        "frontend.web.server.get_market_story_overview",
        lambda provider_name="openai", prompt_style="simple", output_language="zh-CN": {
            "warmup": {"job_state": "running"},
            "ongoing_stories": [],
            "finished_stories": [],
        },
    )
    client = TestClient(app)
    response = client.post("/api/market/stories/warmup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["warmup"]["job_state"] == "running"


def test_market_stories_refresh_endpoint_returns_updated_overview(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._start_background_job",
        lambda **kwargs: {
            "mode": "started",
            "job": {"job_id": 11, "status": "running", "current_stage": "routing_backlog"},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.get_market_story_overview",
        lambda provider_name="openai", prompt_style="simple", output_language="zh-CN": {
            "warmup": {"job_state": "completed"},
            "ongoing_stories": [{"story_title": "Oil shock"}],
            "finished_stories": [{"story_title": "Old election overhang"}],
        },
    )
    client = TestClient(app)
    response = client.post("/api/market/stories/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "started"
    assert payload["job"]["job_id"] == 11
    assert payload["ongoing_stories"][0]["story_title"] == "Oil shock"


def test_market_macro_refresh_endpoint_returns_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._start_background_job",
        lambda **kwargs: {
            "mode": "started",
            "job": {"job_id": 12, "status": "running", "current_stage": "extending_calendar"},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.list_market_macro_events",
        lambda start_date=None, end_date=None, limit=80: [
            {"event_name": "CPI", "event_date_time": "2026-03-12T12:30:00+00:00"},
            {"event_name": "FOMC", "event_date_time": "2026-03-18T18:00:00+00:00"},
        ],
    )
    client = TestClient(app)
    response = client.post("/api/market/macro/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "started"
    assert payload["job"]["job_id"] == 12
    assert len(payload["events"]) == 2
    assert payload["description"] == "Refresh the stored calendar for the next 3 months."


def test_market_macro_endpoint_returns_date_window(monkeypatch) -> None:
    captured = {}

    def fake_list(start_date=None, end_date=None, limit=80):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["limit"] = limit
        return [{"event_name": "CPI", "event_date_time": "2026-03-12T12:30:00+00:00"}]

    monkeypatch.setattr(
        "frontend.web.server.list_market_macro_events",
        fake_list,
    )
    client = TestClient(app)
    response = client.get("/api/market/macro")
    assert response.status_code == 200
    payload = response.json()
    assert payload["events"][0]["event_name"] == "CPI"
    assert captured["start_date"] is None
    assert captured["end_date"] is None
    assert "start_date" in payload
    assert "end_date" in payload


def test_company_earnings_endpoint_returns_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.list_company_earnings",
        lambda company_name: [
            {
                "company_name": company_name,
                "ticker": "GOOGL",
                "earnings_date": "2026-02-03",
                "analysis_text": "earnings analysis",
            }
        ],
    )
    client = TestClient(app)
    response = client.get("/api/company/Google/earnings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Google"
    assert payload["events"][0]["ticker"] == "GOOGL"


def test_company_earnings_refresh_endpoint_returns_stats(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.refresh_company_earnings",
        lambda company_name, provider_name="openai", model="gpt-5-mini", output_language="zh-CN": {
            "updated": 4,
            "event_count": 4,
            "company_name": company_name,
        },
    )
    client = TestClient(app)
    response = client.post("/api/company/Google/earnings/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Google"
    assert payload["updated"] == 4


def test_company_price_intelligence_generate_endpoint_returns_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._start_background_job",
        lambda **kwargs: {
            "mode": "started",
            "job": {"job_id": 13, "status": "running", "current_stage": "building_price_intelligence"},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.get_company_price_intelligence_run",
        lambda company_name, run_id=None: {
            "id": 7,
            "company_name": company_name,
            "as_of_date": "2026-03-12",
            "provider": "openai",
            "model": "gpt-5-mini",
            "context_window_days": 730,
            "focus_window_days": 60,
            "bottom_line": "Near fair with improving fundamentals",
            "fair_price_zone": {"low": 110, "mid": 120, "high": 130, "basis": "blend"},
            "price_position": {"label": "near_fair", "explanation": "Trading near fair zone midpoint"},
            "technical_view": {"summary": "Trend intact"},
            "fundamental_market_view": {"summary": "Demand remains strong"},
            "synthesis_view": {"summary": "Constructive but not cheap"},
            "short_horizon": {"stance": "hold", "confidence": 0.6, "rationale": ["momentum remains positive"]},
            "medium_horizon": {"stance": "buy", "confidence": 0.7, "rationale": ["earnings support"]},
            "long_horizon": {"stance": "buy", "confidence": 0.8, "rationale": ["AI leadership"]},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.list_company_price_intelligence_runs",
        lambda company_name, limit=10: [
            {"id": 7, "company_name": company_name, "created_at": "2026-03-12T10:00:00+00:00"},
            {"id": 6, "company_name": company_name, "created_at": "2026-03-11T10:00:00+00:00"},
        ],
    )
    client = TestClient(app)
    response = client.post("/api/company/Google/price-intelligence/generate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "started"
    assert payload["job"]["job_id"] == 13
    assert payload["run"]["bottom_line"] == "Near fair with improving fundamentals"
    assert payload["run"]["medium_horizon"]["stance"] == "buy"
    assert payload["history_preview"][0]["id"] == 7


def test_company_price_intelligence_history_endpoint_returns_runs(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.list_company_price_intelligence_runs",
        lambda company_name, limit=20: [
            {"id": 7, "company_name": company_name, "created_at": "2026-03-12T10:00:00+00:00"},
            {"id": 6, "company_name": company_name, "created_at": "2026-03-11T10:00:00+00:00"},
        ],
    )
    client = TestClient(app)
    response = client.get("/api/company/Google/price-intelligence/history")
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Google"
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["id"] == 7


def test_company_status_endpoint_returns_history_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_company_status_snapshot",
        lambda company_name, provider_name="openai", prompt_style="simple", snapshot_id=None: {
            "id": 21,
            "as_of_date": "2026-03-29",
            "output_text": "technical report",
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.list_company_status_snapshots",
        lambda company_name, provider_name="openai", prompt_style="simple", limit=10: [
            {"id": 21, "created_at": "2026-03-29 09:00:00", "price_position_summary": "near resistance"},
            {"id": 20, "created_at": "2026-03-28 09:00:00", "price_position_summary": "inside range"},
        ],
    )
    client = TestClient(app)
    response = client.get("/api/company/Google/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["id"] == 21
    assert payload["history_preview"][0]["id"] == 21


def test_company_story_warmup_invalid_when_running_state_is_stale(monkeypatch) -> None:
    stale_time = datetime.now(timezone.utc) - timedelta(hours=4)
    monkeypatch.setattr(
        company_news_service,
        "get_company_story_warmup_state",
        lambda *args, **kwargs: {
            "job_state": "running",
            "current_stage": "fetching_raw",
            "analysis_started": False,
            "analysis_completed": False,
            "raw_fetched_count": 12,
            "failed_stage": "",
            "last_error": "",
            "started_at": stale_time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": stale_time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    monkeypatch.setattr(
        company_news_service,
        "get_company_profile",
        lambda company_name: {"ticker": "GOOGL"},
    )
    assert company_news_service.is_company_story_warmup_invalid("Google") is True


def test_ensure_company_story_warmup_started_invalidates_stale_running_state(monkeypatch) -> None:
    stale_time = datetime.now(timezone.utc) - timedelta(hours=4)
    state = {
        "job_state": "running",
        "current_stage": "fetching_raw",
        "window_days": 10,
        "slice_days": 10,
        "analysis_started": True,
        "analysis_completed": True,
        "raw_fetched_count": 0,
        "raw_stored_count": 0,
        "filtered_kept_count": 0,
        "ongoing_story_count": 0,
        "finished_story_count": 0,
        "retry_count": 0,
        "started_at": stale_time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": stale_time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    upserts = []
    thread_calls = []
    call_count = {"value": 0}

    def fake_get_state(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return dict(state)
        return {"job_state": "running", "current_stage": "fetching_raw"}

    monkeypatch.setattr(company_news_service, "get_company_story_warmup_state", fake_get_state)
    monkeypatch.setattr(company_news_service, "get_company_profile", lambda company_name: {"ticker": "GOOGL"})
    monkeypatch.setattr(
        company_news_service,
        "_upsert_story_warmup_state",
        lambda company_name, **kwargs: upserts.append(kwargs["updates"]) or {"job_state": "failed"},
    )
    monkeypatch.setattr(
        company_news_service,
        "_ensure_story_warmup_thread",
        lambda company_name, **kwargs: thread_calls.append((company_name, kwargs)),
    )

    company_news_service.ensure_company_story_warmup_started("Google")

    assert upserts
    assert upserts[0]["job_state"] == "failed"
    assert "stale" in upserts[0]["last_error"].lower() or "inconsistent" in upserts[0]["last_error"].lower()
    assert thread_calls


def test_company_story_warmup_rate_limit_marks_failed(monkeypatch) -> None:
    now = datetime.now(timezone.utc).date()
    updates = []

    class DummySource:
        def fetch_news(self, company_name, start_date, end_date):
            raise RuntimeError("429 rate limit")

    monkeypatch.setattr(company_news_service, "_ensure_news_schema", lambda: None)
    monkeypatch.setattr(company_news_service, "_build_story_warmup_slices", lambda **kwargs: [(now, now)])
    monkeypatch.setattr(
        company_news_service,
        "get_company_story_warmup_state",
        lambda *args, **kwargs: {
            "analysis_started": False,
            "analysis_completed": False,
            "retry_count": 0,
            "raw_fetched_count": 0,
            "raw_stored_count": 0,
            "filtered_kept_count": 0,
            "ongoing_story_count": 0,
            "finished_story_count": 0,
            "completed_slices": 0,
            "last_completed_slice_end_date": "",
        },
    )
    monkeypatch.setattr(company_news_service, "get_news_provider", lambda *args, **kwargs: object())
    monkeypatch.setattr(company_news_service, "get_news_source", lambda name: DummySource())
    monkeypatch.setattr(company_news_service, "_build_fetch_ranges_for_slice", lambda *args, **kwargs: [(now, now)])
    monkeypatch.setattr(company_news_service, "_resolve_company_ticker", lambda company_name: "GOOGL")
    monkeypatch.setattr(company_news_service, "_news_items_from_provider", lambda *args, **kwargs: [])
    monkeypatch.setattr(company_news_service, "_store_articles", lambda *args, **kwargs: None)
    monkeypatch.setattr(company_news_service, "_filter_company_news_range_raw", lambda **kwargs: 0)
    monkeypatch.setattr(company_news_service, "DEFAULT_STORY_WARMUP_MAX_RETRIES", 1)
    monkeypatch.setattr(company_news_service, "DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC", 1)
    monkeypatch.setattr(
        company_news_service,
        "_upsert_story_warmup_state",
        lambda company_name, **kwargs: updates.append(kwargs["updates"]) or kwargs["updates"],
    )

    company_news_service._run_company_story_warmup_job_inner(
        company_name="Google",
        provider_name="openai",
        model="gpt-5.4",
        prompt_style="simple",
        output_language="zh-CN",
        warmup_days=10,
        slice_days=10,
    )

    assert updates
    assert updates[-1]["job_state"] == "failed"
    assert "rate limit" in updates[-1]["last_error"].lower()
    assert updates[-1]["completed_at"] is not None


def test_company_status_snapshot_endpoint_returns_selected_history_item(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_company_status_snapshot",
        lambda company_name, provider_name="openai", prompt_style="simple", snapshot_id=None: {
            "id": int(snapshot_id or 0),
            "as_of_date": "2026-03-28",
            "output_text": "older technical report",
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.list_company_status_snapshots",
        lambda company_name, provider_name="openai", prompt_style="simple", limit=10: [
            {"id": 22, "created_at": "2026-03-29 09:00:00", "price_position_summary": "breakout test"},
            {"id": 21, "created_at": "2026-03-28 09:00:00", "price_position_summary": "pullback"},
        ],
    )
    client = TestClient(app)
    response = client.get("/api/company/Google/status/21")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["id"] == 21
    assert payload["history_preview"][1]["id"] == 21


def test_company_indicators_analyze_endpoint_no_longer_depends_on_output_language(monkeypatch) -> None:
    class _FakeSnapshot:
        symbol = "NVDA"

    monkeypatch.setattr("frontend.web.server.get_company_profile", lambda company_name: {"ticker": "NVDA"})
    monkeypatch.setattr("frontend.web.server.client.query", lambda ticker: _FakeSnapshot())
    monkeypatch.setattr("frontend.web.server.get_provider", lambda provider, model="gpt-4o-mini": object())

    captured: dict[str, object] = {}

    def _fake_analyze(snapshot, provider=None, **kwargs):
        captured["kwargs"] = kwargs
        return {"sections": {"Quote": {"summary": "中文", "highlights": [], "risks": [], "questions": []}}}

    monkeypatch.setattr("frontend.web.server.analyze_single_stock_sections", _fake_analyze)

    client = TestClient(app)
    response = client.post("/api/company/Nvidia/indicators/analyze")
    assert response.status_code == 200
    assert "output_language" not in captured["kwargs"]


def test_indicator_analysis_skips_quote_section() -> None:
    class _Base:
        def as_dict(self):
            return {
                "symbol": "NVDA",
                "quote_timestamp": "2026-03-29T12:00:00Z",
                "previous_close": 120.0,
                "rsi": 58.0,
            }

    class _Snapshot:
        symbol = "NVDA"
        base = _Base()

    class _Provider:
        name = "fake"

        def __init__(self):
            self.sections = []

        def analyze_section(self, payload):
            self.sections.append(payload["section"])
            return {"summary": "x", "highlights": [], "risks": [], "questions": []}

    provider = _Provider()
    result = analyze_single_stock_sections(_Snapshot(), provider=provider)

    assert "Quote" not in provider.sections
    assert "Quote" not in result["sections"]
    assert "Price & Returns" in result["sections"]


def test_company_analysis_inputs_drop_story_and_earnings_context(monkeypatch) -> None:
    monkeypatch.setattr(
        company_news_service,
        "get_company_daily_reports_for_range",
        lambda *args, **kwargs: [
            {"report_date": "2026-03-10", "output_text": "Report 1"},
            {"report_date": "2026-03-11", "output_text": "Report 2"},
        ],
    )
    monkeypatch.setattr(
        company_news_service,
        "_build_company_status_raw_news_fallback",
        lambda *args, **kwargs: [{"news_title": "Fallback"}],
    )
    monkeypatch.setattr(
        company_news_service,
        "_build_company_status_price_context",
        lambda *args, **kwargs: {"point_count": 12, "latest_close": 123.4, "recent_points": [{"trade_date": "2026-03-11", "close": 123.4}]},
    )
    monkeypatch.setattr(
        company_news_service,
        "_build_company_status_market_story_context",
        lambda *args, **kwargs: [{"story_title": "Rates repricing"}],
    )
    monkeypatch.setattr(
        company_news_service,
        "_build_company_status_market_daily_summary_context",
        lambda *args, **kwargs: [{"summary_date": "2026-03-11", "output_text": "Market summary"}],
    )
    detailed = company_news_service._build_company_price_intelligence_input(
        "Nvidia",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 11),
        provider_name="openai",
        output_language="zh-CN",
    )
    quick = company_news_service._build_company_quick_price_intelligence_input(
        "Nvidia",
        context_start=date(2025, 3, 12),
        focus_start=date(2026, 1, 11),
        end_date=date(2026, 3, 11),
        provider_name="openai",
        output_language="zh-CN",
    )

    for payload in (detailed, quick):
        assert "active_company_stories" not in payload
        assert "recent_story_updates" not in payload
        assert "earnings_context" not in payload
        assert "macro_context" not in payload
        assert payload["price_context"]["point_count"] == 12
        assert payload["input_coverage"]["price_point_count"] == 12

    assert "daily_reports" not in detailed
    assert "raw_news_fallback" not in detailed
    assert "market_daily_summaries" not in detailed
    assert detailed["input_coverage"]["recent_point_count"] == 1
    assert detailed["input_coverage"]["input_item_count"] == 12

    assert quick["daily_reports"]
    assert quick["raw_news_fallback"]
    assert quick["market_daily_summaries"]
    assert quick["input_coverage"]["daily_report_count"] == 2
    assert quick["input_coverage"]["raw_news_fallback_count"] == 1
    assert quick["input_coverage"]["market_summary_count"] == 1


def test_market_page_renders_overview_and_stories_subviews() -> None:
    html = render_market_page(
        {"openai": ["gpt-5-mini"], "gemini": ["gemini-2.5-pro"]},
        default_date="2026-03-12",
    )
    assert "Overview" in html
    assert "Stories" in html
    assert "market-stories-view" in html
    assert "refresh-market-stories" in html
    assert "market-date-stories" not in html
    assert "Macro Calendar" not in html


def test_notes_page_renders_notes_ui() -> None:
    html = render_notes_page()
    assert ">Notes<" in html
    assert "Save Note" in html
    assert "/api/notes" in html


def test_notes_list_endpoint_returns_notes(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.list_user_notes",
        lambda tag=None: [
            {
                "id": 1,
                "title": "Nvidia setup",
                "body_markdown": "- Watch **AI** spending",
                "validity_state": "valid",
                "tags": ["Nvidia", "AI"],
            }
        ],
    )
    client = TestClient(app)
    response = client.get("/api/notes", params={"tag": "nvidia"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"][0]["title"] == "Nvidia setup"


def test_notes_create_endpoint_returns_note(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.create_user_note",
        lambda title, body_markdown, tags=None: {
            "id": 2,
            "title": title,
            "body_markdown": body_markdown,
            "tags": ["Fed"],
            "validity_state": "valid",
        },
    )
    client = TestClient(app)
    response = client.post("/api/notes", json={"title": "Macro", "body": "- Watch rates", "tags": "Fed"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["note"]["title"] == "Macro"


def test_notes_invalidate_endpoint_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.invalidate_user_note",
        lambda note_id, reason=None: {
            "id": note_id,
            "title": "Wrong thesis",
            "validity_state": "invalid",
            "invalidation_reason": reason or "",
        },
    )
    client = TestClient(app)
    response = client.post("/api/notes/7/invalidate", json={"reason": "Thesis broken"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["note"]["validity_state"] == "invalid"


def test_calendar_page_renders_calendar_controls() -> None:
    html = render_calendar_page()
    assert ">Calendar<" in html
    assert "macro releases" in html
    assert "refresh-market-macro" in html
    assert "Refresh 3 Months" in html


def test_update_company_ticker_returns_user_error_when_data_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.set_company_ticker",
        lambda company_name, ticker: (_ for _ in ()).throw(
            ValueError("ticker cannot be changed after company news or story data has been fetched")
        ),
    )
    client = TestClient(app)
    response = client.put("/api/company/Nvidia/ticker", json={"ticker": "NVDA"})
    assert response.status_code == 200
    payload = response.json()
    assert "cannot be changed" in payload["error"]


def test_company_story_rebuild_warmup_endpoint_returns_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._start_background_job",
        lambda **kwargs: {
            "mode": "started",
            "job": {"job_id": 14, "status": "running", "current_stage": "fetching_raw"},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.get_company_story_overview",
        lambda company_name, **kwargs: {
            "company": company_name,
            "warmup": {"job_state": "running", "current_stage": "fetching_raw"},
            "ongoing_stories": [],
            "finished_stories": [],
        },
    )
    client = TestClient(app)
    response = client.post("/api/company/Nvidia/stories/rebuild-warmup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "started"
    assert payload["job"]["job_id"] == 14


def test_company_story_refresh_endpoint_returns_warmup_started(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._start_background_job",
        lambda **kwargs: {
            "mode": "already_running",
            "job": {"job_id": 15, "status": "running", "current_stage": "fetching_raw"},
        },
    )
    monkeypatch.setattr(
        "frontend.web.server.get_company_story_overview",
        lambda company_name, **kwargs: {
            "company": company_name,
            "warmup": {"job_state": "running", "current_stage": "fetching_raw"},
            "ongoing_stories": [],
            "finished_stories": [],
        },
    )
    client = TestClient(app)
    response = client.post("/api/company/Nvidia/stories/refresh")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "already_running"
    assert payload["job"]["job_id"] == 15


def test_build_fetch_ranges_for_slice_skips_covered_past_days() -> None:
    today = date(2026, 3, 16)
    covered_days = {
        date(2026, 3, 7),
        date(2026, 3, 8),
        date(2026, 3, 10),
        date(2026, 3, 11),
    }

    def fake_has_raw(company_name: str, target_date: date) -> bool:
        return target_date in covered_days

    original = company_news_service._has_company_raw_for_day
    company_news_service._has_company_raw_for_day = fake_has_raw
    try:
        ranges = company_news_service._build_fetch_ranges_for_slice(
            "Nvidia",
            slice_start=date(2026, 3, 7),
            slice_end=today,
            today=today,
        )
    finally:
        company_news_service._has_company_raw_for_day = original

    assert ranges == [
        (date(2026, 3, 9), date(2026, 3, 9)),
        (date(2026, 3, 12), date(2026, 3, 16)),
    ]


def test_company_story_incremental_items_include_kept_filtered_rows(monkeypatch) -> None:
    article = SimpleNamespace(
        id=1,
        news_date_time=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
        news_title="Nvidia launches new AI chip",
        news_source="Reuters",
        news_source_link="https://example.com",
        llm_analyzed_content=json.dumps({"summary": "Launch details"}),
        original_content="raw",
        is_filtered=True,
    )
    monkeypatch.setattr(
        company_news_service,
        "get_company_news_for_range",
        lambda *args, **kwargs: [article],
    )

    items = company_news_service._build_company_story_incremental_news_items(
        "Nvidia",
        target_date=date(2026, 3, 16),
    )

    assert len(items) == 1
    assert items[0]["news_title"] == "Nvidia launches new AI chip"


def test_company_detail_renders_earnings_tab_and_price_intelligence_panel() -> None:
    html = render_company_detail_page(
        "Google",
        model_choices_by_provider={"openai": ["gpt-5-mini"]},
        indicator_models=["gpt-5-mini"],
    )
    assert ">Stories<" in html
    assert ">Daily News<" in html
    assert ">Weekly Report<" in html
    assert ">Earnings<" in html
    assert "Price Intelligence" in html
    assert "Generate Price Intelligence" in html
    assert "Technical Report" in html
    assert "Generate Technical Report" in html
    assert "price-intelligence-style" not in html
    assert "Rebuild Warm-up" in html


def test_daily_worker_runs_market_before_companies(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "market_agent.app.company_updates.run_market_daily_update",
        lambda **kwargs: calls.append("market") or {"scope": "market", "updated": True},
    )
    monkeypatch.setattr(
        "market_agent.app.company_updates.run_company_daily_update",
        lambda company_name, **kwargs: calls.append(company_name)
        or {"company_name": company_name, "updated": True},
    )

    results = run_daily_updates_for_watchlist(companies=["Google", "Oracle"])

    assert calls == ["market", "Google", "Oracle"]
    assert results[0]["scope"] == "market"
    assert results[1]["company_name"] == "Google"
    assert results[2]["company_name"] == "Oracle"


def test_market_story_generation_uses_chunk_fallback(monkeypatch) -> None:
    monkeypatch.setattr(market_updates, "MARKET_STORY_PROMPT_JSON_LIMIT", 1)
    monkeypatch.setattr(market_updates, "MARKET_STORY_CHUNK_SIZE", 2)

    prompts: list[str] = []

    class FakeProvider:
        def generate_text(self, *, prompt: str) -> str:
            prompts.append(prompt)
            return '{"ongoing_stories":[{"story_title":"Rates","past":["A"],"now":["B"],"next":["Scenario: C | Impact: D | Probability: E | Sentiment: F"]}],"finished_stories":[]}'

    payload = market_updates._generate_market_story_payload(
        provider=FakeProvider(),
        provider_name="openai",
        model="gpt-5-mini",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 13),
        output_language="zh-CN",
        items=[
            {"news_title": "A", "news_date_time": "2026-03-01T00:00:00+00:00", "news_source": "finnhub", "news_source_link": "u1", "summary": "s1"},
            {"news_title": "B", "news_date_time": "2026-03-02T00:00:00+00:00", "news_source": "finnhub", "news_source_link": "u2", "summary": "s2"},
            {"news_title": "C", "news_date_time": "2026-03-03T00:00:00+00:00", "news_source": "finnhub", "news_source_link": "u3", "summary": "s3"},
        ],
    )

    assert payload["ongoing_stories"][0]["story_title"] == "Rates"


def test_refresh_market_news_for_range_skips_existing_past_days(monkeypatch) -> None:
    fetched_days: list[date] = []

    monkeypatch.setattr(
        market_updates,
        "ensure_database_schema",
        lambda: None,
    )
    monkeypatch.setattr(
        market_updates,
        "_has_market_raw_for_day",
        lambda target_date: target_date == date(2026, 3, 10),
    )
    monkeypatch.setattr(
        market_updates,
        "_fetch_market_news_for_day",
        lambda target_date: fetched_days.append(target_date) or [],
    )
    monkeypatch.setattr(
        market_updates,
        "_upsert_market_news_raw",
        lambda item: 1,
    )

    stats = market_updates.refresh_market_news_for_range(
        start_date=date(2026, 3, 10),
        end_date=date(2026, 3, 11),
    )

    assert fetched_days == [date(2026, 3, 11)]
    assert stats["skipped_existing_days"] == 1


def test_market_daily_news_refresh_job_reuses_existing_past_day_even_when_forced(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_market_daily_news_overview",
        lambda **kwargs: {"date": "2026-03-10", "raw_news": [{"headline": "A"}], "summaries": [], "clusters": []},
    )
    monkeypatch.setattr(
        "frontend.web.server.market_updates_module.refresh_market_news_for_range",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("past-day raw fetch should be skipped")),
    )
    monkeypatch.setattr(
        "frontend.web.server.generate_market_daily_report",
        lambda **kwargs: {"generated": True, "report_count": 1, "prompt_char_count": 100, "input_item_count": 5, "output_char_count": 50},
    )
    monkeypatch.setattr(
        "frontend.web.server.refresh_market_daily_clusters",
        lambda **kwargs: {"cluster_count": 0, "prompt_char_count": 80, "input_item_count": 5, "output_char_count": 40},
    )

    class DummyTracker:
        def mark_running(self, *_args, **_kwargs):
            return None

    result = __import__("frontend.web.server", fromlist=["_run_market_daily_news_job"])._run_market_daily_news_job(
        DummyTracker(),
        target_date=date(2026, 3, 10),
        provider_name="openai",
        model="gpt-5-mini",
        prompt_style="simple",
        output_language="zh-CN",
        force_fetch=True,
    )

    assert result["counts"]["reused_existing_raw"] is True
    assert result["counts"]["fetched_total"] == 0


def test_run_market_daily_update_reuses_existing_raw(monkeypatch) -> None:
    monkeypatch.setattr(
        market_updates,
        "get_market_story_warmup_state",
        lambda: {"job_state": "completed"},
    )
    monkeypatch.setattr(market_updates, "_has_market_raw_for_day", lambda target_date: True)
    monkeypatch.setattr(
        market_updates,
        "refresh_market_news_for_range",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("raw fetch should be skipped")),
    )
    monkeypatch.setattr(
        market_updates,
        "refresh_market_macro_events",
        lambda **kwargs: {"updated": 0, "event_count": 0},
    )
    monkeypatch.setattr(
        market_updates,
        "generate_market_daily_report",
        lambda **kwargs: {"generated": True, "report_count": 1},
    )
    monkeypatch.setattr(
        market_updates,
        "refresh_market_daily_clusters",
        lambda **kwargs: {"generated": True, "cluster_count": 3},
    )
    monkeypatch.setattr(
        market_updates,
        "refresh_market_story_states",
        lambda **kwargs: {"ongoing_story_count": 1, "finished_story_count": 0, "routed_cluster_count": 3},
    )

    result = market_updates.run_market_daily_update(target_date=date(2026, 3, 13))

    assert result["refresh_stats"]["mode"] == "reuse_existing_raw"
    assert result["daily_report_stats"]["report_count"] == 1
    assert result["cluster_stats"]["cluster_count"] == 3
    assert result["story_stats"]["routed_cluster_count"] == 3


def test_market_warmup_generates_daily_reports_and_clusters(monkeypatch) -> None:
    state = {"job_state": "not_started"}
    report_days = []
    cluster_days = []

    monkeypatch.setattr(market_updates, "_current_app_date", lambda: date(2026, 3, 16))
    monkeypatch.setattr(market_updates, "get_market_story_warmup_state", lambda: dict(state))

    def fake_upsert(**kwargs):
        state.update(kwargs)

    monkeypatch.setattr(market_updates, "_upsert_market_story_warmup_state", fake_upsert)
    monkeypatch.setattr(
        market_updates,
        "_get_market_raw_coverage",
        lambda start_date, end_date: {
            "item_count": 4,
            "covered_day_count": 2,
            "missing_dates": [],
        },
    )
    monkeypatch.setattr(
        market_updates,
        "generate_market_daily_report",
        lambda **kwargs: report_days.append(kwargs["target_date"]) or {"generated": True, "report_count": 1},
    )
    monkeypatch.setattr(
        market_updates,
        "refresh_market_daily_clusters",
        lambda **kwargs: cluster_days.append(kwargs["target_date"]) or {"generated": True, "cluster_count": 2},
    )
    monkeypatch.setattr(
        market_updates,
        "_generate_market_story_map",
        lambda **kwargs: {"ongoing_story_count": 1, "finished_story_count": 0, "cluster_count": 4},
    )

    market_updates.start_market_story_warmup(
        provider_name="openai",
        model="gpt-5.4",
        prompt_style="simple",
        output_language="zh-CN",
        warmup_days=2,
        slice_days=2,
    )

    assert report_days == [date(2026, 3, 15), date(2026, 3, 16)]
    assert cluster_days == [date(2026, 3, 15), date(2026, 3, 16)]


def test_market_macro_refresh_uses_llm_calendar(monkeypatch) -> None:
    monkeypatch.setattr(
        market_updates,
        "_generate_market_research_text",
        lambda provider_name, model, prompt: json.dumps(
            [
                {
                    "event_name": "US CPI",
                    "event_date_time": "2026-04-10T12:30:00+00:00",
                    "category": "inflation",
                    "actual_value": "",
                    "prior_value": "3.1%",
                    "expectation_value": "3.0%",
                    "summary": "Inflation release",
                    "source_url": "https://example.com/cpi",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        market_updates,
        "get_news_provider",
        lambda provider_name, model, timeout_sec=120: type(
            "Provider",
            (),
            {"generate_text": staticmethod(lambda prompt: "macro summary")},
        )(),
    )

    upserts: list[dict[str, object]] = []
    monkeypatch.setattr(
        market_updates,
        "_upsert_market_macro_event",
        lambda item, summary_text, provider_name, model, output_language: upserts.append(item) or 1,
    )

    stats = market_updates.refresh_market_macro_events(extend_window=True)

    assert stats["updated"] == 1
    assert stats["event_count"] == 1
    assert upserts[0]["event_name"] == "US CPI"


def test_market_macro_extension_window_uses_today_plus_3_months(monkeypatch) -> None:
    monkeypatch.setattr(market_updates, "_current_app_date", lambda: date(2026, 3, 29))
    start, end = market_updates._resolve_macro_extension_window()
    assert start.isoformat() == "2026-03-29"
    assert end.isoformat() == "2026-06-26"


def test_market_story_state_batch_clears_inactive_rows_before_rollover(monkeypatch) -> None:
    executed: list[str] = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            executed.append(" ".join(str(query).split()))
            return None

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

    monkeypatch.setattr(market_updates, "get_connection", lambda: _Conn())
    market_updates._upsert_market_story_state_batch(
        provider_name="openai",
        model="gpt-5.4",
        prompt_style="simple",
        output_language="zh-CN",
        stories=[
            {
                "story_key": "rates",
                "story_title": "Rates",
                "importance_rank": 1,
                "story_status": "ongoing",
            }
        ],
    )

    assert "DELETE FROM market_story_state" in executed[0]
    assert "is_active = FALSE" in executed[0]
    assert "UPDATE market_story_state" in executed[1]
    assert "is_active = TRUE" in executed[1]
