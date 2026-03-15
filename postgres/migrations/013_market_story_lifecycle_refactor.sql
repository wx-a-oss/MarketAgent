ALTER TABLE market_story_state
    ADD COLUMN IF NOT EXISTS story_summary TEXT,
    ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS timeline_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS future_impact_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS market_news_daily_cluster (
    id BIGSERIAL PRIMARY KEY,
    cluster_date DATE NOT NULL,
    cluster_key TEXT NOT NULL,
    cluster_title TEXT NOT NULL,
    cluster_summary TEXT NOT NULL DEFAULT '',
    source_news_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_daily_cluster_unique
    ON market_news_daily_cluster (cluster_date, cluster_key, provider, prompt_style, output_language);

CREATE INDEX IF NOT EXISTS idx_market_news_daily_cluster_lookup
    ON market_news_daily_cluster (cluster_date DESC, provider, prompt_style, output_language, updated_at DESC);
