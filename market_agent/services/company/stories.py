"""Story state/Q&A functions."""

from __future__ import annotations

import json
import logging
import time as pytime
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.llms.news_registry import get_news_provider
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    COL_STORY_KEY,
    TBL_COMPANY_STORY_QA,
    TBL_COMPANY_STORY_STATE,
    TBL_COMPANY_STORY_UPDATE,
)
from market_agent.services.company._constants import DEFAULT_MODEL, DEFAULT_PROVIDER
from market_agent.services.company._helpers import (
    _as_text,
    _ensure_news_schema,
    _normalize_company_name,
    _normalize_story_key,
    _normalize_story_record,
    _parse_json_object,
    _row_to_story_state,
)
from market_agent.services.company.prompts import (
    _build_company_story_qa_merge_prompt,
    _build_company_story_qa_prompt,
    _build_company_story_routing_prompt,
    _build_company_story_update_prompt,
    _build_incremental_existing_story_prompt,
    _build_incremental_new_story_prompt,
)
from market_agent.llms.usage_context import usage_context
from market_agent.services.company.reports import list_company_daily_clusters

logger = logging.getLogger("uvicorn.error")


def list_company_story_states(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, {COL_STORY_KEY}, story_title, story_summary,
                       importance_rank, story_status, priority, confidence,
                       happened_text, happening_text, next_text,
                       timeline_json, future_impact_json, open_questions_json,
                       evidence_json, change_log_json, last_event_at,
                       provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                       is_active, updated_at, created_at
                FROM {TBL_COMPANY_STORY_STATE}
                WHERE company_name = %s AND provider = %s AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s AND is_active = TRUE
                ORDER BY importance_rank ASC, updated_at DESC, id DESC
                """,
                (company_name, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [_row_to_story_state(row) for row in rows]


def get_company_story_state(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, {COL_STORY_KEY}, story_title, story_summary,
                       importance_rank, story_status, priority, confidence,
                       happened_text, happening_text, next_text,
                       timeline_json, future_impact_json, open_questions_json,
                       evidence_json, change_log_json, last_event_at,
                       provider, model, prompt_style, {COL_OUTPUT_LANGUAGE},
                       is_active, updated_at, created_at
                FROM {TBL_COMPANY_STORY_STATE}
                WHERE company_name = %s AND {COL_STORY_KEY} = %s AND provider = %s
                  AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC LIMIT 1
                """,
                (company_name, story_key, provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_story_state(row)


def list_company_story_updates(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    limit: int = 12,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    safe_limit = max(1, min(int(limit), 60))
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, {COL_STORY_KEY}, as_of_date, provider, model,
                       prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, output_json, created_at
                FROM {TBL_COMPANY_STORY_UPDATE}
                WHERE company_name = %s AND {COL_STORY_KEY} = %s AND provider = %s
                  AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                (company_name, story_key, provider_name, prompt_style, output_language, safe_limit),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]), "company_name": row["company_name"],
            "story_key": row[COL_STORY_KEY], "as_of_date": row["as_of_date"].isoformat(),
            "provider": row["provider"], "model": row["model"],
            "prompt_style": row["prompt_style"], "output_language": row[COL_OUTPUT_LANGUAGE],
            "input_payload": row["input_payload"] or "", "output_json": row["output_json"] or "",
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def get_latest_company_story_update_date(
    company_name: str,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> str:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(as_of_date) AS latest_story_date FROM {TBL_COMPANY_STORY_UPDATE} WHERE company_name = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s",
                (company_name, provider_name, prompt_style, output_language),
            )
            row = cur.fetchone()
    latest = row["latest_story_date"] if row else None
    return latest.isoformat() if latest else ""


def list_company_story_qa(
    company_name: str,
    *,
    story_key: str,
    provider_name: str = DEFAULT_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    limit: int = 12,
) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    safe_limit = max(1, min(int(limit), 40))
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, company_name, {COL_STORY_KEY}, question, answer, provider, model,
                       prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, created_at
                FROM {TBL_COMPANY_STORY_QA}
                WHERE company_name = %s AND {COL_STORY_KEY} = %s AND provider = %s
                  AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                (company_name, story_key, provider_name, prompt_style, output_language, safe_limit),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]), "company_name": row["company_name"],
            "story_key": row[COL_STORY_KEY], "question": row["question"] or "",
            "answer": row["answer"] or "", "provider": row["provider"], "model": row["model"],
            "prompt_style": row["prompt_style"], "output_language": row[COL_OUTPUT_LANGUAGE],
            "input_payload": row["input_payload"] or "",
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for row in rows
    ]


