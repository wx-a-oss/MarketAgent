-- Adds persisted history for Market tab daily LLM summaries.
CREATE TABLE IF NOT EXISTS market_news_daily_summary (
    id BIGSERIAL PRIMARY KEY,
    summary_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    news_sources TEXT,
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE market_news_daily_summary
ADD COLUMN IF NOT EXISTS news_sources TEXT;

CREATE INDEX IF NOT EXISTS idx_market_news_daily_summary_date
    ON market_news_daily_summary (summary_date, created_at DESC);
