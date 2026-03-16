from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.calendar_page import render_calendar_page  # noqa: E402
from frontend.web.company_detail_page import render_company_detail_page  # noqa: E402
from frontend.web.market_page import render_market_page  # noqa: E402
from frontend.web.server import app  # noqa: E402
from market_agent.app.company_updates import run_daily_updates_for_watchlist  # noqa: E402
from market_agent.app import market_updates  # noqa: E402
from market_agent.analysis.company.news import service as company_news_service  # noqa: E402


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
        "frontend.web.server.run_market_daily_update",
        lambda **kwargs: {"updated": True, "story_count": 2},
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
    response = client.post("/api/market/stories/refresh", params={"date": "2026-03-12"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] is True
    assert payload["ongoing_stories"][0]["story_title"] == "Oil shock"


def test_market_macro_refresh_endpoint_returns_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.refresh_market_macro_events",
        lambda provider_name="openai", model="gpt-5-mini", output_language="zh-CN", extend_window=False: {
            "updated": 2,
            "event_count": 2,
            "window_start": "2026-03-13",
            "window_end": "2026-04-11",
            "action": "extend_calendar_by_1_month",
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
    assert payload["updated"] == 2
    assert len(payload["events"]) == 2
    assert payload["description"] == "Extend calendar by 1 more month."


def test_market_macro_endpoint_returns_date_window(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.list_market_macro_events",
        lambda start_date=None, end_date=None, limit=80: [{"event_name": "CPI"}],
    )
    client = TestClient(app)
    response = client.get("/api/market/macro")
    assert response.status_code == 200
    payload = response.json()
    assert payload["events"][0]["event_name"] == "CPI"
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


def test_company_price_intelligence_generate_endpoint_returns_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.generate_company_status_snapshot",
        lambda company_name, provider_name="openai", model="gpt-5-mini", prompt_style="simple", output_language="zh-CN", window_days=90: {"generated": True},
    )
    monkeypatch.setattr(
        "frontend.web.server.get_company_status_snapshot",
        lambda company_name, provider_name="openai", prompt_style="simple": {
            "company_name": company_name,
            "output_text": "price intelligence",
            "window_start_date": "2026-01-01",
            "window_end_date": "2026-03-12",
            "provider": provider_name,
            "model": "gpt-5-mini",
        },
    )
    client = TestClient(app)
    response = client.post("/api/company/Google/price-intelligence/generate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["output_text"] == "price intelligence"


def test_market_page_renders_overview_and_stories_subviews() -> None:
    html = render_market_page(
        {"openai": ["gpt-5-mini"], "gemini": ["gemini-2.5-pro"]},
        default_date="2026-03-12",
    )
    assert "Overview" in html
    assert "Stories" in html
    assert "market-stories-view" in html
    assert "refresh-market-stories" in html
    assert "Macro Calendar" not in html


def test_calendar_page_renders_calendar_controls() -> None:
    html = render_calendar_page()
    assert ">Calendar<" in html
    assert "macro releases" in html
    assert "refresh-market-macro" in html
    assert "Extend 1 Month" in html


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
        "frontend.web.server.rebuild_company_warmup",
        lambda company_name, **kwargs: {"job_state": "running", "current_stage": "fetching_raw"},
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
    assert payload["mode"] == "warmup_rebuilt"
    assert payload["warmup"]["job_state"] == "running"


def test_company_story_refresh_endpoint_returns_warmup_started(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.start_company_daily_update",
        lambda company_name, **kwargs: {
            "company_name": company_name,
            "target_date": "2026-03-16",
            "mode": "warmup_started",
            "warmup": {"job_state": "running", "current_stage": "fetching_raw"},
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
    assert payload["mode"] == "warmup_started"


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
    assert "Analyze Position" in html
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


def test_market_daily_news_refresh_reuses_existing_past_day_even_when_forced(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_market_daily_news_overview",
        lambda **kwargs: {"date": "2026-03-10", "raw_news": [{"headline": "A"}], "summaries": [], "clusters": []},
    )
    monkeypatch.setattr(
        "frontend.web.server.market_updates_module.refresh_market_news_for_range",
        lambda **kwargs: {"mode": "fetched"},
    )
    monkeypatch.setattr(
        "frontend.web.server.generate_market_daily_report",
        lambda **kwargs: {"generated": True},
    )
    monkeypatch.setattr(
        "frontend.web.server.refresh_market_daily_clusters",
        lambda **kwargs: {"cluster_count": 0},
    )

    client = TestClient(app)
    response = client.post(
        "/api/market/daily-news/refresh",
        params={"date": "2026-03-10", "force_fetch": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh_stats"]["mode"] == "reuse_existing_raw_past_date"


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


def test_market_macro_extension_window_uses_future_max_date(monkeypatch) -> None:
    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return {"max_event_dt": datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

    monkeypatch.setattr(market_updates, "get_connection", lambda: _Conn())
    start, end = market_updates._resolve_macro_extension_window()
    assert start.isoformat() == "2026-06-11"
    assert end.isoformat() == "2026-07-10"
