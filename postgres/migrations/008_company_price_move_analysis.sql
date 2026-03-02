CREATE TABLE IF NOT EXISTS company_price_move_analysis (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    range_key TEXT NOT NULL,
    point_date_time TIMESTAMPTZ NOT NULL,
    point_label TEXT NOT NULL,
    close_price DOUBLE PRECISION,
    pct_change DOUBLE PRECISION,
    volume BIGINT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_price_move_analysis_unique
    ON company_price_move_analysis (
        company_name,
        ticker,
        range_key,
        point_date_time,
        provider,
        prompt_style,
        output_language
    );

CREATE INDEX IF NOT EXISTS idx_company_price_move_analysis_lookup
    ON company_price_move_analysis (
        company_name,
        ticker,
        range_key,
        provider,
        prompt_style,
        output_language,
        updated_at DESC
    );
