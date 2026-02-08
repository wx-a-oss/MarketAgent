"""Global page rendering."""

from __future__ import annotations

from frontend.web.shared_page import render_simple_query_page


def render_global_page() -> str:
    return render_simple_query_page(
        title="Global",
        placeholder="Search market or region (e.g. Europe, Asia)",
        active="global",
    )
