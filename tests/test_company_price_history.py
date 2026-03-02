from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.server import (
    _attach_moving_averages,
    _parse_ma_windows,
    app,
)


def test_parse_ma_windows_filters_invalid_and_deduplicates() -> None:
    assert _parse_ma_windows("20, 50,200,50,0,abc,999") == [20, 50, 200]
    assert _parse_ma_windows("") == [20, 50, 200]


def test_attach_moving_averages_uses_close_values() -> None:
    points = [
        {"date": "2026-02-01", "close": 10.0},
        {"date": "2026-02-02", "close": 20.0},
        {"date": "2026-02-03", "close": 30.0},
        {"date": "2026-02-04", "close": 40.0},
    ]
    enriched = _attach_moving_averages(points, windows=[2, 3])
    assert enriched[0]["ma_2"] is None
    assert enriched[1]["ma_2"] == 15.0
    assert enriched[2]["ma_3"] == 20.0
    assert enriched[3]["ma_2"] == 35.0
    assert enriched[3]["ma_3"] == 30.0


def test_company_price_history_endpoint_prefers_yahoo(monkeypatch) -> None:
    def fake_yahoo(symbol: str, *, years: int):
        assert symbol == "AAPL"
        assert years == 1
        return [
            {"date": "2026-02-01", "close": 10.0, "adj_close": 10.0, "volume": 100},
            {"date": "2026-02-02", "close": 12.0, "adj_close": 12.0, "volume": 120},
            {"date": "2026-02-03", "close": 14.0, "adj_close": 14.0, "volume": 140},
        ]

    def fake_finnhub(symbol: str, *, years: int, api_key: str):
        raise AssertionError("Finnhub fallback should not be called when Yahoo returns data")

    monkeypatch.setattr("frontend.web.server._fetch_yahoo_daily_price_history", fake_yahoo)
    monkeypatch.setattr("frontend.web.server._fetch_finnhub_daily_price_history", fake_finnhub)

    client = TestClient(app)
    response = client.get(
        "/api/company/Apple/price/history",
        params={"ticker": "AAPL", "years": 1, "ma_windows": "2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["source"] == "yahoo_finance_chart"
    assert payload["point_count"] == 3
    assert payload["points"][-1]["ma_2"] == 13.0


def test_company_price_history_endpoint_reports_error_when_no_data(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._fetch_yahoo_daily_price_history",
        lambda symbol, *, years: [],
    )
    monkeypatch.setattr(
        "frontend.web.server._fetch_finnhub_daily_price_history",
        lambda symbol, *, years, api_key: [],
    )
    monkeypatch.setattr("frontend.web.server.os.getenv", lambda key, default="": "")

    client = TestClient(app)
    response = client.get(
        "/api/company/Apple/price/history",
        params={"ticker": "AAPL", "years": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["points"] == []
    assert "error" in payload
