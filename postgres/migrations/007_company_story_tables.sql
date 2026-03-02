CREATE TABLE IF NOT EXISTS company_story_state (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    story_title TEXT NOT NULL,
    importance_rank INTEGER NOT NULL DEFAULT 999,
    story_status TEXT NOT NULL DEFAULT 'stable',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    happened_text TEXT,
    happening_text TEXT,
    next_text TEXT,
    open_questions_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    change_log_json TEXT NOT NULL DEFAULT '[]',
    last_event_at TIMESTAMPTZ,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_story_state_unique
    ON company_story_state (company_name, story_key, provider, prompt_style, output_language);

CREATE INDEX IF NOT EXISTS idx_company_story_state_lookup
    ON company_story_state (
        company_name,
        provider,
        prompt_style,
        output_language,
        is_active,
        importance_rank,
        updated_at DESC
    );

CREATE TABLE IF NOT EXISTS company_story_update (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_story_update_lookup
    ON company_story_update (
        company_name,
        story_key,
        provider,
        prompt_style,
        output_language,
        created_at DESC
    );

CREATE TABLE IF NOT EXISTS company_story_qa (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_story_qa_lookup
    ON company_story_qa (
        company_name,
        story_key,
        provider,
        prompt_style,
        output_language,
        created_at DESC
    );
