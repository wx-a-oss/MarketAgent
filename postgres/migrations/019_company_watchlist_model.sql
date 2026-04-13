ALTER TABLE company_watchlist
    ADD COLUMN IF NOT EXISTS llm_model TEXT NOT NULL DEFAULT 'gpt-5.4-mini';

UPDATE company_watchlist
SET llm_model = 'gpt-5.4-mini'
WHERE COALESCE(NULLIF(TRIM(llm_model), ''), '') = '';

