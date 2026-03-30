"""Calendar page rendering."""

from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_calendar_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Calendar</title>
                <style>
                    {BASE_PAGE_STYLES}
                    .report {{
                        font-family: "Space Grotesk", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB",
                                     "Microsoft YaHei", "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
                        font-size: 14px;
                        line-height: 1.7;
                        color: #0f172a;
                    }}
                    .report h1 {{
                        font-size: 26px;
                        font-weight: 600;
                        margin-bottom: 8px;
                    }}
                    .report h2 {{
                        font-size: 18px;
                        font-weight: 600;
                        margin: 12px 0 6px;
                    }}
                    .section-title {{
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 1rem;
                        margin-bottom: 0.6rem;
                    }}
                    .summary-controls {{
                        display: flex;
                        align-items: center;
                        gap: 0.55rem;
                        margin: 0;
                    }}
                    .summary-status {{
                        color: #64748b;
                        font-size: 0.82rem;
                    }}
                    .analyze-btn {{
                        background: #0f766e;
                        color: #fff;
                        padding: 0.55rem 0.95rem;
                        border-radius: 999px;
                    }}
                    .analyze-btn:hover {{
                        background: #115e59;
                    }}
                    .macro-calendar-wrap {{
                        display: grid;
                        gap: 1rem;
                    }}
                    .macro-calendar-note {{
                        font-size: 0.82rem;
                        color: #64748b;
                    }}
                    .macro-month-grid {{
                        display: grid;
                        grid-template-columns: repeat(7, minmax(0, 1fr));
                        gap: 0.4rem;
                    }}
                    .macro-month-title {{
                        margin: 0 0 0.45rem;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #0f172a;
                    }}
                    .macro-weekday {{
                        font-size: 0.72rem;
                        color: #64748b;
                        text-transform: uppercase;
                        letter-spacing: 0.04em;
                        padding: 0.12rem 0.2rem;
                    }}
                    .macro-day-cell {{
                        min-height: 102px;
                        border: 1px solid #e5e7eb;
                        border-radius: 0.65rem;
                        padding: 0.45rem;
                        background: #fff;
                        display: flex;
                        flex-direction: column;
                        gap: 0.28rem;
                        cursor: pointer;
                    }}
                    .macro-day-cell.empty {{
                        background: transparent;
                        border-style: dashed;
                        border-color: #f1f5f9;
                        cursor: default;
                    }}
                    .macro-day-cell.has-events {{
                        border-color: #cbd5e1;
                        background: #f8fbff;
                    }}
                    .macro-day-cell.selected {{
                        border-color: #0f766e;
                        box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.14);
                    }}
                    .macro-day-num {{
                        font-size: 0.82rem;
                        font-weight: 700;
                        color: #0f172a;
                    }}
                    .macro-day-events {{
                        display: grid;
                        gap: 0.18rem;
                    }}
                    .macro-pill {{
                        font-size: 0.68rem;
                        line-height: 1.2;
                        padding: 0.14rem 0.32rem;
                        border-radius: 999px;
                        background: #e2e8f0;
                        color: #334155;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }}
                    .macro-overflow {{
                        font-size: 0.68rem;
                        color: #64748b;
                    }}
                    .macro-detail-card {{
                        border: 1px solid #dbeafe;
                        background: #f8fbff;
                        border-radius: 0.8rem;
                        padding: 0.8rem 0.9rem;
                    }}
                    .macro-detail-date {{
                        font-size: 0.88rem;
                        color: #475569;
                        margin-bottom: 0.55rem;
                    }}
                    .macro-detail-item {{
                        border-top: 1px solid #e2e8f0;
                        padding: 0.55rem 0 0;
                        margin-top: 0.55rem;
                    }}
                    .macro-detail-item:first-child {{
                        border-top: none;
                        margin-top: 0;
                        padding-top: 0;
                    }}
                    .macro-detail-item h3 {{
                        margin: 0 0 0.22rem;
                        font-size: 0.95rem;
                        color: #0f172a;
                    }}
                    .macro-detail-meta {{
                        color: #64748b;
                        font-size: 0.78rem;
                        margin-bottom: 0.2rem;
                    }}
                    .macro-detail-values {{
                        display: grid;
                        gap: 0.14rem;
                        font-size: 0.82rem;
                        color: #334155;
                    }}
                    .macro-detail-link a {{
                        color: #475569;
                        text-decoration: underline;
                        font-size: 0.78rem;
                    }}
                    @media (max-width: 860px) {{
                        .macro-month-grid {{
                            grid-template-columns: repeat(1, minmax(0, 1fr));
                        }}
                        .macro-weekday {{
                            display: none;
                        }}
                    }}
                </style>
            </head>
            <body class="report">
                {render_nav("calendar")}
                <div class="container">
                    <section class="card">
                        <div class="section-title">
                            <div>
                                <h1 style="margin:0;">Calendar</h1>
                                <p class="summary-status" style="margin:0.35rem 0 0;">
                                    Scheduled U.S. macro releases. Each refresh rechecks the next 3 months and adds missing future events while keeping past history visible below.
                                </p>
                            </div>
                            <div class="summary-controls">
                                <button id="refresh-market-macro" class="analyze-btn" type="button">Refresh 3 Months</button>
                                <span id="market-macro-status" class="summary-status"></span>
                            </div>
                        </div>
                        <div id="market-macro-events" class="macro-calendar-wrap"></div>
                    </section>
                </div>
                <script>
                    const summaryLanguage = document.getElementById("global-language-select");
                    const marketMacroEventsEl = document.getElementById("market-macro-events");
                    const marketMacroStatus = document.getElementById("market-macro-status");
                    const refreshMacroBtn = document.getElementById("refresh-market-macro");
                    let selectedMacroDate = "";
                    let macroJobStop = null;

                    function getOutputLanguage() {{
                        const selected = summaryLanguage && summaryLanguage.value
                            ? String(summaryLanguage.value)
                            : "zh-CN";
                        return selected || "zh-CN";
                    }}

                    function formatMacroCellLabel(name) {{
                        const text = String(name || "").trim();
                        if (!text) return "Event";
                        const replacements = [
                            ["Consumer Price Index", "CPI"],
                            ["Producer Price Index", "PPI"],
                            ["Nonfarm Payrolls", "NFP"],
                            ["Federal Open Market Committee", "FOMC"],
                            ["Gross Domestic Product", "GDP"],
                            ["Unemployment Rate", "Unemployment"],
                            ["Retail Sales", "Retail Sales"],
                            ["Consumer Confidence", "Consumer Confidence"],
                            ["Trade Balance", "Trade Balance"],
                        ];
                        for (const [needle, label] of replacements) {{
                            if (text.toLowerCase().includes(needle.toLowerCase())) return label;
                        }}
                        return text.length > 22 ? `${{text.slice(0, 21)}}…` : text;
                    }}

                    function localDateKey(value = new Date()) {{
                        const year = value.getFullYear();
                        const month = String(value.getMonth() + 1).padStart(2, "0");
                        const day = String(value.getDate()).padStart(2, "0");
                        return `${{year}}-${{month}}-${{day}}`;
                    }}

                    function buildJobKey(...parts) {{
                        return parts.map((item) => String(item || "").trim().toLowerCase()).join("|");
                    }}

                    function formatJobText(job) {{
                        if (!job) return "";
                        const counts = job.final_counts || {{}};
                        const bits = [String(job.status || "")];
                        if (job.current_stage) bits.push(String(job.current_stage));
                        if (job.elapsed_sec) bits.push(`${{Number(job.elapsed_sec || 0).toFixed(1)}}s`);
                        if (job.input_char_count) bits.push(`prompt=${{job.input_char_count}} chars`);
                        if (counts.updated) bits.push(`updated=${{counts.updated}}`);
                        if (counts.event_count) bits.push(`events=${{counts.event_count}}`);
                        if (job.result_summary) bits.push(String(job.result_summary));
                        if (job.error_text) bits.push(String(job.error_text));
                        return bits.filter(Boolean).join(" · ");
                    }}

                    async function fetchJobByKey(jobKey) {{
                        const response = await fetch(`/api/jobs/by-key?job_key=${{encodeURIComponent(jobKey)}}&include_finished=true`);
                        const payload = await response.json();
                        return payload.job || null;
                    }}

                    async function fetchJob(jobId) {{
                        const response = await fetch(`/api/jobs/${{encodeURIComponent(String(jobId))}}`);
                        const payload = await response.json();
                        return payload.job || null;
                    }}

                    function pollJob(jobId, onUpdate, onDone) {{
                        let stopped = false;
                        async function tick() {{
                            if (stopped) return;
                            const job = await fetchJob(jobId);
                            if (onUpdate) onUpdate(job);
                            const running = job && ["queued", "running"].includes(String(job.status || ""));
                            if (running) {{
                                window.setTimeout(tick, 2000);
                                return;
                            }}
                            if (onDone) onDone(job);
                        }}
                        tick();
                        return () => {{ stopped = true; }};
                    }}

                    function renderMacroEvents(events) {{
                        if (!marketMacroEventsEl) return;
                        if (!events || !events.length) {{
                            marketMacroEventsEl.innerHTML = '<p class="summary-status">No calendar events available.</p>';
                            return;
                        }}
                        const eventsByDate = new Map();
                        for (const item of events) {{
                            const dateKey = String(item.event_date_time || "").slice(0, 10);
                            if (!dateKey) continue;
                            if (!eventsByDate.has(dateKey)) {{
                                eventsByDate.set(dateKey, []);
                            }}
                            eventsByDate.get(dateKey).push(item);
                        }}
                        const dateKeys = Array.from(eventsByDate.keys()).sort();
                        const firstRenderableDate = dateKeys[0] || "";
                        const lastRenderableDate = dateKeys[dateKeys.length - 1] || "";
                        const selectedWithinRange = !!(
                            selectedMacroDate &&
                            firstRenderableDate &&
                            lastRenderableDate &&
                            selectedMacroDate >= firstRenderableDate &&
                            selectedMacroDate <= lastRenderableDate
                        );
                        if (!selectedWithinRange) {{
                            const todayText = localDateKey();
                            const pastDates = dateKeys.filter((item) => item < todayText);
                            const futureDates = dateKeys.filter((item) => item > todayText);
                            selectedMacroDate =
                                (todayText && firstRenderableDate && lastRenderableDate && todayText >= firstRenderableDate && todayText <= lastRenderableDate)
                                    ? todayText
                                    : (eventsByDate.has(todayText)
                                        ? todayText
                                        : (pastDates.length ? pastDates[pastDates.length - 1] : (futureDates[0] || dateKeys[0] || "")));
                        }}
                        const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
                        const monthStarts = [];
                        const firstDate = new Date(`${{dateKeys[0]}}T00:00:00`);
                        const lastDate = new Date(`${{dateKeys[dateKeys.length - 1]}}T00:00:00`);
                        const cursor = new Date(firstDate.getFullYear(), firstDate.getMonth(), 1);
                        while (cursor <= lastDate) {{
                            monthStarts.push(new Date(cursor));
                            cursor.setMonth(cursor.getMonth() + 1);
                        }}

                        const monthHtml = monthStarts.map((monthStart) => {{
                            const year = monthStart.getFullYear();
                            const month = monthStart.getMonth();
                            const monthLabel = monthStart.toLocaleDateString(undefined, {{ year: "numeric", month: "long" }});
                            const startWeekday = new Date(year, month, 1).getDay();
                            const endDay = new Date(year, month + 1, 0).getDate();
                            const cells = [];
                            for (let i = 0; i < startWeekday; i += 1) {{
                                cells.push('<div class="macro-day-cell empty"></div>');
                            }}
                            for (let day = 1; day <= endDay; day += 1) {{
                                const dt = new Date(year, month, day);
                                const key = `${{dt.getFullYear()}}-${{String(dt.getMonth() + 1).padStart(2, "0")}}-${{String(day).padStart(2, "0")}}`;
                                const dayEvents = eventsByDate.get(key) || [];
                                const classes = ["macro-day-cell"];
                                if (dayEvents.length) classes.push("has-events");
                                if (key === selectedMacroDate) classes.push("selected");
                                const labels = dayEvents.slice(0, 3).map((item) => `<div class="macro-pill" title="${{String(item.event_name || "").replace(/"/g, "&quot;")}}">${{formatMacroCellLabel(item.event_name)}}</div>`).join("");
                                const overflow = dayEvents.length > 3 ? `<div class="macro-overflow">+${{dayEvents.length - 3}}</div>` : "";
                                cells.push(`
                                    <button type="button" class="${{classes.join(" ")}}" data-macro-date="${{key}}">
                                        <div class="macro-day-num">${{day}}</div>
                                        <div class="macro-day-events">${{labels}}${{overflow}}</div>
                                    </button>
                                `);
                            }}
                            return `
                                <section>
                                    <h3 class="macro-month-title">${{monthLabel}}</h3>
                                    <div class="macro-month-grid">
                                        ${{weekdays.map((label) => `<div class="macro-weekday">${{label}}</div>`).join("")}}
                                        ${{cells.join("")}}
                                    </div>
                                </section>
                            `;
                        }}).join("");

                        const selectedEvents = eventsByDate.get(selectedMacroDate) || [];
                        const detailTitle = selectedMacroDate
                            ? new Date(`${{selectedMacroDate}}T00:00:00`).toLocaleDateString(undefined, {{
                                year: "numeric",
                                month: "long",
                                day: "numeric",
                            }})
                            : "";
                        const detailHtml = selectedEvents.length
                            ? selectedEvents.map((item) => `
                                <div class="macro-detail-item">
                                    <h3>${{item.event_name || "Event"}}</h3>
                                    <div class="macro-detail-meta">${{item.country || "US"}} · ${{item.category || "macro"}} · ${{item.event_date_time || ""}}</div>
                                    <div class="macro-detail-values">
                                        <div><strong>Actual:</strong> ${{item.actual_value || "—"}}${{item.unit ? ` ${{item.unit}}` : ""}}</div>
                                        <div><strong>Prior:</strong> ${{item.previous_value || "—"}}</div>
                                        <div><strong>Expectation:</strong> ${{item.consensus_value || "—"}}</div>
                                    </div>
                                    ${{item.source_url ? `<div class="macro-detail-link"><a href="${{item.source_url}}" target="_blank" rel="noopener noreferrer">Source</a></div>` : ""}}
                                </div>
                            `).join("")
                            : '<p class="summary-status">Select a day with events.</p>';

                        marketMacroEventsEl.innerHTML = `
                            <div class="macro-calendar-wrap">
                                ${{monthHtml}}
                                <div class="macro-detail-card">
                                    <div class="macro-detail-date">${{detailTitle || "Selected day"}}</div>
                                    ${{detailHtml}}
                                </div>
                            </div>
                        `;
                        marketMacroEventsEl.querySelectorAll("[data-macro-date]").forEach((button) => {{
                            button.addEventListener("click", () => {{
                                selectedMacroDate = button.getAttribute("data-macro-date") || "";
                                renderMacroEvents(events);
                            }});
                        }});
                    }}

                    async function loadCalendar(refresh = false) {{
                        const endpoint = refresh
                            ? `/api/market/macro/refresh?output_language=${{encodeURIComponent(getOutputLanguage())}}`
                            : "/api/market/macro";
                        const response = await fetch(endpoint, {{ method: refresh ? "POST" : "GET" }});
                        const payload = await response.json();
                        renderMacroEvents(payload.events || []);
                        if (marketMacroStatus) {{
                            marketMacroStatus.textContent = payload.job ? formatJobText(payload.job) : "";
                        }}
                        if (payload.job && refreshMacroBtn) {{
                            const running = ["queued", "running"].includes(String(payload.job.status || ""));
                            refreshMacroBtn.disabled = running;
                            refreshMacroBtn.textContent = running ? "Refresh Running..." : "Refresh 3 Months";
                            if (running) {{
                                if (macroJobStop) macroJobStop();
                                macroJobStop = pollJob(payload.job.job_id, (job) => {{
                                    if (marketMacroStatus) marketMacroStatus.textContent = formatJobText(job);
                                    const stillRunning = job && ["queued", "running"].includes(String(job.status || ""));
                                    refreshMacroBtn.disabled = !!stillRunning;
                                    refreshMacroBtn.textContent = stillRunning ? "Refresh Running..." : "Refresh 3 Months";
                                }}, async () => {{
                                    await loadCalendar(false);
                                }});
                            }}
                        }}
                    }}
                    if (refreshMacroBtn) {{
                        refreshMacroBtn.addEventListener("click", async () => {{
                            await loadCalendar(true);
                        }});
                    }}
                    loadCalendar(false).then(async () => {{
                        const job = await fetchJobByKey(buildJobKey("market_macro", "openai", getOutputLanguage()));
                        if (job && marketMacroStatus) {{
                            marketMacroStatus.textContent = formatJobText(job);
                        }}
                        if (job && refreshMacroBtn && ["queued", "running"].includes(String(job.status || ""))) {{
                            refreshMacroBtn.disabled = true;
                            refreshMacroBtn.textContent = "Extend Running...";
                            if (macroJobStop) macroJobStop();
                            macroJobStop = pollJob(job.job_id, (currentJob) => {{
                                if (marketMacroStatus) marketMacroStatus.textContent = formatJobText(currentJob);
                            }}, async () => {{
                                await loadCalendar(false);
                            }});
                        }}
                    }});
                </script>
            </body>
        </html>
    """
