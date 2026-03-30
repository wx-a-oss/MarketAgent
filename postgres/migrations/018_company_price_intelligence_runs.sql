CREATE TABLE IF NOT EXISTS company_price_intelligence_run (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    output_language TEXT NOT NULL,
    context_window_days INTEGER NOT NULL,
    focus_window_days INTEGER NOT NULL,
    input_payload TEXT NOT NULL,
    output_json TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_price_intelligence_run_lookup
    ON company_price_intelligence_run (
        company_name,
        created_at DESC,
        id DESC
    );
