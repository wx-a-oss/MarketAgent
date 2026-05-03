-- Comprehensive earnings report storage with structured JSONB columns.
-- Replaces the lightweight company_earnings_event approach with
-- full LLM-extracted earnings call data.

CREATE TABLE IF NOT EXISTS company_earnings_report (
    id SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,

    -- Quarter identification
    fiscal_year TEXT NOT NULL,
    fiscal_quarter TEXT NOT NULL,
    quarter_end_date DATE,
    earnings_date DATE,

    -- Structured financial data
    financials JSONB NOT NULL DEFAULT '{}',

    -- Open-ended company-specific metrics (LLM decides structure)
    company_specific JSONB NOT NULL DEFAULT '[]',

    -- Qualitative analysis
    analysis JSONB NOT NULL DEFAULT '{}',

    -- Estimates vs actuals
    estimates JSONB NOT NULL DEFAULT '{}',

    -- Price reaction around earnings
    price_reaction JSONB NOT NULL DEFAULT '{}',

    -- Raw LLM response for debugging
    raw_llm_response TEXT,

    -- Metadata
    provider TEXT NOT NULL DEFAULT 'openai',
    model TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (company_name, fiscal_year, fiscal_quarter)
);

CREATE INDEX IF NOT EXISTS idx_earnings_report_lookup
    ON company_earnings_report (company_name, earnings_date DESC, updated_at DESC);
