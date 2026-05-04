-- LLM API usage tracking for cost monitoring.

CREATE TABLE IF NOT EXISTS llm_usage_log (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    company_name TEXT,
    module TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    cost_usd DOUBLE PRECISION,
    input_char_count INTEGER,
    output_char_count INTEGER,
    response_time_ms INTEGER,
    used_web_search BOOLEAN DEFAULT FALSE,
    cache_hit BOOLEAN,
    cached_tokens INTEGER,
    request_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_log_created ON llm_usage_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_purpose ON llm_usage_log (purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_company ON llm_usage_log (company_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_module ON llm_usage_log (module, created_at DESC);
