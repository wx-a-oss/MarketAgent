from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.server import (  # noqa: E402
    US_MARKET_TZ,
    _resolve_market_price_sections,
    app,
)
from datetime import datetime


def test_resolve_market_price_sections_uses_snapshot_for_historical(monkeypatch) -> None:
    target = date.today() - timedelta(days=2)
    snapshot_payload = {
        "sections": [{"key": "indexes", "label": "Indexes", "items": [{"label": "S&P 500", "close_price": "5000"}]}]
    }
    monkeypatch.setattr("frontend.web.server._get_market_price_snapshot", lambda day: snapshot_payload)
    monkeypatch.setattr(
        "frontend.web.server._build_market_price_sections_live",
        lambda: (_ for _ in ()).throw(AssertionError("live fetch should not be called")),
    )

    sections, source, exists = _resolve_market_price_sections(target_date=target)
    assert sections == snapshot_payload["sections"]
    assert source == "snapshot"
    assert exists is True


def test_resolve_market_price_sections_persists_after_close(monkeypatch) -> None:
    target = datetime.now(US_MARKET_TZ).date()
    live_sections = [{"key": "indexes", "label": "Indexes", "items": [{"label": "S&P 500", "close_price": "5010"}]}]
    persisted: dict[str, object] = {}
    monkeypatch.setattr("frontend.web.server._get_market_price_snapshot", lambda day: None)
    monkeypatch.setattr("frontend.web.server._is_us_market_open_now", lambda: False)
    monkeypatch.setattr("frontend.web.server._is_us_market_day_closed_now", lambda: True)
    monkeypatch.setattr("frontend.web.server._is_us_trading_day", lambda day: True)
    monkeypatch.setattr("frontend.web.server._build_market_price_sections_live", lambda: live_sections)

    def fake_upsert(snapshot_date, payload):
        persisted["date"] = snapshot_date
        persisted["payload"] = payload

    monkeypatch.setattr("frontend.web.server._upsert_market_price_snapshot", fake_upsert)

    sections, source, exists = _resolve_market_price_sections(target_date=target)
    assert sections == live_sections
    assert source == "live_persisted_snapshot"
    assert exists is True
    assert persisted["date"] == target
    assert persisted["payload"] == {"sections": live_sections}


def test_market_overview_returns_dynamic_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._fetch_market_news",
        lambda target_date=None: [{"headline": "A", "url": "u", "source": "x"}],
    )
    monkeypatch.setattr(
        "frontend.web.server._resolve_market_price_sections",
        lambda target_date: (
            [
                {"key": "indexes", "label": "Indexes", "items": [{"label": "S&P 500", "close_price": "5000"}]},
                {"key": "crypto", "label": "Crypto", "items": [{"label": "Bitcoin", "close_price": "90000"}]},
            ],
            "snapshot",
            True,
        ),
    )
    client = TestClient(app)
    response = client.get("/api/market/overview", params={"date": date.today().isoformat()})
    assert response.status_code == 200
    payload = response.json()
    assert payload["price_data_source"] == "snapshot"
    assert payload["price_snapshot_exists"] is True
    assert len(payload["sections"]) == 2
    assert payload["indexes"][0]["label"] == "S&P 500"
    assert payload["crypto"][0]["label"] == "Bitcoin"
