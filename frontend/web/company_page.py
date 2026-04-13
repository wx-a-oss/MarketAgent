"""Company watchlist page rendering."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_company_page(
    *,
    model_choices_by_provider: dict[str, list[str]] | None = None,
    default_company_model: str = "gpt-5.4-mini",
) -> str:
    openai_models = list((model_choices_by_provider or {}).get("openai") or [])
    if default_company_model not in openai_models:
        openai_models.append(default_company_model)
    model_options = "".join(
        f'<option value="{model}"{" selected" if model == default_company_model else ""}>{model}</option>'
        for model in openai_models
    )
    safe_default_model = default_company_model.replace("\\", "\\\\").replace('"', '\\"')
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
                    .company-meta {{
                        display: inline-flex;
                        align-items: center;
                        gap: 0.5rem;
                        min-width: 0;
                    }}
                    .company-model-tag {{
                        border: 1px solid #cbd5e1;
                        background: #ffffff;
                        color: #475569;
                        border-radius: 999px;
                        padding: 0.2rem 0.55rem;
                        font-size: 0.76rem;
                        font-weight: 600;
                    }}
                    .ticker-edit-btn {{
                        border: 1px solid #f59e0b;
                        background: #fff7ed;
                        color: #b45309;
                        border-radius: 0.5rem;
                        padding: 0.3rem 0.6rem;
                        font-size: 0.8rem;
                        font-weight: 600;
                        cursor: pointer;
                    }}
                    .ticker-edit-btn.filled {{
                        border-color: #ea580c;
                        background: #ffedd5;
                        color: #9a3412;
                    }}
                    .ticker-edit-btn:hover {{
                        border-color: #c2410c;
                        background: #fed7aa;
                    }}
                    .ticker-input {{
                        width: 110px;
                        border: 1px solid #f59e0b;
                        border-radius: 0.5rem;
                        padding: 0.3rem 0.55rem;
                        font-size: 0.8rem;
                        outline: none;
                        text-transform: uppercase;
                        background: #fff7ed;
                    }}
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
                            <select id="company-model">
                                {model_options}
                            </select>
                            <button type="submit">Subscribe</button>
                        </form>
                        <div id="company-list" class="list"></div>
                    </section>
                </div>
                <script>
                    const DEFAULT_COMPANY_MODEL = "{safe_default_model}";
                    const listEl = document.getElementById("company-list");
                    const formEl = document.getElementById("company-form");
                    const inputEl = document.getElementById("company-input");
                    const modelEl = document.getElementById("company-model");

                    async function loadCompanies() {{
                        const response = await fetch("/api/companies");
                        const payload = await response.json();
                        const companies = (payload.companies || []).map((item) =>
                            typeof item === "string"
                                ? {{ company_name: item, ticker: "", llm_model: DEFAULT_COMPANY_MODEL }}
                                : item
                        );
                        if (!companies.length) {{
                            listEl.innerHTML = '<p class="muted">No companies added yet.</p>';
                            return;
                        }}
                        listEl.innerHTML = companies
                            .map(
                                (item) => {{
                                    const name = item.company_name || "";
                                    const ticker = normalizeTicker(item.ticker || "");
                                    const llmModel = String(item.llm_model || DEFAULT_COMPANY_MODEL);
                                    return `
                                    <div class="list-item">
                                        <div class="company-meta">
                                            <a class="company-button" href="/company/${{encodeURIComponent(name)}}">${{escapeHtml(capitalizeName(name))}}</a>
                                            <span class="company-model-tag">${{escapeHtml(llmModel)}}</span>
                                            <button
                                                class="ticker-edit-btn ${{ticker ? "filled" : ""}}"
                                                data-company="${{escapeHtml(name)}}"
                                                data-ticker="${{escapeHtml(ticker)}}"
                                                title="Click to edit ticker"
                                            >${{formatTicker(ticker)}}</button>
                                        </div>
                                        <button class="remove-btn" data-name="${{escapeHtml(name)}}">Remove</button>
                                    </div>
                                `;
                                }}
                            )
                            .join("");

                        listEl.querySelectorAll(".ticker-edit-btn").forEach((button) => {{
                            button.addEventListener("click", () => startTickerEdit(button));
                        }});

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
                        const selectedModel = modelEl && modelEl.value ? String(modelEl.value) : DEFAULT_COMPANY_MODEL;
                        if (!name) {{
                            return;
                        }}
                        const response = await fetch("/api/companies");
                        const payload = await response.json();
                        const companies = (payload.companies || []).map((item) =>
                            typeof item === "string" ? item : item.company_name
                        );
                        if (!companies.includes(name)) {{
                            await fetch("/api/companies", {{
                                method: "POST",
                                headers: {{
                                    "Content-Type": "application/json",
                                }},
                                body: JSON.stringify({{ company_name: name, model: selectedModel }}),
                            }});
                        }}
                        window.location.href = `/company/${{encodeURIComponent(name)}}`;
                    }});

                    loadCompanies();

                    function startTickerEdit(button) {{
                        const companyName = button.dataset.company || "";
                        const currentTicker = normalizeTicker(button.dataset.ticker || "");
                        const input = document.createElement("input");
                        input.type = "text";
                        input.className = "ticker-input";
                        input.value = currentTicker;
                        input.placeholder = "Ticker";
                        input.maxLength = 16;
                        button.replaceWith(input);
                        input.focus();
                        input.select();

                        const save = async () => {{
                            const nextTicker = normalizeTicker(input.value);
                            await fetch(`/api/company/${{encodeURIComponent(companyName)}}/ticker`, {{
                                method: "PUT",
                                headers: {{
                                    "Content-Type": "application/json",
                                }},
                                body: JSON.stringify({{ ticker: nextTicker || null }}),
                            }});
                            loadCompanies();
                        }};

                        input.addEventListener("keydown", async (event) => {{
                            if (event.key === "Enter") {{
                                event.preventDefault();
                                await save();
                            }}
                            if (event.key === "Escape") {{
                                event.preventDefault();
                                loadCompanies();
                            }}
                        }});

                        input.addEventListener("blur", () => {{
                            loadCompanies();
                        }});
                    }}

                    function capitalizeName(name) {{
                        if (!name) {{
                            return "";
                        }}
                        return name.charAt(0).toUpperCase() + name.slice(1);
                    }}

                    function normalizeTicker(ticker) {{
                        return (ticker || "").trim().toUpperCase();
                    }}

                    function formatTicker(ticker) {{
                        return ticker ? `${{ticker}}` : "Set ticker";
                    }}

                    function escapeHtml(value) {{
                        return String(value)
                            .replaceAll("&", "&amp;")
                            .replaceAll("<", "&lt;")
                            .replaceAll(">", "&gt;")
                            .replaceAll('"', "&quot;");
                    }}
                </script>
            </body>
        </html>
    """
