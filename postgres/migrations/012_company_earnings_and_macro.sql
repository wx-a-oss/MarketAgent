CREATE TABLE IF NOT EXISTS company_earnings_event (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    fiscal_period TEXT,
    estimate_eps DOUBLE PRECISION,
    actual_eps DOUBLE PRECISION,
    surprise_percent DOUBLE PRECISION,
    estimate_revenue DOUBLE PRECISION,
    actual_revenue DOUBLE PRECISION,
    guidance_summary TEXT,
    price_reaction_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    analysis_text TEXT,
    provider TEXT,
    model TEXT,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_earnings_event_unique
    ON company_earnings_event (company_name, ticker, earnings_date);

CREATE INDEX IF NOT EXISTS idx_company_earnings_event_lookup
    ON company_earnings_event (company_name, earnings_date DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_macro_event (
    id BIGSERIAL PRIMARY KEY,
    event_code TEXT,
    event_name TEXT NOT NULL,
    category TEXT,
    country TEXT,
    event_date_time TIMESTAMPTZ NOT NULL,
    actual_value TEXT,
    previous_value TEXT,
    consensus_value TEXT,
    unit TEXT,
    importance TEXT,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    impact_summary TEXT,
    provider TEXT,
    model TEXT,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_macro_event_unique
    ON market_macro_event (event_name, event_date_time, country);

CREATE INDEX IF NOT EXISTS idx_market_macro_event_lookup
    ON market_macro_event (event_date_time DESC, category, country, updated_at DESC);
