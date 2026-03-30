from __future__ import annotations

from frontend.web.shared_page import BASE_PAGE_STYLES, render_nav


def render_notes_page() -> str:
    return f"""
        <html>
            <head>
                <title>MarketAgent – Notes</title>
                <style>
                    {BASE_PAGE_STYLES}
                    body {{
                        background:
                            radial-gradient(circle at top right, rgba(14, 165, 233, 0.08), transparent 22%),
                            linear-gradient(180deg, #faf7f2 0%, #f4efe8 100%);
                    }}
                    .container {{ max-width: 1080px; }}
                    .notes-shell {{ display: grid; gap: 1rem; }}
                    .notes-card {{
                        background: rgba(255,255,255,0.92);
                        border: 1px solid rgba(148, 163, 184, 0.25);
                        border-radius: 1rem;
                        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
                        padding: 1.2rem;
                    }}
                    .notes-head h1 {{ margin: 0; font-size: 2rem; }}
                    .notes-meta {{ color: #64748b; font-size: 0.92rem; max-width: 760px; }}
                    .composer-grid {{ display: grid; gap: 0.8rem; }}
                    .notes-title-input, .notes-tags-input, .notes-edit-title, .notes-edit-tags {{
                        width: 100%; border: 1px solid #cbd5e1; border-radius: 0.75rem; padding: 0.75rem 0.9rem; font-size: 0.95rem; background: #fff;
                    }}
                    .notes-body-input, .notes-edit-body {{
                        width: 100%; min-height: 160px; border: 1px solid #cbd5e1; border-radius: 0.9rem; padding: 0.9rem 1rem; font-size: 0.96rem;
                        line-height: 1.5; resize: vertical; background: #fff; font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
                    }}
                    .notes-helper {{ font-size: 0.8rem; color: #64748b; }}
                    .notes-actions {{ display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap; }}
                    .notes-status {{ font-size: 0.85rem; color: #64748b; }}
                    .notes-btn {{ border: none; border-radius: 999px; padding: 0.7rem 1rem; font-weight: 700; cursor: pointer; }}
                    .notes-btn-primary {{ background: #0f766e; color: #fff; }}
                    .notes-btn-primary:hover {{ background: #0d9488; }}
                    .notes-btn-secondary {{ background: #e2e8f0; color: #0f172a; }}
                    .notes-btn-secondary:hover {{ background: #cbd5e1; }}
                    .filter-bar {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
                    .tag-chip {{ border: 1px solid #cbd5e1; background: #fff; color: #334155; border-radius: 999px; padding: 0.45rem 0.8rem; cursor: pointer; font-size: 0.84rem; font-weight: 600; }}
                    .tag-chip.active {{ background: #0f172a; border-color: #0f172a; color: #fff; }}
                    .tag-chip small {{ opacity: 0.75; font-weight: 600; }}
                    .timeline-list {{ display: grid; gap: 1rem; }}
                    .note-item {{ border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 1rem; background: #fff; padding: 1rem 1.05rem; }}
                    .note-item.invalid {{ background: #f8fafc; border-color: rgba(239, 68, 68, 0.25); }}
                    .note-item.invalid .note-title, .note-item.invalid .note-body {{ color: #64748b; text-decoration: line-through; text-decoration-thickness: 1.5px; }}
                    .note-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap; }}
                    .note-title {{ margin: 0; font-size: 1.08rem; color: #0f172a; }}
                    .note-submeta {{ font-size: 0.78rem; color: #64748b; display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.35rem; }}
                    .note-body {{ margin-top: 0.9rem; color: #111827; line-height: 1.6; }}
                    .note-body p {{ margin: 0 0 0.35rem; }}
                    .note-body ul, .note-body ol {{ margin: 0.2rem 0 0.5rem 1.1rem; }}
                    .note-body li {{ margin-bottom: 0.2rem; }}
                    .note-tags {{ display: flex; gap: 0.45rem; flex-wrap: wrap; margin-top: 0.9rem; }}
                    .note-tag {{ background: #eff6ff; color: #1d4ed8; border-radius: 999px; padding: 0.2rem 0.55rem; font-size: 0.76rem; font-weight: 700; }}
                    .note-flag {{ border-radius: 999px; padding: 0.18rem 0.55rem; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.01em; }}
                    .note-flag-invalid {{ background: #fee2e2; color: #b91c1c; }}
                    .note-controls {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
                    .note-inline-btn {{ border: none; background: transparent; color: #2563eb; font-weight: 700; cursor: pointer; padding: 0; }}
                    .note-inline-btn:hover {{ text-decoration: underline; }}
                    .note-edit-panel {{ display: none; margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed #cbd5e1; }}
                    .note-edit-panel.active {{ display: grid; gap: 0.65rem; }}
                    .empty-state {{ color: #64748b; font-size: 0.95rem; padding: 0.6rem 0; }}
                </style>
            </head>
            <body class="report">
                {render_nav("notes")}
                <div class="container">
                    <section class="notes-shell">
                        <article class="notes-card">
                            <div class="notes-head">
                                <h1>Notes</h1>
                                <div class="notes-meta">Capture ideas, doubts, trade setups, and research thoughts in one timeline. Notes support Markdown for bullets and <strong>bold</strong> text, remain editable, and can be invalidated without being deleted.</div>
                            </div>
                        </article>
                        <article class="notes-card">
                            <div class="composer-grid">
                                <input id="note-title" class="notes-title-input" type="text" placeholder="Title" />
                                <textarea id="note-body" class="notes-body-input" placeholder="Write your note in Markdown...&#10;&#10;- Bullet point&#10;- Another thought&#10;&#10;Use **bold** when something matters."></textarea>
                                <input id="note-tags" class="notes-tags-input" type="text" placeholder="Tags, comma separated. Example: Nvidia, market, Fed" />
                                <div class="notes-actions">
                                    <div>
                                        <div class="notes-helper">Markdown supported: <code>- item</code>, <code>* item</code>, <code>**bold**</code></div>
                                        <div id="notes-status" class="notes-status"></div>
                                    </div>
                                    <button id="note-save-btn" class="notes-btn notes-btn-primary" type="button">Save Note</button>
                                </div>
                            </div>
                        </article>
                        <article class="notes-card">
                            <div class="filter-bar" id="notes-filter-bar"></div>
                        </article>
                        <article class="notes-card">
                            <div id="notes-timeline" class="timeline-list"></div>
                        </article>
                    </section>
                </div>
                <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
                <script>
                    (function() {{
                        const statusEl = document.getElementById("notes-status");
                        const titleEl = document.getElementById("note-title");
                        const bodyEl = document.getElementById("note-body");
                        const tagsEl = document.getElementById("note-tags");
                        const saveBtn = document.getElementById("note-save-btn");
                        const filterBar = document.getElementById("notes-filter-bar");
                        const timelineEl = document.getElementById("notes-timeline");
                        let activeTag = "";
                        let allTags = [];

                        function escapeHtml(value) {{
                            return String(value || "")
                                .replace(/&/g, "&amp;")
                                .replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;");
                        }}

                        function renderMarkdown(value) {{
                            const safe = escapeHtml(value || "");
                            if (!safe.trim()) return "<p>—</p>";
                            if (window.marked && typeof window.marked.parse === "function") {{
                                return window.marked.parse(safe);
                            }}
                            return `<p>${{safe}}</p>`;
                        }}

                        function formatDateTime(value) {{
                            if (!value) return "";
                            const dt = new Date(value);
                            if (Number.isNaN(dt.getTime())) return String(value);
                            return dt.toLocaleString(undefined, {{ dateStyle: "medium", timeStyle: "short" }});
                        }}

                        async function fetchJson(url, options) {{
                            const response = await fetch(url, options);
                            const payload = await response.json();
                            if (!response.ok) throw new Error(payload.error || response.statusText || "Request failed");
                            if (payload.error) throw new Error(payload.error);
                            return payload;
                        }}

                        function renderTagFilters() {{
                            const chips = [`<button class="tag-chip ${{activeTag ? "" : "active"}}" type="button" data-tag="">All Notes</button>`];
                            for (const tag of allTags) {{
                                chips.push(`<button class="tag-chip ${{activeTag === tag.normalized_tag ? "active" : ""}}" type="button" data-tag="${{tag.normalized_tag}}">${{escapeHtml(tag.tag)}} <small>(${{tag.note_count}})</small></button>`);
                            }}
                            filterBar.innerHTML = chips.join("");
                            filterBar.querySelectorAll("[data-tag]").forEach((el) => {{
                                el.addEventListener("click", async () => {{
                                    activeTag = el.getAttribute("data-tag") || "";
                                    renderTagFilters();
                                    await loadNotes();
                                }});
                            }});
                        }}

                        function renderNoteCard(note) {{
                            const tags = Array.isArray(note.tags) ? note.tags : [];
                            const invalid = note.validity_state === "invalid";
                            const created = formatDateTime(note.created_at);
                            const updated = formatDateTime(note.updated_at);
                            const invalidated = formatDateTime(note.invalidated_at);
                            const invalidBadge = invalid ? `<span class="note-flag note-flag-invalid">Invalid</span>` : "";
                            const invalidWhen = invalid && invalidated ? `<span>Invalidated ${{invalidated}}</span>` : "";
                            const invalidateAction = invalid ? "" : `<button class="note-inline-btn" type="button" data-action="invalidate">Invalidate</button>`;
                            const invalidReason = invalid && note.invalidation_reason
                                ? `<div class="note-submeta"><span>Reason: ${{escapeHtml(note.invalidation_reason)}}</span></div>`
                                : "";
                            const tagsHtml = tags.length
                                ? tags.map((tag) => `<span class="note-tag">${{escapeHtml(tag)}}</span>`).join("")
                                : "";
                            return `
                                <article class="note-item ${{invalid ? "invalid" : ""}}" data-note-id="${{note.id}}">
                                    <div class="note-header">
                                        <div>
                                            <h3 class="note-title">${{escapeHtml(note.title)}}</h3>
                                            <div class="note-submeta">
                                                <span>Created ${{created || "—"}}</span>
                                                <span>Edited ${{updated || "—"}}</span>
                                                ${{invalidBadge}}
                                                ${{invalidWhen}}
                                            </div>
                                        </div>
                                        <div class="note-controls">
                                            <button class="note-inline-btn" type="button" data-action="edit">Edit</button>
                                            ${{invalidateAction}}
                                        </div>
                                    </div>
                                    <div class="note-body">${{renderMarkdown(note.body_markdown || "")}}</div>
                                    ${{invalidReason}}
                                    <div class="note-tags">${{tagsHtml}}</div>
                                    <div class="note-edit-panel" data-edit-panel>
                                        <input class="notes-edit-title" type="text" value="${{escapeHtml(note.title)}}" />
                                        <textarea class="notes-edit-body">${{escapeHtml(note.body_markdown || "")}}</textarea>
                                        <input class="notes-edit-tags" type="text" value="${{escapeHtml(tags.join(", "))}}" />
                                        <div class="note-controls">
                                            <button class="notes-btn notes-btn-primary" type="button" data-action="save-edit">Save</button>
                                            <button class="notes-btn notes-btn-secondary" type="button" data-action="cancel-edit">Cancel</button>
                                        </div>
                                    </div>
                                </article>
                            `;
                        }}

                        function bindTimelineActions() {{
                            timelineEl.querySelectorAll(".note-item").forEach((card) => {{
                                const noteId = card.getAttribute("data-note-id");
                                const panel = card.querySelector("[data-edit-panel]");
                                const titleInput = card.querySelector(".notes-edit-title");
                                const bodyInput = card.querySelector(".notes-edit-body");
                                const tagsInput = card.querySelector(".notes-edit-tags");
                                card.querySelectorAll('[data-action="edit"]').forEach((btn) => {{
                                    btn.addEventListener("click", () => {{
                                        panel.classList.add("active");
                                    }});
                                }});
                                card.querySelectorAll('[data-action="cancel-edit"]').forEach((btn) => {{
                                    btn.addEventListener("click", () => {{
                                        panel.classList.remove("active");
                                    }});
                                }});
                                card.querySelectorAll('[data-action="save-edit"]').forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        try {{
                                            statusEl.textContent = "Saving edit...";
                                            await fetchJson(`/api/notes/${{noteId}}`, {{
                                                method: "PUT",
                                                headers: {{ "Content-Type": "application/json" }},
                                                body: JSON.stringify({{
                                                    title: titleInput.value,
                                                    body: bodyInput.value,
                                                    tags: tagsInput.value,
                                                }}),
                                            }});
                                            statusEl.textContent = "Note updated.";
                                            await refreshAll();
                                        }} catch (error) {{
                                            statusEl.textContent = `Error: ${{error.message}}`;
                                        }}
                                    }});
                                }});
                                card.querySelectorAll('[data-action="invalidate"]').forEach((btn) => {{
                                    btn.addEventListener("click", async () => {{
                                        const reason = window.prompt("Why is this note invalid?", "") || "";
                                        try {{
                                            statusEl.textContent = "Invalidating note...";
                                            await fetchJson(`/api/notes/${{noteId}}/invalidate`, {{
                                                method: "POST",
                                                headers: {{ "Content-Type": "application/json" }},
                                                body: JSON.stringify({{ reason }}),
                                            }});
                                            statusEl.textContent = "Note invalidated.";
                                            await refreshAll();
                                        }} catch (error) {{
                                            statusEl.textContent = `Error: ${{error.message}}`;
                                        }}
                                    }});
                                }});
                            }});
                        }}

                        async function loadTags() {{
                            const payload = await fetchJson("/api/notes/tags");
                            allTags = Array.isArray(payload.tags) ? payload.tags : [];
                            renderTagFilters();
                        }}

                        async function loadNotes() {{
                            const query = activeTag ? `?tag=${{encodeURIComponent(activeTag)}}` : "";
                            const payload = await fetchJson(`/api/notes${{query}}`);
                            const notes = Array.isArray(payload.notes) ? payload.notes : [];
                            if (!notes.length) {{
                                timelineEl.innerHTML = `<div class="empty-state">No notes yet${{activeTag ? ` for #${{escapeHtml(activeTag)}}` : ""}}.</div>`;
                                return;
                            }}
                            timelineEl.innerHTML = notes.map(renderNoteCard).join("");
                            bindTimelineActions();
                        }}

                        async function refreshAll() {{
                            await loadTags();
                            await loadNotes();
                        }}

                        saveBtn.addEventListener("click", async () => {{
                            try {{
                                statusEl.textContent = "Saving note...";
                                await fetchJson("/api/notes", {{
                                    method: "POST",
                                    headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{
                                        title: titleEl.value,
                                        body: bodyEl.value,
                                        tags: tagsEl.value,
                                    }}),
                                }});
                                titleEl.value = "";
                                bodyEl.value = "";
                                tagsEl.value = "";
                                activeTag = "";
                                statusEl.textContent = "Note saved.";
                                await refreshAll();
                            }} catch (error) {{
                                statusEl.textContent = `Error: ${{error.message}}`;
                            }}
                        }});

                        refreshAll().catch((error) => {{
                            statusEl.textContent = `Error: ${{error.message}}`;
                        }});
                    }})();
                </script>
            </body>
        </html>
    """
