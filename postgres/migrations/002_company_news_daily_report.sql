-- Daily company report snapshots (provider/prompt-specific; model version overwrites per provider).
CREATE TABLE IF NOT EXISTS company_news_daily_report (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    report_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_news_daily_report_lookup
    ON company_news_daily_report (
        company_name,
        report_date DESC,
        provider,
        prompt_style,
        created_at DESC
    );
