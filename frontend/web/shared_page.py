"""Shared page helpers for the web frontend."""

from __future__ import annotations


BASE_PAGE_STYLES = """
    body { font-family: Arial, sans-serif; margin: 2rem; background: #f5f5f5; }
    nav { background: white; border-radius: 0.75rem; padding: 0.75rem 1.25rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); max-width: 960px; margin: 0 auto 1.5rem; }
    nav a { margin-right: 1rem; text-decoration: none; color: #1f2937; font-weight: 600; }
    nav a.active { color: #2563eb; }
    .container { max-width: 960px; margin: 0 auto; padding: 0 1rem; display: grid; gap: 1.5rem; }
    .card { background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    h1, h2 { margin-top: 0; }
    form { display: flex; gap: 0.5rem; }
    input[type="text"] { flex: 1; padding: 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }
    button { padding: 0.65rem 1.2rem; border: none; border-radius: 0.5rem; background: #2563eb; color: white; cursor: pointer; }
    button:hover { background: #1d4ed8; }
"""


def render_nav(active: str) -> str:
    items = [
        ("stock", "/", "Stock"),
        ("company", "/company", "Company"),
        ("person", "/person", "Person"),
    ]
    links = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for key, href, label in items
    )
    return f"<nav>{links}</nav>"


def render_simple_query_page(title: str, placeholder: str, active: str) -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – {title}</title>
                <style>
                    {BASE_PAGE_STYLES}
                </style>
            </head>
            <body>
                {render_nav(active)}
                <div class="container">
                    <section class="card">
                        <h1>{title}</h1>
                        <form method="get">
                            <input type="text" placeholder="{placeholder}" />
                            <button type="submit">Search</button>
                        </form>
                    </section>
                </div>
            </body>
        </html>
    """
