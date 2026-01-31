"""Company watchlist page rendering."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_company_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Company</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .list {{ display: grid; gap: 0.75rem; }}
                    .list-item {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        padding: 0.6rem 0.8rem;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.6rem;
                        background: #f9fafb;
                    }}
                    .company-button {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.35rem;
                        padding: 0.4rem 0.75rem;
                        border-radius: 999px;
                        background: #eef2ff;
                        color: #2563eb;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 1rem;
                        border: 1px solid #c7d2fe;
                    }}
                    .company-button:hover {{ background: #e0e7ff; }}
                    .remove-btn {{ background: transparent; color: #ef4444; border: none; cursor: pointer; }}
                    .remove-btn:hover {{ color: #b91c1c; }}
                    #company-list {{ margin-top: 1rem; }}
                </style>
            </head>
            <body>
                {render_nav("company")}
                <div class="container">
                    <section class="card">
                        <h1>Company</h1>
                        <form id="company-form">
                            <input type="text" id="company-input" placeholder="Add company (e.g. Apple Inc.)" />
                            <button type="submit">Query</button>
                        </form>
                        <div id="company-list" class="list"></div>
                    </section>
                </div>
                <script>
                    const listEl = document.getElementById("company-list");
                    const formEl = document.getElementById("company-form");
                    const inputEl = document.getElementById("company-input");

                    async function loadCompanies() {{
                        const response = await fetch("/api/companies");
                        const payload = await response.json();
                        const companies = payload.companies || [];
                        if (!companies.length) {{
                            listEl.innerHTML = '<p class="muted">No companies added yet.</p>';
                            return;
                        }}
                        listEl.innerHTML = companies
                            .map(
                                (name) => `
                                    <div class="list-item">
                                        <a class="company-button" href="/company/${{encodeURIComponent(name)}}">${{capitalizeName(name)}}</a>
                                        <button class="remove-btn" data-name="${{name}}">Remove</button>
                                    </div>
                                `
                            )
                            .join("");
                        listEl.querySelectorAll(".remove-btn").forEach((button) => {{
                            button.addEventListener("click", async () => {{
                                const company = button.dataset.name;
                                await fetch(`/api/companies/${{encodeURIComponent(company)}}`, {{
                                    method: "DELETE",
                                }});
                                loadCompanies();
                            }});
                        }});
                    }}

                    formEl.addEventListener("submit", async (event) => {{
                        event.preventDefault();
                        const name = capitalizeName(inputEl.value.trim());
                        if (!name) {{
                            return;
                        }}
                        const response = await fetch("/api/companies");
                        const payload = await response.json();
                        const companies = payload.companies || [];
                        if (!companies.includes(name)) {{
                            await fetch("/api/companies", {{
                                method: "POST",
                                headers: {{
                                    "Content-Type": "application/json",
                                }},
                                body: JSON.stringify({{ company_name: name }}),
                            }});
                        }}
                        window.location.href = `/company/${{encodeURIComponent(name)}}`;
                    }});

                    loadCompanies();

                    function capitalizeName(name) {{
                        if (!name) {{
                            return "";
                        }}
                        return name.charAt(0).toUpperCase() + name.slice(1);
                    }}
                </script>
            </body>
        </html>
    """
