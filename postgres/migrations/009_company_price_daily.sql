CREATE TABLE IF NOT EXISTS company_price_daily (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    volume BIGINT,
    source TEXT NOT NULL DEFAULT 'unknown',
    source_symbol TEXT,
    currency TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_price_daily_unique
    ON company_price_daily (company_name, ticker, trade_date);

CREATE INDEX IF NOT EXISTS idx_company_price_daily_lookup
    ON company_price_daily (company_name, ticker, trade_date DESC);
