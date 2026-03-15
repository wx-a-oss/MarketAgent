CREATE TABLE IF NOT EXISTS market_news_raw (
    id BIGSERIAL PRIMARY KEY,
    news_date DATE NOT NULL,
    news_date_time TIMESTAMPTZ,
    headline TEXT NOT NULL,
    source TEXT,
    source_tag TEXT,
    news_url TEXT NOT NULL,
    summary TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_raw_unique
    ON market_news_raw (news_date, news_url);

CREATE INDEX IF NOT EXISTS idx_market_news_raw_lookup
    ON market_news_raw (news_date DESC, source_tag, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_story_state (
    id BIGSERIAL PRIMARY KEY,
    story_key TEXT NOT NULL,
    story_title TEXT NOT NULL,
    importance_rank INTEGER NOT NULL DEFAULT 999,
    story_status TEXT NOT NULL DEFAULT 'stable',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    happened_text TEXT,
    happening_text TEXT,
    next_text TEXT,
    evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    change_log_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_event_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_story_state_unique
    ON market_story_state (story_key, provider, prompt_style, output_language, is_active);

CREATE INDEX IF NOT EXISTS idx_market_story_state_lookup
    ON market_story_state (provider, prompt_style, output_language, importance_rank ASC, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_story_update (
    id BIGSERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_output TEXT,
    stories_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_story_update_lookup
    ON market_story_update (as_of_date DESC, provider, prompt_style, output_language, created_at DESC);

CREATE TABLE IF NOT EXISTS market_story_warmup_state (
    id BIGSERIAL PRIMARY KEY,
    job_key TEXT NOT NULL DEFAULT 'global',
    job_state TEXT NOT NULL DEFAULT 'not_started',
    current_stage TEXT NOT NULL DEFAULT 'idle',
    warmup_window_start DATE,
    warmup_window_end DATE,
    raw_fetched_count INTEGER NOT NULL DEFAULT 0,
    raw_stored_count INTEGER NOT NULL DEFAULT 0,
    filtered_kept_count INTEGER NOT NULL DEFAULT 0,
    ongoing_story_count INTEGER NOT NULL DEFAULT 0,
    finished_story_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_story_warmup_state_unique
    ON market_story_warmup_state (job_key);

CREATE TABLE IF NOT EXISTS market_story_event (
    id BIGSERIAL PRIMARY KEY,
    story_key TEXT NOT NULL,
    event_date TIMESTAMPTZ,
    event_type TEXT NOT NULL DEFAULT 'milestone',
    event_title TEXT NOT NULL,
    event_summary TEXT,
    evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_story_event_lookup
    ON market_story_event (story_key, event_date DESC, created_at DESC);
