CREATE TABLE IF NOT EXISTS company_story_warmup_state (
    company_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    job_state TEXT NOT NULL DEFAULT 'not_started',
    current_stage TEXT NOT NULL DEFAULT 'idle',
    window_days INTEGER NOT NULL DEFAULT 10,
    slice_days INTEGER NOT NULL DEFAULT 10,
    window_start_date DATE,
    window_end_date DATE,
    total_slices INTEGER NOT NULL DEFAULT 0,
    completed_slices INTEGER NOT NULL DEFAULT 0,
    current_slice_start_date DATE,
    current_slice_end_date DATE,
    last_completed_slice_end_date DATE,
    analysis_started BOOLEAN NOT NULL DEFAULT FALSE,
    analysis_completed BOOLEAN NOT NULL DEFAULT FALSE,
    raw_fetched_count INTEGER NOT NULL DEFAULT 0,
    raw_stored_count INTEGER NOT NULL DEFAULT 0,
    filtered_kept_count INTEGER NOT NULL DEFAULT 0,
    ongoing_story_count INTEGER NOT NULL DEFAULT 0,
    finished_story_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    last_error TEXT,
    failed_stage TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_name, provider, prompt_style, output_language)
);

CREATE INDEX IF NOT EXISTS idx_company_story_warmup_state_lookup
    ON company_story_warmup_state (
        company_name,
        provider,
        prompt_style,
        output_language,
        updated_at DESC
    );
