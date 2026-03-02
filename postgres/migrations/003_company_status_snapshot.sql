-- Company status snapshot layer (rolling company state built from daily/weekly reports)
CREATE TABLE IF NOT EXISTS company_status_snapshot (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    window_start_date DATE NOT NULL,
    window_end_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_status_snapshot_lookup
    ON company_status_snapshot (
        company_name,
        provider,
        prompt_style,
        created_at DESC
    );
