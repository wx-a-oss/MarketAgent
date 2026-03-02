ALTER TABLE company_news_analyzed
ADD COLUMN IF NOT EXISTS output_language TEXT NOT NULL DEFAULT 'en';

DROP INDEX IF EXISTS idx_company_news_analyzed_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_news_analyzed_unique
    ON company_news_analyzed (company_name, news_title, news_date_time, llm_model, output_language);
