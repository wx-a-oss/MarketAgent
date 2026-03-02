from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.web.server import app  # noqa: E402


def test_market_item_analyses_endpoint_returns_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.web.server._get_market_news_item_analyses",
        lambda news_date, model, output_language: [
            {
                "id": 1,
                "news_date": news_date.isoformat(),
                "news_url": "https://example.com/a",
                "headline": "A",
                "source": "Reuters",
                "source_tag": "finnhub",
                "provider": "openai",
                "model": model,
                "output_language": output_language,
                "prompt_style": "simple",
                "output_text": "analysis",
                "updated_at": "2026-02-28 12:00:00",
            }
        ],
    )
    client = TestClient(app)
    response = client.get(
        "/api/market/news/item-analyses",
        params={"date": "2026-02-28", "model": "gpt-5.2", "output_language": "zh-CN"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == "2026-02-28"
    assert len(payload["analyses"]) == 1
    assert payload["analyses"][0]["news_url"] == "https://example.com/a"


def test_market_item_analyze_endpoint_persists_analysis(monkeypatch) -> None:
    monkeypatch.setattr("frontend.web.server._resolve_news_provider_for_model", lambda model: "openai")
    monkeypatch.setattr("frontend.web.server._run_market_news_summary", lambda provider, model, prompt: "single news analysis")

    def _fake_upsert(**kwargs):
        return {
            "id": 2,
            "news_date": kwargs["news_date"].isoformat(),
            "news_url": kwargs["news_url"],
            "headline": kwargs["headline"],
            "source": kwargs["source"],
            "source_tag": kwargs["source_tag"],
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "output_language": kwargs["output_language"],
            "prompt_style": kwargs["prompt_style"],
            "output_text": kwargs["output_text"],
            "updated_at": "2026-02-28 12:30:00",
        }

    monkeypatch.setattr("frontend.web.server._upsert_market_news_item_analysis", _fake_upsert)

    client = TestClient(app)
    response = client.post(
        "/api/market/news/item-analyze",
        params={"model": "gpt-5.2", "output_language": "zh-CN"},
        json={
            "date": "2026-02-28",
            "item": {
                "headline": "Stocks rise",
                "url": "https://example.com/stocks-rise",
                "source": "Yahoo Finance",
                "source_tag": "yahoo",
                "summary": "short",
                "datetime_text": "Feb 28, 2026 10:00 AM",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["analysis"]["news_url"] == "https://example.com/stocks-rise"
    assert payload["analysis"]["output_text"] == "single news analysis"
