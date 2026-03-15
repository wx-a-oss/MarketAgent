from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.server import app


def test_company_stock_series_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_company_profile",
        lambda company_name: {"ticker": "GOOGL"},
    )
    monkeypatch.setattr(
        "frontend.web.server.ensure_company_profile",
        lambda company_name: {"ticker": "GOOGL"},
    )
    monkeypatch.setattr(
        "frontend.web.server._get_or_refresh_company_price_series",
        lambda **kwargs: [
            {"date": "2026-02-01", "date_time": "2026-02-01T00:00:00+00:00", "close": 100.0, "volume": 1000, "pct_change": None},
            {"date": "2026-02-02", "date_time": "2026-02-02T00:00:00+00:00", "close": 102.0, "volume": 1100, "pct_change": 2.0},
            {"date": "2026-02-03", "date_time": "2026-02-03T00:00:00+00:00", "close": 101.0, "volume": 1200, "pct_change": -0.98},
        ],
    )
    monkeypatch.setattr(
        "frontend.web.server._list_company_price_daily_points_all",
        lambda **kwargs: [],
    )

    client = TestClient(app)
    response = client.get("/api/company/Google/stock/series", params={"range_key": "1Y", "ma_windows": "2"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "GOOGL"
    assert payload["range_key"] == "1Y"
    assert payload["point_count"] == 3
    assert payload["points"][-1]["ma_2"] == 101.5


def test_company_stock_move_analysis_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server.get_company_profile",
        lambda company_name: {"ticker": "GOOGL"},
    )
    monkeypatch.setattr(
        "frontend.web.server.ensure_company_profile",
        lambda company_name: {"ticker": "GOOGL"},
    )
    monkeypatch.setattr(
        "frontend.web.server._get_or_refresh_company_price_series",
        lambda **kwargs: [
            {"date": "2026-02-01", "date_time": "2026-02-01T00:00:00+00:00", "close": 100.0, "volume": 1000, "pct_change": None},
            {"date": "2026-02-02", "date_time": "2026-02-02T00:00:00+00:00", "close": 110.0, "volume": 2100, "pct_change": 10.0},
        ],
    )
    monkeypatch.setattr(
        "frontend.web.server._get_company_price_move_analysis",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "frontend.web.server._build_company_price_move_prompt",
        lambda **kwargs: "prompt",
    )
    monkeypatch.setattr(
        "frontend.web.server._run_market_news_summary",
        lambda **kwargs: "analysis text",
    )

    def _fake_upsert(**kwargs):
        return {
            "id": 1,
            "company_name": kwargs["company_name"],
            "ticker": kwargs["ticker"],
            "range_key": kwargs["range_key"],
            "point_date_time": kwargs["point_date_time"],
            "point_label": kwargs["point_label"],
            "close_price": kwargs["close_price"],
            "pct_change": kwargs["pct_change"],
            "volume": kwargs["volume"],
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "prompt_style": kwargs["prompt_style"],
            "output_language": kwargs["output_language"],
            "output_text": kwargs["output_text"],
            "updated_at": "2026-02-28 12:00:00",
            "created_at": "2026-02-28 12:00:00",
        }

    monkeypatch.setattr("frontend.web.server._upsert_company_price_move_analysis", _fake_upsert)
    monkeypatch.setattr("frontend.web.server.pytime.sleep", lambda *_args, **_kwargs: None)

    client = TestClient(app)
    response = client.post(
        "/api/company/Google/stock/moves/analyze",
        params={"range_key": "1Y", "top_n": 5, "provider": "openai", "model": "gpt-5-mini"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["analyses"][0]["output_text"] == "analysis text"
