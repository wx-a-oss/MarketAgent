"""Central registry for DB table/column names used by recent features.

Keep new schema fields here to avoid scattering raw strings across service code.
"""

from __future__ import annotations

# Shared language field
COL_OUTPUT_LANGUAGE = "output_language"

# Company analyzed content
TBL_COMPANY_NEWS_ANALYZED = "company_news_analyzed"

# Market summary storage
TBL_MARKET_NEWS_DAILY_SUMMARY = "market_news_daily_summary"
COL_NEWS_SOURCES = "news_sources"

# Market single news analysis storage
TBL_MARKET_NEWS_ITEM_ANALYSIS = "market_news_item_analysis"
TBL_MARKET_NEWS_RAW = "market_news_raw"
TBL_MARKET_NEWS_DAILY_CLUSTER = "market_news_daily_cluster"
COL_NEWS_DATE = "news_date"
COL_NEWS_URL = "news_url"
COL_HEADLINE = "headline"
COL_SOURCE = "source"
COL_SOURCE_TAG = "source_tag"
COL_PROVIDER = "provider"
COL_MODEL = "model"
COL_PROMPT_STYLE = "prompt_style"
COL_INPUT_PAYLOAD = "input_payload"
COL_OUTPUT_TEXT = "output_text"

# Market daily price snapshot storage
TBL_MARKET_PRICE_DAILY_SNAPSHOT = "market_price_daily_snapshot"
COL_SNAPSHOT_DATE = "snapshot_date"
COL_PAYLOAD = "payload"

# Market story storage
TBL_MARKET_STORY_STATE = "market_story_state"
TBL_MARKET_STORY_UPDATE = "market_story_update"
TBL_MARKET_STORY_WARMUP_STATE = "market_story_warmup_state"
TBL_MARKET_STORY_EVENT = "market_story_event"

# Company earnings storage
TBL_COMPANY_EARNINGS_EVENT = "company_earnings_event"
COL_EARNINGS_DATE = "earnings_date"

# Macro/government release storage
TBL_MARKET_MACRO_EVENT = "market_macro_event"
COL_EVENT_DATE_TIME = "event_date_time"

# Company story storage
TBL_COMPANY_STORY_STATE = "company_story_state"
TBL_COMPANY_STORY_UPDATE = "company_story_update"
TBL_COMPANY_STORY_QA = "company_story_qa"
TBL_COMPANY_STORY_WARMUP_STATE = "company_story_warmup_state"
TBL_COMPANY_NEWS_DAILY_CLUSTER = "company_news_daily_cluster"
COL_STORY_KEY = "story_key"

# Company stock move analysis storage
TBL_COMPANY_PRICE_MOVE_ANALYSIS = "company_price_move_analysis"
COL_RANGE_KEY = "range_key"
COL_POINT_DATE_TIME = "point_date_time"

# Company daily price cache
TBL_COMPANY_PRICE_DAILY = "company_price_daily"
COL_TICKER = "ticker"
COL_TRADE_DATE = "trade_date"
