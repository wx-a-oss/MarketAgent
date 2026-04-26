"""Backward-compatible re-exports. Logic now split into domain modules."""

from market_agent.services.company._constants import *  # noqa: F401,F403
from market_agent.services.company._helpers import *  # noqa: F401,F403
from market_agent.services.company.watchlist import *  # noqa: F401,F403
from market_agent.services.company.notes import *  # noqa: F401,F403
from market_agent.services.company.profiles import *  # noqa: F401,F403
from market_agent.services.company.news_crud import *  # noqa: F401,F403
from market_agent.services.company.reports import *  # noqa: F401,F403
from market_agent.services.company.status_snapshot import *  # noqa: F401,F403
from market_agent.services.company.stories import *  # noqa: F401,F403
from market_agent.services.company.story_warmup import *  # noqa: F401,F403

# Private names imported by external modules (workflows, tests, analysis shim).
# star-imports skip names starting with underscore, so we re-export explicitly.
from market_agent.services.company._helpers import (  # noqa: F401
    _as_text,
    _build_output_language_line,
    _decode_llm_content,
    _ensure_news_schema,
    _extract_analyzed_content,
    _extract_drop_reason,
    _format_story_section_bullets,
    _is_item_relevant,
    _normalize_company_name,
    _normalize_note_tag,
    _normalize_note_tags,
    _normalize_story_key,
    _normalize_story_record,
    _normalize_ticker,
    _parse_date_time,
    _parse_iso_date,
    _parse_json_object,
    _parse_story_warmup_state_datetime,
    _replace_user_note_tags,
    _resolve_symbol_from_lookup,
    _row_to_story_state,
    _row_to_story_warmup_state,
    _story_timeline_from_legacy_fields,
    _tag_source,
    _days,
    _group_story_states,
)
from market_agent.services.company.profiles import (  # noqa: F401
    _build_fetch_ranges_for_slice,
    _count_company_raw_for_range,
    _extract_profile_extension,
    _has_company_raw_for_day,
    _resolve_company_ticker,
)
from market_agent.services.company.news_crud import (  # noqa: F401
    _archive_dropped_news_with_cursor,
    _delete_news_by_signature,
    _delete_news_by_signature_with_cursor,
    _delete_raw_news_by_id,
    _exists_analyzed_article,
    _exists_raw_article,
    _fetch_news_with_source,
    _filter_company_news_range_raw,
    _filter_finnhub_items_in_batches,
    _get_latest_news_date,
    _mark_raw_news_filtered_by_id,
    _mark_raw_news_filtered_by_ids,
    _news_item_from_payload,
    _news_items_from_provider,
    _store_articles,
)
from market_agent.services.company.reports import (  # noqa: F401
    _build_company_daily_report_input_items,
    _build_company_monthly_report_prompt,
    _build_company_story_cluster_input_items,
    _build_company_story_incremental_news_items,
    _build_monthly_report_input_items,
    _build_weekly_report_input_items,
    _normalize_company_cluster_rows,
    _normalize_structured_period_report,
    _render_period_report_as_text,
    _replace_company_daily_clusters,
    _store_weekly_report,
    _upsert_company_daily_report,
)
from market_agent.services.company.status_snapshot import (  # noqa: F401
    _build_company_price_intelligence_input,
    _build_company_quick_price_intelligence_input,
    _build_company_status_input_coverage,
    _build_company_status_macro_context,
    _build_company_status_market_daily_summary_context,
    _build_company_status_market_snapshot_context,
    _build_company_status_market_story_context,
    _build_company_status_price_context,
    _build_company_status_price_move_context,
    _build_company_status_raw_news_fallback,
    _insert_company_price_intelligence_run,
    _normalize_company_quick_price_intelligence_payload,
    _normalize_company_status_payload,
    _render_company_quick_price_intelligence_markdown,
    _render_company_status_markdown,
    _upsert_company_status_snapshot,
)
from market_agent.services.company.stories import (  # noqa: F401
    _apply_incremental_story_updates,
    _get_company_story_qa_row,
    _insert_story_qa,
    _normalize_incremental_story_item,
    _normalize_story_routing_result,
    _persist_story_refresh,
)
from market_agent.services.company.story_warmup import (  # noqa: F401
    _WARMUP_THREADS,
    _WARMUP_THREADS_LOCK,
    _build_company_story_warmup_input_items,
    _build_story_warmup_slices,
    _ensure_story_warmup_thread,
    _generate_company_story_warmup_story_map,
    _get_company_story_warmup_invalid_reason,
    _normalize_story_warmup_groups,
    _run_company_story_warmup_job,
    _run_company_story_warmup_job_inner,
    _story_warmup_key,
    _upsert_story_warmup_state,
)
from market_agent.services.company.prompts import (  # noqa: F401
    _build_company_story_warmup_consolidation_prompt,
)
