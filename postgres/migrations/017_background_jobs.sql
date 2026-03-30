CREATE TABLE IF NOT EXISTS background_job (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    job_key TEXT NOT NULL,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL DEFAULT '',
    provider TEXT,
    model TEXT,
    output_language TEXT,
    prompt_style TEXT,
    target_entity TEXT,
    target_date DATE,
    window_start DATE,
    window_end DATE,
    input_char_count INTEGER NOT NULL DEFAULT 0,
    input_item_count INTEGER NOT NULL DEFAULT 0,
    output_char_count INTEGER NOT NULL DEFAULT 0,
    elapsed_sec DOUBLE PRECISION NOT NULL DEFAULT 0,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary TEXT,
    error_text TEXT,
    owner_pid BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_background_job_key_status
    ON background_job (job_key, status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_background_job_lookup
    ON background_job (job_type, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS background_job_stage (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES background_job(id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    elapsed_sec DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_background_job_stage_lookup
    ON background_job_stage (job_id, id ASC);
