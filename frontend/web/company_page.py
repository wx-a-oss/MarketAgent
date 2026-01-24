"""Company page rendering."""

from __future__ import annotations

from frontend.web.shared_page import render_simple_query_page


def render_company_page() -> str:
    return render_simple_query_page(
        title="Company",
        placeholder="Search company (e.g. Apple Inc.)",
        active="company",
    )
