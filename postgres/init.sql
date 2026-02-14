DROP TABLE IF EXISTS company_news;

CREATE TABLE IF NOT EXISTS company_news_raw (
    id BIGSERIAL NOT NULL,
    company_name TEXT NOT NULL,
    news_date_time TIMESTAMPTZ NOT NULL,
    news_title TEXT NOT NULL,
    content TEXT,
    source TEXT,
    source_link TEXT,
    is_analyzed BOOLEAN NOT NULL DEFAULT FALSE,
    is_filtered BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (company_name, id)
);

CREATE INDEX IF NOT EXISTS idx_company_news_raw_company_name
    ON company_news_raw (company_name);

CREATE INDEX IF NOT EXISTS idx_company_news_raw_date_time
    ON company_news_raw (news_date_time DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_news_raw_unique
    ON company_news_raw (company_name, news_title, news_date_time);

CREATE TABLE IF NOT EXISTS company_news_analyzed (
    id BIGSERIAL NOT NULL,
    company_name TEXT NOT NULL,
    news_date_time TIMESTAMPTZ NOT NULL,
    news_title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    source_link TEXT,
    llm_model TEXT NOT NULL,
    PRIMARY KEY (company_name, id)
);

CREATE INDEX IF NOT EXISTS idx_company_news_analyzed_company_name
    ON company_news_analyzed (company_name);

CREATE INDEX IF NOT EXISTS idx_company_news_analyzed_date_time
    ON company_news_analyzed (news_date_time DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_news_analyzed_unique
    ON company_news_analyzed (company_name, news_title, news_date_time, llm_model);

CREATE TABLE IF NOT EXISTS company_news_dropped (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    raw_news_id BIGINT,
    news_date_time TIMESTAMPTZ NOT NULL,
    news_title TEXT NOT NULL,
    raw_content TEXT,
    raw_source TEXT,
    raw_source_link TEXT,
    raw_is_analyzed BOOLEAN NOT NULL DEFAULT FALSE,
    analyzed_content TEXT,
    analyzed_source TEXT,
    analyzed_source_link TEXT,
    analyzed_llm_model TEXT,
    drop_reason TEXT,
    dropped_by TEXT,
    dropped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_news_dropped_company_name
    ON company_news_dropped (company_name, dropped_at DESC);

CREATE TABLE IF NOT EXISTS company_watchlist (
    company_name TEXT PRIMARY KEY,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS news_report (
    company_name TEXT NOT NULL,
    beginning_date DATE NOT NULL,
    end_date DATE NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_name, beginning_date, end_date)
);

CREATE TABLE IF NOT EXISTS company_profile (
    company_name TEXT PRIMARY KEY,
    ticker TEXT,
    name TEXT,
    exchange TEXT,
    currency TEXT,
    country TEXT,
    ipo DATE,
    weburl TEXT,
    logo TEXT,
    finnhub_industry TEXT,
    phone TEXT,
    market_capitalization NUMERIC,
    share_outstanding NUMERIC,
    cusip TEXT,
    isin TEXT,
    lei TEXT,
    properties_extension JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
