CREATE TABLE IF NOT EXISTS user_note (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    validity_state TEXT NOT NULL DEFAULT 'valid',
    invalidation_reason TEXT,
    invalidated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_note_timeline
    ON user_note (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_user_note_validity
    ON user_note (validity_state, created_at DESC);

CREATE TABLE IF NOT EXISTS user_note_tag (
    id BIGSERIAL PRIMARY KEY,
    note_id BIGINT NOT NULL REFERENCES user_note(id) ON DELETE CASCADE,
    tag_text TEXT NOT NULL,
    normalized_tag TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_note_tag_unique
    ON user_note_tag (note_id, normalized_tag);

CREATE INDEX IF NOT EXISTS idx_user_note_tag_lookup
    ON user_note_tag (normalized_tag, note_id);
