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
    output_language TEXT NOT NULL DEFAULT 'en',
    PRIMARY KEY (company_name, id)
);

ALTER TABLE company_news_analyzed
    ADD COLUMN IF NOT EXISTS output_language TEXT NOT NULL DEFAULT 'en';

CREATE INDEX IF NOT EXISTS idx_company_news_analyzed_company_name
    ON company_news_analyzed (company_name);

CREATE INDEX IF NOT EXISTS idx_company_news_analyzed_date_time
    ON company_news_analyzed (news_date_time DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_news_analyzed_unique
    ON company_news_analyzed (company_name, news_title, news_date_time, llm_model, output_language);

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

CREATE TABLE IF NOT EXISTS company_story_state (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    story_title TEXT NOT NULL,
    importance_rank INTEGER NOT NULL DEFAULT 999,
    story_status TEXT NOT NULL DEFAULT 'stable',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    happened_text TEXT,
    happening_text TEXT,
    next_text TEXT,
    open_questions_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    change_log_json TEXT NOT NULL DEFAULT '[]',
    last_event_at TIMESTAMPTZ,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_story_state_unique
    ON company_story_state (company_name, story_key, provider, prompt_style, output_language);

CREATE INDEX IF NOT EXISTS idx_company_story_state_lookup
    ON company_story_state (
        company_name,
        provider,
        prompt_style,
        output_language,
        is_active,
        importance_rank,
        updated_at DESC
    );

CREATE TABLE IF NOT EXISTS company_story_update (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_story_update_lookup
    ON company_story_update (
        company_name,
        story_key,
        provider,
        prompt_style,
        output_language,
        created_at DESC
    );

CREATE TABLE IF NOT EXISTS company_story_qa (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    story_key TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_story_qa_lookup
    ON company_story_qa (
        company_name,
        story_key,
        provider,
        prompt_style,
        output_language,
        created_at DESC
    );

CREATE TABLE IF NOT EXISTS company_story_warmup_state (
    company_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    job_state TEXT NOT NULL DEFAULT 'not_started',
    current_stage TEXT NOT NULL DEFAULT 'idle',
    window_days INTEGER NOT NULL DEFAULT 10,
    slice_days INTEGER NOT NULL DEFAULT 10,
    window_start_date DATE,
    window_end_date DATE,
    total_slices INTEGER NOT NULL DEFAULT 0,
    completed_slices INTEGER NOT NULL DEFAULT 0,
    current_slice_start_date DATE,
    current_slice_end_date DATE,
    last_completed_slice_end_date DATE,
    analysis_started BOOLEAN NOT NULL DEFAULT FALSE,
    analysis_completed BOOLEAN NOT NULL DEFAULT FALSE,
    raw_fetched_count INTEGER NOT NULL DEFAULT 0,
    raw_stored_count INTEGER NOT NULL DEFAULT 0,
    filtered_kept_count INTEGER NOT NULL DEFAULT 0,
    ongoing_story_count INTEGER NOT NULL DEFAULT 0,
    finished_story_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    last_error TEXT,
    failed_stage TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_name, provider, prompt_style, output_language)
);

CREATE INDEX IF NOT EXISTS idx_company_story_warmup_state_lookup
    ON company_story_warmup_state (
        company_name,
        provider,
        prompt_style,
        output_language,
        updated_at DESC
    );

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

CREATE TABLE IF NOT EXISTS company_price_daily (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    volume BIGINT,
    source TEXT NOT NULL DEFAULT 'unknown',
    source_symbol TEXT,
    currency TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_price_daily_unique
    ON company_price_daily (company_name, ticker, trade_date);

CREATE INDEX IF NOT EXISTS idx_company_price_daily_lookup
    ON company_price_daily (company_name, ticker, trade_date DESC);

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

CREATE TABLE IF NOT EXISTS market_news_daily_summary (
    id BIGSERIAL PRIMARY KEY,
    summary_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL,
    news_sources TEXT,
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_news_daily_summary_date
    ON market_news_daily_summary (summary_date, created_at DESC);

CREATE TABLE IF NOT EXISTS market_news_item_analysis (
    id BIGSERIAL PRIMARY KEY,
    news_date DATE NOT NULL,
    news_url TEXT NOT NULL,
    headline TEXT NOT NULL,
    source TEXT,
    source_tag TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    input_payload TEXT NOT NULL,
    output_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_item_analysis_unique
    ON market_news_item_analysis (news_date, news_url, model, output_language, prompt_style);

CREATE INDEX IF NOT EXISTS idx_market_news_item_analysis_lookup
    ON market_news_item_analysis (news_date DESC, model, output_language, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_news_raw (
    id BIGSERIAL PRIMARY KEY,
    news_date DATE NOT NULL,
    news_date_time TIMESTAMPTZ,
    headline TEXT NOT NULL,
    source TEXT,
    source_tag TEXT,
    news_url TEXT NOT NULL,
    summary TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_raw_unique
    ON market_news_raw (news_date, news_url);

CREATE INDEX IF NOT EXISTS idx_market_news_raw_lookup
    ON market_news_raw (news_date DESC, source_tag, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_story_state (
    id BIGSERIAL PRIMARY KEY,
    story_key TEXT NOT NULL,
    story_title TEXT NOT NULL,
    story_summary TEXT,
    importance_rank INTEGER NOT NULL DEFAULT 999,
    story_status TEXT NOT NULL DEFAULT 'stable',
    priority TEXT NOT NULL DEFAULT 'normal',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    happened_text TEXT,
    happening_text TEXT,
    next_text TEXT,
    timeline_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    future_impact_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    change_log_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_event_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_story_state_unique
    ON market_story_state (story_key, provider, prompt_style, output_language, is_active);

CREATE INDEX IF NOT EXISTS idx_market_story_state_lookup
    ON market_story_state (provider, prompt_style, output_language, importance_rank ASC, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_news_daily_cluster (
    id BIGSERIAL PRIMARY KEY,
    cluster_date DATE NOT NULL,
    cluster_key TEXT NOT NULL,
    cluster_title TEXT NOT NULL,
    cluster_summary TEXT NOT NULL DEFAULT '',
    source_news_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_news_daily_cluster_unique
    ON market_news_daily_cluster (cluster_date, cluster_key, provider, prompt_style, output_language);

CREATE INDEX IF NOT EXISTS idx_market_news_daily_cluster_lookup
    ON market_news_daily_cluster (cluster_date DESC, provider, prompt_style, output_language, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_story_update (
    id BIGSERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_style TEXT NOT NULL DEFAULT 'simple',
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_output TEXT,
    stories_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_story_update_lookup
    ON market_story_update (as_of_date DESC, provider, prompt_style, output_language, created_at DESC);

CREATE TABLE IF NOT EXISTS market_story_warmup_state (
    id BIGSERIAL PRIMARY KEY,
    job_key TEXT NOT NULL DEFAULT 'global',
    job_state TEXT NOT NULL DEFAULT 'not_started',
    current_stage TEXT NOT NULL DEFAULT 'idle',
    warmup_window_start DATE,
    warmup_window_end DATE,
    raw_fetched_count INTEGER NOT NULL DEFAULT 0,
    raw_stored_count INTEGER NOT NULL DEFAULT 0,
    filtered_kept_count INTEGER NOT NULL DEFAULT 0,
    ongoing_story_count INTEGER NOT NULL DEFAULT 0,
    finished_story_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_story_warmup_state_unique
    ON market_story_warmup_state (job_key);

CREATE TABLE IF NOT EXISTS market_story_event (
    id BIGSERIAL PRIMARY KEY,
    story_key TEXT NOT NULL,
    event_date TIMESTAMPTZ,
    event_type TEXT NOT NULL DEFAULT 'milestone',
    event_title TEXT NOT NULL,
    event_summary TEXT,
    evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_story_event_lookup
    ON market_story_event (story_key, event_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS company_earnings_event (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    fiscal_period TEXT,
    estimate_eps DOUBLE PRECISION,
    actual_eps DOUBLE PRECISION,
    surprise_percent DOUBLE PRECISION,
    estimate_revenue DOUBLE PRECISION,
    actual_revenue DOUBLE PRECISION,
    guidance_summary TEXT,
    price_reaction_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    analysis_text TEXT,
    provider TEXT,
    model TEXT,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_earnings_event_unique
    ON company_earnings_event (company_name, ticker, earnings_date);

CREATE INDEX IF NOT EXISTS idx_company_earnings_event_lookup
    ON company_earnings_event (company_name, earnings_date DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_macro_event (
    id BIGSERIAL PRIMARY KEY,
    event_code TEXT,
    event_name TEXT NOT NULL,
    category TEXT,
    country TEXT,
    event_date_time TIMESTAMPTZ NOT NULL,
    actual_value TEXT,
    previous_value TEXT,
    consensus_value TEXT,
    unit TEXT,
    importance TEXT,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    impact_summary TEXT,
    provider TEXT,
    model TEXT,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_macro_event_unique
    ON market_macro_event (event_name, event_date_time, country);

CREATE INDEX IF NOT EXISTS idx_market_macro_event_lookup
    ON market_macro_event (event_date_time DESC, category, country, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_price_daily_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_price_daily_snapshot_date
    ON market_price_daily_snapshot (snapshot_date DESC, updated_at DESC);
