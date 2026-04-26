"""Backward-compatible re-exports. Logic now split into domain modules."""

from market_agent.workflows.market_macro import *  # noqa: F401,F403
from market_agent.workflows.market_news import *  # noqa: F401,F403
from market_agent.workflows.market_stories import *  # noqa: F401,F403
from market_agent.workflows.market_clusters import *  # noqa: F401,F403

# Private names used by tests, server, and the app shim
from market_agent.workflows.market_news import (  # noqa: F401
    _current_app_date,
    _fetch_market_news_for_day,
    _generate_market_research_text,
    _get_market_raw_coverage,
    _has_market_raw_for_day,
    _upsert_market_news_raw,
)
from market_agent.workflows.market_macro import (  # noqa: F401
    _fetch_macro_calendar_with_llm,
    _resolve_macro_extension_window,
    _resolve_macro_maintenance_window,
    _upsert_market_macro_event,
)
from market_agent.workflows.market_stories import (  # noqa: F401
    _generate_market_story_map,
    _generate_market_story_payload,
    _upsert_market_story_state_batch,
    _upsert_market_story_warmup_state,
)

# Infrastructure names that sub-modules look up through _shim() and tests
# may monkeypatch on this shim module.
from market_agent.db.bootstrap import ensure_database_schema, get_connection  # noqa: F401
from market_agent.llms.news_registry import get_news_provider  # noqa: F401
