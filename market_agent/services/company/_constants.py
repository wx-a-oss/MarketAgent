"""Module-level constants shared across company service sub-modules."""

from __future__ import annotations

import logging
import os

from market_agent.config.models import DEFAULT_COMPANY_OPENAI_MODEL

DEFAULT_MODEL = DEFAULT_COMPANY_OPENAI_MODEL
DEFAULT_PROVIDER = "openai"
DEFAULT_SOURCE = "openai"
FINNHUB_AUTO_ANALYZE_LIMIT = 10
ANALYZE_DAY_BATCH_SIZE = 3
FILTER_DAY_BATCH_SIZE = 10
DEFAULT_STORY_WARMUP_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_DAYS", "14").strip() or "14")
)
DEFAULT_STORY_WARMUP_SLICE_DAYS = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_SLICE_DAYS", "1").strip() or "1")
)
DEFAULT_STORY_WARMUP_MAX_RETRIES = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_MAX_RETRIES", "3").strip() or "3")
)
DEFAULT_STORY_WARMUP_RETRY_DELAY_SEC = max(
    1, int(os.getenv("COMPANY_STORY_WARMUP_RETRY_DELAY_SEC", "60").strip() or "60")
)
DEFAULT_STORY_WARMUP_STALE_MINUTES = max(
    5, int(os.getenv("COMPANY_STORY_WARMUP_STALE_MINUTES", "180").strip() or "180")
)
STORY_WARMUP_PROMPT_JSON_LIMIT = max(
    12000, int(os.getenv("COMPANY_STORY_WARMUP_PROMPT_JSON_LIMIT", "45000").strip() or "45000")
)
STORY_WARMUP_CHUNK_SIZE = max(
    5, int(os.getenv("COMPANY_STORY_WARMUP_CHUNK_SIZE", "25").strip() or "25")
)
COMPANY_DAILY_CLUSTER_MIN = 3
COMPANY_DAILY_CLUSTER_MAX = 8
PRICE_ANALYSIS_REPORT_LIMIT = 30
PRICE_ANALYSIS_RAW_FALLBACK_LIMIT = 30
PRICE_ANALYSIS_MARKET_SUMMARY_LIMIT = 5

logger = logging.getLogger("uvicorn.error")
