CREATE TABLE IF NOT EXISTS market_price_analysis_daily (
    id BIGSERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'prices_v1',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    output_json TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_price_analysis_daily_unique
    ON market_price_analysis_daily (analysis_date, provider, prompt_style, output_language);

CREATE INDEX IF NOT EXISTS idx_market_price_analysis_daily_lookup
    ON market_price_analysis_daily (analysis_date DESC, provider, prompt_style, output_language, updated_at DESC);