def refresh_company_story_states(
    company_name: str,
    *,
    as_of_date: Optional[date] = None,
    window_days: int = 21,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    _ensure_news_schema()
    started_at = pytime.perf_counter()
    company_name = _normalize_company_name(company_name)
    if not company_name:
        return {"generated": False, "story_count": 0, "elapsed_sec": 0.0}
    end_date = as_of_date or datetime.now(timezone.utc).date()
    existing = list_company_story_states(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    clusters = list_company_daily_clusters(company_name, target_date=end_date, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    if not clusters:
        return {"generated": False, "story_count": len(existing), "routed_cluster_count": 0, "updated_story_count": 0, "new_story_count": 0, "ignored_cluster_count": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    routing_prompt = _build_company_story_routing_prompt(company_name, as_of_date=end_date, prompt_style=prompt_style, output_language=output_language, existing_stories=existing, clusters=clusters)
    with usage_context("company_stories", company_name=company_name, module="company"):
        routing_raw_output = provider.generate_text(prompt=routing_prompt)
    routing_payload = _parse_json_object(routing_raw_output) or {}
    routing_result = _normalize_story_routing_result(existing_stories=existing, clusters=clusters, payload=routing_payload)
    applied = _apply_incremental_story_updates(company_name=company_name, as_of_date=end_date, provider=provider, existing_stories=existing, routed=routing_result, prompt_style=prompt_style, output_language=output_language)
    final_stories = applied["stories"]
    if not final_stories:
        return {"generated": False, "story_count": 0, "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}
    _persist_story_refresh(company_name=company_name, as_of_date=end_date, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"routing_prompt": routing_prompt, "routing_result": routing_result, "daily_clusters": clusters, "existing_story_count": len(existing), "updated_story_keys": applied["updated_story_keys"], "new_story_keys": applied["new_story_keys"]}, raw_output=json.dumps({"routing": routing_payload, "applied": applied["raw_outputs"]}, ensure_ascii=False), stories=final_stories)
    return {"generated": True, "story_count": len(final_stories), "routed_cluster_count": len(clusters), "updated_story_count": len(applied["updated_story_keys"]), "new_story_count": len(applied["new_story_keys"]), "ignored_cluster_count": len(routing_result["ignored_items"]), "elapsed_sec": round(pytime.perf_counter() - started_at, 2)}


def ask_company_story_question(
    company_name: str,
    *,
    story_key: str,
    question: str,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 90,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    story_key = str(story_key or "").strip()
    question = str(question or "").strip()
    if not company_name or not story_key or not question:
        return None
    story = get_company_story_state(company_name, story_key=story_key, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    if not story:
        return None
    updates = list_company_story_updates(company_name, story_key=story_key, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language, limit=4)
    prompt = _build_company_story_qa_prompt(company_name=company_name, output_language=output_language, story=story, recent_updates=updates, question=question)
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    with usage_context("company_stories", company_name=company_name, module="company"):
        answer = provider.generate_text(prompt=prompt)
    row = _insert_story_qa(company_name=company_name, story_key=story_key, question=question, answer=answer, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"prompt": prompt, "story": story, "recent_updates": updates})
    return row


def merge_company_story_qa_answer(
    company_name: str,
    *,
    story_key: str,
    qa_id: int,
    provider_name: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
    temperature: float = 0.2,
    timeout_sec: int = 90,
) -> Optional[Dict[str, Any]]:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    story_key = str(story_key or "").strip()
    if not company_name or not story_key:
        return None
    story = get_company_story_state(company_name, story_key=story_key, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    if not story:
        return None
    qa_row = _get_company_story_qa_row(company_name, story_key=story_key, qa_id=qa_id)
    if not qa_row:
        return None
    recent_updates = list_company_story_updates(company_name, story_key=story_key, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language, limit=4)
    prompt = _build_company_story_qa_merge_prompt(company_name=company_name, output_language=output_language, story=story, recent_updates=recent_updates, qa_row=qa_row)
    provider = get_news_provider(provider_name, model=model, temperature=temperature, timeout_sec=timeout_sec)
    with usage_context("company_stories", company_name=company_name, module="company"):
        raw_output = provider.generate_text(prompt=prompt)
    payload = _parse_json_object(raw_output) or {}
    merged_story = _normalize_incremental_story_item(payload, fallback_story_key=story_key, fallback_story_title=str(story.get("story_title") or story_key), fallback_rank=int(story.get("importance_rank") or 999))
    if not merged_story:
        return None
    all_stories = list_company_story_states(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    merged_stories: List[Dict[str, Any]] = []
    replaced = False
    for item in all_stories:
        if str(item.get("story_key") or "").strip() == story_key:
            merged_stories.append(merged_story)
            replaced = True
        else:
            merged_stories.append(item)
    if not replaced:
        merged_stories.append(merged_story)
    merged_stories = sorted([_normalize_story_record(item) for item in merged_stories if isinstance(item, dict)], key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or "")))
    _persist_story_refresh(company_name=company_name, as_of_date=datetime.now(timezone.utc).date(), provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"merge_source": "story_qa", "qa_row": qa_row, "story": story, "recent_updates": recent_updates, "prompt": prompt}, raw_output=raw_output, stories=merged_stories)
    return merged_story


def update_company_story_status(
    company_name: str, *, story_key: str, story_status: str,
    provider_name: str = DEFAULT_PROVIDER, prompt_style: str = "simple", output_language: str = "zh-CN",
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {TBL_COMPANY_STORY_STATE} SET story_status = %s, updated_at = NOW() WHERE company_name = %s AND {COL_STORY_KEY} = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s AND is_active = TRUE",
                (story_status, company_name, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def update_company_story_priority(
    company_name: str, *, story_key: str, priority: str,
    provider_name: str = DEFAULT_PROVIDER, prompt_style: str = "simple", output_language: str = "zh-CN",
) -> bool:
    _ensure_news_schema()
    company_name = _normalize_company_name(company_name)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {TBL_COMPANY_STORY_STATE} SET priority = %s, updated_at = NOW() WHERE company_name = %s AND {COL_STORY_KEY} = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s AND is_active = TRUE",
                (priority, company_name, story_key, provider_name, prompt_style, output_language),
            )
            changed = cur.rowcount > 0
        conn.commit()
    return changed


def create_company_story_from_news(
    company_name: str, *, target_date: date, story_title: str, news_item: Dict[str, Any],
    provider_name: str = DEFAULT_PROVIDER, model: str = DEFAULT_MODEL, prompt_style: str = "simple", output_language: str = "zh-CN",
) -> Optional[Dict[str, Any]]:
    company_name = _normalize_company_name(company_name)
    title = str(story_title or news_item.get("news_title") or "").strip()
    if not company_name or not title:
        return None
    existing = list_company_story_states(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    story_key = _normalize_story_key("", fallback_title=title, fallback_index=len(existing))
    story = _normalize_story_record({"story_key": story_key, "story_title": title, "story_summary": str(news_item.get("summary") or news_item.get("news_title") or "").strip(), "importance_rank": len(existing) + 1, "story_status": "ongoing", "priority": "normal", "timeline_items": [{"date": target_date.isoformat(), "label": str(news_item.get("news_title") or title).strip(), "summary": str(news_item.get("summary") or "").strip()}], "future_and_impact": [], "evidence": [{"news_title": str(news_item.get("news_title") or title).strip(), "news_date_time": str(news_item.get("news_date_time") or target_date.isoformat()), "news_source_link": str(news_item.get("news_source_link") or "").strip(), "summary": str(news_item.get("summary") or "").strip()}], "change_log": ["Created manually from company news."]})
    if not story:
        return None
    _persist_story_refresh(company_name=company_name, as_of_date=target_date, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"manual_action": "create_story_from_news", "news_item": news_item}, raw_output=json.dumps({"story": story}, ensure_ascii=False), stories=sorted(existing + [story], key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or ""))))
    return story


def attach_news_to_company_story(
    company_name: str, *, target_date: date, story_key: str, news_item: Dict[str, Any],
    provider_name: str = DEFAULT_PROVIDER, model: str = DEFAULT_MODEL, prompt_style: str = "simple", output_language: str = "zh-CN",
) -> bool:
    company_name = _normalize_company_name(company_name)
    stories = list_company_story_states(company_name, provider_name=provider_name, prompt_style=prompt_style, output_language=output_language)
    updated: List[Dict[str, Any]] = []
    matched = False
    for story in stories:
        if str(story.get("story_key") or "").strip() != str(story_key or "").strip():
            updated.append(story)
            continue
        matched = True
        next_story = dict(story)
        timeline_items = list(next_story.get("timeline_items") or [])
        timeline_items.append({"date": target_date.isoformat(), "label": str(news_item.get("news_title") or "").strip() or next_story.get("story_title"), "summary": str(news_item.get("summary") or "").strip()})
        evidence = list(next_story.get("evidence") or [])
        evidence.append({"news_title": str(news_item.get("news_title") or "").strip(), "news_date_time": str(news_item.get("news_date_time") or target_date.isoformat()), "news_source_link": str(news_item.get("news_source_link") or "").strip(), "summary": str(news_item.get("summary") or "").strip()})
        change_log = list(next_story.get("change_log") or [])
        change_log.append("Attached manually from company news.")
        next_story["timeline_items"] = timeline_items
        next_story["evidence"] = evidence
        next_story["change_log"] = change_log
        next_story["story_status"] = "ongoing"
        updated.append(next_story)
    if not matched:
        return False
    _persist_story_refresh(company_name=company_name, as_of_date=target_date, provider_name=provider_name, model=model, prompt_style=prompt_style, output_language=output_language, input_payload={"manual_action": "attach_news_to_story", "story_key": story_key, "news_item": news_item}, raw_output=json.dumps({"story_key": story_key, "news_item": news_item}, ensure_ascii=False), stories=updated)
    return True


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _persist_story_refresh(*, company_name: str, as_of_date: date, provider_name: str, model: str, prompt_style: str, output_language: str, input_payload: Dict[str, Any], raw_output: str, stories: List[Dict[str, Any]]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            active_keys: List[str] = []
            for item in stories:
                story_key = str(item["story_key"]).strip()
                active_keys.append(story_key)
                cur.execute(
                    f"""
                    INSERT INTO {TBL_COMPANY_STORY_STATE} (
                        company_name, {COL_STORY_KEY}, story_title, story_summary, importance_rank,
                        story_status, priority, confidence, happened_text, happening_text, next_text,
                        timeline_json, future_impact_json, open_questions_json, evidence_json, change_log_json,
                        last_event_at, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, is_active, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW(), %s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (company_name, {COL_STORY_KEY}, provider, prompt_style, {COL_OUTPUT_LANGUAGE})
                    DO UPDATE SET
                        story_title = EXCLUDED.story_title, story_summary = EXCLUDED.story_summary,
                        importance_rank = EXCLUDED.importance_rank, story_status = EXCLUDED.story_status,
                        priority = EXCLUDED.priority, confidence = EXCLUDED.confidence,
                        happened_text = EXCLUDED.happened_text, happening_text = EXCLUDED.happening_text,
                        next_text = EXCLUDED.next_text, timeline_json = EXCLUDED.timeline_json,
                        future_impact_json = EXCLUDED.future_impact_json, open_questions_json = EXCLUDED.open_questions_json,
                        evidence_json = EXCLUDED.evidence_json, change_log_json = EXCLUDED.change_log_json,
                        last_event_at = NOW(), model = EXCLUDED.model, is_active = TRUE, updated_at = NOW()
                    """,
                    (company_name, story_key, item["story_title"], item.get("story_summary") or "", int(item["importance_rank"]), item["story_status"], item.get("priority") or "normal", float(item["confidence"]), item["happened_text"], item["happening_text"], item["next_text"], json.dumps(item.get("timeline_items") or [], ensure_ascii=False), json.dumps(item.get("future_and_impact") or [], ensure_ascii=False), json.dumps(item.get("open_questions") or [], ensure_ascii=False), json.dumps(item.get("evidence") or [], ensure_ascii=False), json.dumps(item.get("change_log") or [], ensure_ascii=False), provider_name, model, prompt_style, output_language),
                )
                cur.execute(
                    f"INSERT INTO {TBL_COMPANY_STORY_UPDATE} (company_name, {COL_STORY_KEY}, as_of_date, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, output_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (company_name, story_key, as_of_date, provider_name, model, prompt_style, output_language, json.dumps(input_payload, ensure_ascii=False), json.dumps(item, ensure_ascii=False)),
                )
            if active_keys:
                cur.execute(f"UPDATE {TBL_COMPANY_STORY_STATE} SET is_active = FALSE, updated_at = NOW() WHERE company_name = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s AND {COL_STORY_KEY} <> ALL(%s)", (company_name, provider_name, prompt_style, output_language, active_keys))
            else:
                cur.execute(f"UPDATE {TBL_COMPANY_STORY_STATE} SET is_active = FALSE, updated_at = NOW() WHERE company_name = %s AND provider = %s AND prompt_style = %s AND {COL_OUTPUT_LANGUAGE} = %s", (company_name, provider_name, prompt_style, output_language))
            cur.execute(f"INSERT INTO {TBL_COMPANY_STORY_UPDATE} (company_name, {COL_STORY_KEY}, as_of_date, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, output_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (company_name, "__refresh__", as_of_date, provider_name, model, prompt_style, output_language, json.dumps(input_payload, ensure_ascii=False), raw_output))
        conn.commit()


def _insert_story_qa(*, company_name: str, story_key: str, question: str, answer: str, provider_name: str, model: str, prompt_style: str, output_language: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {TBL_COMPANY_STORY_QA} (company_name, {COL_STORY_KEY}, question, answer, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, company_name, {COL_STORY_KEY}, question, answer, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, created_at",
                (company_name, story_key, question, answer, provider_name, model, prompt_style, output_language, json.dumps(input_payload, ensure_ascii=False)),
            )
            row = cur.fetchone()
        conn.commit()
    return {"id": int(row["id"]), "company_name": row["company_name"], "story_key": row[COL_STORY_KEY], "question": row["question"] or "", "answer": row["answer"] or "", "provider": row["provider"], "model": row["model"], "prompt_style": row["prompt_style"], "output_language": row[COL_OUTPUT_LANGUAGE], "input_payload": row["input_payload"] or "", "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S")}


def _get_company_story_qa_row(company_name: str, *, story_key: str, qa_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, company_name, {COL_STORY_KEY}, question, answer, provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, created_at FROM {TBL_COMPANY_STORY_QA} WHERE company_name = %s AND {COL_STORY_KEY} = %s AND id = %s LIMIT 1", (company_name, story_key, qa_id))
            row = cur.fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "company_name": row["company_name"], "story_key": row[COL_STORY_KEY], "question": row["question"] or "", "answer": row["answer"] or "", "provider": row["provider"], "model": row["model"], "prompt_style": row["prompt_style"], "output_language": row[COL_OUTPUT_LANGUAGE], "input_payload": row["input_payload"] or "", "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S")}


def _normalize_story_routing_result(*, existing_stories: List[Dict[str, Any]], clusters: List[Dict[str, Any]], payload: Dict[str, Any]) -> Dict[str, Any]:
    existing_by_key = {str(item.get("story_key") or "").strip(): item for item in existing_stories if str(item.get("story_key") or "").strip()}
    clusters_by_key = {str(item.get("cluster_key") or "").strip(): item for item in clusters if str(item.get("cluster_key") or "").strip()}
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
    assigned_keys: set[str] = set()
    existing_groups: Dict[str, List[Dict[str, Any]]] = {}
    new_groups: Dict[str, Dict[str, Any]] = {}
    ignored_items: List[Dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        try:
            cluster_key = str(item.get("cluster_key") or "").strip()
        except (TypeError, ValueError):
            continue
        if not cluster_key or cluster_key in assigned_keys or cluster_key not in clusters_by_key:
            continue
        assigned_keys.add(cluster_key)
        action = str(item.get("action") or "").strip().lower()
        cluster = clusters_by_key[cluster_key]
        if action == "existing_story":
            sk = str(item.get("story_key") or "").strip()
            if sk and sk in existing_by_key:
                existing_groups.setdefault(sk, []).append(cluster)
                continue
        if action == "new_story":
            new_title = _as_text(item.get("new_story_title")) or cluster.get("cluster_title") or f"Story {cluster_key}"
            new_key = _normalize_story_key("", fallback_title=new_title, fallback_index=len(new_groups))
            bucket = new_groups.setdefault(new_key, {"story_key": new_key, "story_title": new_title, "clusters": []})
            bucket["clusters"].append(cluster)
            continue
        ignored_items.append({"cluster_key": cluster_key, "reason": _as_text(item.get("reason")) or "ignore", "cluster_title": cluster.get("cluster_title") or ""})
    for cluster_key, cluster in clusters_by_key.items():
        if cluster_key in assigned_keys:
            continue
        new_title = cluster.get("cluster_title") or f"Story {cluster_key}"
        new_key = _normalize_story_key("", fallback_title=new_title, fallback_index=len(new_groups))
        bucket = new_groups.setdefault(new_key, {"story_key": new_key, "story_title": new_title, "clusters": []})
        bucket["clusters"].append(cluster)
    return {"existing_groups": existing_groups, "new_groups": list(new_groups.values()), "ignored_items": ignored_items}


def _normalize_incremental_story_item(payload: Dict[str, Any], *, fallback_story_key: str, fallback_story_title: str, fallback_rank: int) -> Optional[Dict[str, Any]]:
    story = payload.get("story")
    if not isinstance(story, dict):
        return None
    return _normalize_story_record({**story, "story_key": story.get("story_key") or fallback_story_key, "story_title": story.get("story_title") or fallback_story_title, "importance_rank": story.get("importance_rank") or fallback_rank, "confidence": story.get("confidence", 0.5), "priority": story.get("priority") or "normal"})


def _apply_incremental_story_updates(*, company_name: str, as_of_date: date, provider, existing_stories: List[Dict[str, Any]], routed: Dict[str, Any], prompt_style: str, output_language: str) -> Dict[str, Any]:
    del prompt_style
    existing_by_key = {str(item.get("story_key") or "").strip(): item for item in existing_stories if str(item.get("story_key") or "").strip()}
    final_stories: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    updated_story_keys: List[str] = []
    new_story_keys: List[str] = []
    for story_key, story in existing_by_key.items():
        clusters = routed["existing_groups"].get(story_key) or []
        if not clusters:
            final_stories.append(story)
            continue
        prompt = _build_incremental_existing_story_prompt(company_name, as_of_date=as_of_date, output_language=output_language, story=story, clusters=clusters)
        with usage_context("company_stories", company_name=company_name, module="company"):
            raw_output = provider.generate_text(prompt=prompt)
        payload = _parse_json_object(raw_output) or {}
        normalized = _normalize_incremental_story_item(payload, fallback_story_key=story_key, fallback_story_title=str(story.get("story_title") or story_key), fallback_rank=int(story.get("importance_rank") or 999)) or story
        final_stories.append(normalized)
        updated_story_keys.append(story_key)
        raw_outputs.append({"type": "existing_story", "story_key": story_key, "prompt": prompt, "raw_output": raw_output, "cluster_keys": [str(item.get("cluster_key") or "").strip() for item in clusters]})
    for index, bucket in enumerate(routed["new_groups"]):
        story_key = str(bucket.get("story_key") or "").strip()
        story_title = str(bucket.get("story_title") or "").strip() or f"Story {index + 1}"
        clusters = bucket.get("clusters") if isinstance(bucket.get("clusters"), list) else []
        if not clusters:
            continue
        prompt = _build_incremental_new_story_prompt(company_name, as_of_date=as_of_date, output_language=output_language, story_key=story_key, story_title=story_title, clusters=clusters)
        with usage_context("company_stories", company_name=company_name, module="company"):
            raw_output = provider.generate_text(prompt=prompt)
        payload = _parse_json_object(raw_output) or {}
        normalized = _normalize_incremental_story_item(payload, fallback_story_key=story_key, fallback_story_title=story_title, fallback_rank=len(final_stories) + 1)
        if not normalized:
            continue
        final_stories.append(normalized)
        new_story_keys.append(normalized["story_key"])
        raw_outputs.append({"type": "new_story", "story_key": normalized["story_key"], "prompt": prompt, "raw_output": raw_output, "cluster_keys": [str(item.get("cluster_key") or "").strip() for item in clusters]})
    final_stories = sorted([_normalize_story_record(item) for item in final_stories if isinstance(item, dict)], key=lambda item: (int(item.get("importance_rank") or 999), str(item.get("story_title") or "")))
    return {"stories": final_stories, "raw_outputs": raw_outputs, "updated_story_keys": updated_story_keys, "new_story_keys": new_story_keys}
