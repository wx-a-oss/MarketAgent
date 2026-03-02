from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.web import server as web_server


class _FakeResponse:
    def __init__(self, body: bytes):
        self._io = BytesIO(body)

    def read(self) -> bytes:
        return self._io.read()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_fetch_yahoo_rss_market_news_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Yahoo Finance News</title>
    <item>
      <title>Stocks rise on cooling inflation</title>
      <link>https://finance.yahoo.com/news/example-1</link>
      <description>US markets climbed as yields eased.</description>
      <pubDate>Fri, 21 Feb 2026 15:10:00 GMT</pubDate>
      <source>Yahoo Finance</source>
    </item>
    <item>
      <title>Bitcoin extends weekly gains</title>
      <link>https://finance.yahoo.com/news/example-2</link>
      <description>Crypto markets stayed firm.</description>
      <pubDate>Fri, 21 Feb 2026 15:20:00 GMT</pubDate>
      <source>Yahoo Finance</source>
    </item>
  </channel>
</rss>
"""

    def _fake_urlopen(request, timeout=15):  # noqa: ANN001
        return _FakeResponse(rss_xml)

    monkeypatch.setattr(web_server.urllib.request, "urlopen", _fake_urlopen)

    items = web_server._fetch_yahoo_rss_market_news(limit=5)
    assert len(items) == 2
    assert items[0]["source_tag"] == "yahoo"
    assert items[0]["headline"] == "Stocks rise on cooling inflation"
    assert items[0]["url"] == "https://finance.yahoo.com/news/example-1"
    assert "markets climbed" in items[0]["summary"].lower()


@pytest.mark.integration
def test_fetch_yahoo_rss_market_news_live_returns_items() -> None:
    items = web_server._fetch_yahoo_rss_market_news(limit=5)
    assert len(items) > 0, "Expected Yahoo RSS feed to return at least one item."
    assert all(item.get("source_tag") == "yahoo" for item in items)
    assert all(str(item.get("url") or "").startswith("http") for item in items)
