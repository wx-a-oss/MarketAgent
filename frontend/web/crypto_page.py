"""Crypto page rendering."""

from __future__ import annotations

from frontend.web.shared_page import render_simple_query_page


def render_crypto_page() -> str:
    return render_simple_query_page(
        title="Crypto",
        placeholder="Search crypto (e.g. BTC, ETH)",
        active="crypto",
    )
