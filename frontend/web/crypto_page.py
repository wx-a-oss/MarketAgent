"""Crypto page rendering."""

from __future__ import annotations

from frontend.web.shared_page import render_simple_query_page


def render_crypto_page() -> str:
    return render_simple_query_page(
        title="Capital",
        placeholder="Search capital markets (e.g. BTC, ETH, gold, rates)",
        active="capital",
    )
