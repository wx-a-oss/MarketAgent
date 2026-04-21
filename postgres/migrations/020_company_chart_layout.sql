CREATE TABLE IF NOT EXISTS company_chart_layout (
    company_name TEXT PRIMARY KEY,
    position_index INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT company_chart_layout_company_fk
        FOREIGN KEY (company_name)
        REFERENCES company_watchlist(company_name)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_chart_layout_position
    ON company_chart_layout (position_index);
