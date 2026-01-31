CREATE TABLE IF NOT EXISTS company_news (
    id BIGSERIAL NOT NULL,
    company_name TEXT NOT NULL,
    news_date_time TIMESTAMPTZ NOT NULL,
    news_title TEXT NOT NULL,
    original_content TEXT,
    llm_analyzed_content TEXT NOT NULL,
    news_source_link TEXT,
    news_source TEXT,
    PRIMARY KEY (company_name, id)
);

CREATE INDEX IF NOT EXISTS idx_company_news_company_name
    ON company_news (company_name);

CREATE INDEX IF NOT EXISTS idx_company_news_date_time
    ON company_news (news_date_time DESC);

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
