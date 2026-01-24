"""Person page rendering."""

from __future__ import annotations

from frontend.web.shared_page import render_simple_query_page


def render_person_page() -> str:
    return render_simple_query_page(
        title="Person",
        placeholder="Search person (e.g. Tim Cook)",
        active="person",
    )
