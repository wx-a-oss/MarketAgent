"""Shared page helpers for the web frontend."""

from __future__ import annotations


BASE_PAGE_STYLES = """
    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap");
    body {
        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
        margin: 2rem;
        background: #f5f5f5;
        color: #111827;
    }
    nav {
        background: white;
        border-radius: 0.75rem;
        padding: 0.75rem 1.25rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        max-width: 960px;
        margin: 0 auto 1.5rem;
        font-family: inherit;
    }
    .nav-inner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .nav-links {
        display: inline-flex;
        align-items: center;
        gap: 1rem;
        flex-wrap: wrap;
    }
    nav a {
        text-decoration: none;
        color: #1f2937;
        font-weight: 600;
        font-size: 0.95rem;
        letter-spacing: 0.01em;
    }
    nav a.active { color: #2563eb; }
    .container { max-width: 960px; margin: 0 auto; padding: 0 1rem; display: grid; gap: 1.5rem; }
    .card { background: white; border-radius: 0.75rem; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    h1, h2 { margin-top: 0; }
    form { display: flex; gap: 0.5rem; }
    input[type="text"] { flex: 1; padding: 0.65rem; border: 1px solid #ccc; border-radius: 0.5rem; }
    button { padding: 0.65rem 1.2rem; border: none; border-radius: 0.5rem; background: #2563eb; color: white; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    .report {
        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
        font-size: 13px;
        line-height: 1.65;
        color: #111;
    }
    .report h1 {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .report h2 {
        font-size: 14px;
        font-weight: 600;
        margin: 12px 0 6px;
    }
    .report ul {
        padding-left: 16px;
        margin: 0;
    }
    .report li {
        margin-bottom: 6px;
    }
    .report strong {
        font-weight: 600;
    }
"""


def render_nav(active: str) -> str:
    items = [
        ("market", "/market", "Market"),
        ("company", "/company", "Company"),
        ("charts", "/charts", "Charts"),
        ("notes", "/notes", "Notes"),
        ("person", "/person", "Person"),
    ]
    links = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for key, href, label in items
    )
    return (
        '<nav>'
        '<div class="nav-inner">'
        f'<div class="nav-links">{links}</div>'
        '</div>'
        '</nav>'
    )


def render_simple_query_page(title: str, placeholder: str, active: str) -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – {title}</title>
                <style>
                    {BASE_PAGE_STYLES}
                </style>
            </head>
            <body class="report">
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
