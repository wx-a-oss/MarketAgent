"""User note functions."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from market_agent.db.bootstrap import get_connection
from market_agent.services.company._helpers import (
    _ensure_news_schema,
    _normalize_note_tag,
    _normalize_note_tags,
    _replace_user_note_tags,
)

logger = logging.getLogger("uvicorn.error")


def create_user_note(
    *,
    title: str,
    body_markdown: str,
    tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    _ensure_news_schema()
    clean_title = str(title or "").strip()
    clean_body = str(body_markdown or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    if not clean_body:
        raise ValueError("body is required")
    tag_rows = _normalize_note_tags(tags)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_note (
                    title,
                    body_markdown,
                    validity_state,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, 'valid', NOW(), NOW())
                RETURNING id
                """,
                (clean_title, clean_body),
            )
            row = cur.fetchone()
            note_id = int(row["id"])
            _replace_user_note_tags(cur, note_id=note_id, tag_rows=tag_rows)
        conn.commit()
    note = get_user_note(note_id)
    if not note:
        raise ValueError("failed to create note")
    return note


def update_user_note(
    note_id: int,
    *,
    title: str,
    body_markdown: str,
    tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    _ensure_news_schema()
    clean_title = str(title or "").strip()
    clean_body = str(body_markdown or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    if not clean_body:
        raise ValueError("body is required")
    tag_rows = _normalize_note_tags(tags)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_note
                SET title = %s,
                    body_markdown = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (clean_title, clean_body, int(note_id)),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("note not found")
            _replace_user_note_tags(cur, note_id=int(note_id), tag_rows=tag_rows)
        conn.commit()
    note = get_user_note(int(note_id))
    if not note:
        raise KeyError("note not found")
    return note


def invalidate_user_note(note_id: int, *, reason: Optional[str] = None) -> Dict[str, Any]:
    _ensure_news_schema()
    note = get_user_note(int(note_id))
    if not note:
        raise KeyError("note not found")
    if str(note.get("validity_state") or "valid") == "invalid":
        return note
    clean_reason = str(reason or "").strip() or None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_note
                SET validity_state = 'invalid',
                    invalidation_reason = %s,
                    invalidated_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (clean_reason, int(note_id)),
            )
        conn.commit()
    updated = get_user_note(int(note_id))
    if not updated:
        raise KeyError("note not found")
    return updated


def get_user_note(note_id: int) -> Optional[Dict[str, Any]]:
    notes = list_user_notes(note_id=int(note_id))
    return notes[0] if notes else None


def list_user_notes(*, tag: Optional[str] = None, note_id: Optional[int] = None) -> List[Dict[str, Any]]:
    _ensure_news_schema()
    params: List[Any] = []
    where = []
    join = ""
    if note_id is not None:
        where.append("n.id = %s")
        params.append(int(note_id))
    normalized_tag = _normalize_note_tag(tag)
    if normalized_tag:
        join = "JOIN user_note_tag t_filter ON t_filter.note_id = n.id"
        where.append("t_filter.normalized_tag = %s")
        params.append(normalized_tag)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    n.id,
                    n.title,
                    n.body_markdown,
                    n.validity_state,
                    n.invalidation_reason,
                    n.invalidated_at,
                    n.created_at,
                    n.updated_at
                FROM user_note AS n
                {join}
                {where_sql}
                ORDER BY n.created_at DESC, n.id DESC
                """
                ,
                tuple(params),
            )
            note_rows = cur.fetchall()
            if not note_rows:
                return []
            note_ids = [int(row["id"]) for row in note_rows]
            cur.execute(
                """
                SELECT note_id, tag_text, normalized_tag
                FROM user_note_tag
                WHERE note_id = ANY(%s)
                ORDER BY normalized_tag ASC, id ASC
                """,
                (note_ids,),
            )
            tag_rows = cur.fetchall()
    tags_by_note: Dict[int, List[Dict[str, str]]] = {}
    for row in tag_rows:
        bucket = tags_by_note.setdefault(int(row["note_id"]), [])
        bucket.append(
            {
                "tag": str(row["tag_text"] or "").strip(),
                "normalized_tag": str(row["normalized_tag"] or "").strip(),
            }
        )
    result: List[Dict[str, Any]] = []
    for row in note_rows:
        note_tags = tags_by_note.get(int(row["id"]), [])
        result.append(
            {
                "id": int(row["id"]),
                "title": str(row["title"] or ""),
                "body_markdown": str(row["body_markdown"] or ""),
                "validity_state": str(row["validity_state"] or "valid"),
                "invalidation_reason": str(row["invalidation_reason"] or ""),
                "invalidated_at": row["invalidated_at"].isoformat() if row.get("invalidated_at") else "",
                "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
                "tags": [item["tag"] for item in note_tags],
                "normalized_tags": [item["normalized_tag"] for item in note_tags],
            }
        )
    return result


def list_user_note_tags() -> List[Dict[str, Any]]:
    _ensure_news_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    normalized_tag,
                    MIN(tag_text) AS display_tag,
                    COUNT(DISTINCT note_id) AS note_count
                FROM user_note_tag
                GROUP BY normalized_tag
                ORDER BY COUNT(DISTINCT note_id) DESC, MIN(tag_text) ASC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "tag": str(row["display_tag"] or ""),
            "normalized_tag": str(row["normalized_tag"] or ""),
            "note_count": int(row["note_count"] or 0),
        }
        for row in rows
    ]
