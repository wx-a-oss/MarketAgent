CREATE TABLE IF NOT EXISTS market_news_item_analysis (
    id BIGSERIAL PRIMARY KEY,
    news_date DATE NOT NULL,
    news_url TEXT NOT NULL,
    headline TEXT NOT NULL,
    source TEXT,
    source_tag TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_item_analysis_unique
    ON market_news_item_analysis (news_date, news_url, model, output_language, prompt_style);

CREATE INDEX IF NOT EXISTS idx_market_news_item_analysis_lookup
    ON market_news_item_analysis (news_date DESC, model, output_language, updated_at DESC);
