from __future__ import annotations

import json
import os
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Optional

from market_agent.db.bootstrap import ensure_database_schema, get_connection

_STATUS_RUNNING = {"queued", "running"}
_ACTIVE_THREADS: dict[int, threading.Thread] = {}
_ACTIVE_LOCK = threading.Lock()
_INTERRUPTED_MARKED = False
_INTERRUPTED_LOCK = threading.Lock()
_APP_PID = os.getpid()


@dataclass
class JobRecord:
    job_id: int
    job_type: str
    job_key: str
    status: str
    current_stage: str
    metrics_json: Dict[str, Any]
    result_summary: str
    error_text: str
    created_at: str
    started_at: str
    completed_at: str
    updated_at: str
    elapsed_sec: float
    provider: str
    model: str
    output_language: str
    prompt_style: str
    target_entity: str
    target_date: str
    window_start: str
    window_end: str
    input_char_count: int
    input_item_count: int
    output_char_count: int
    final_counts: Dict[str, Any]
    stage_history: list[Dict[str, Any]]


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _iso(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


def mark_interrupted_jobs() -> None:
    global _INTERRUPTED_MARKED
    with _INTERRUPTED_LOCK:
        if _INTERRUPTED_MARKED:
            return
        ensure_database_schema()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE background_job
                    SET status = 'interrupted',
                        error_text = CASE WHEN COALESCE(error_text, '') = '' THEN 'Process restarted before job completed.' ELSE error_text END,
                        current_stage = CASE WHEN COALESCE(current_stage, '') = '' THEN 'interrupted' ELSE current_stage END,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE status IN ('queued', 'running')
                    """
                )
                cur.execute(
                    """
                    UPDATE background_job_stage
                    SET status = 'interrupted',
                        message = CASE WHEN COALESCE(message, '') = '' THEN 'Process restarted before stage completed.' ELSE message END,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE status IN ('queued', 'running')
                    """
                )
            conn.commit()
        _INTERRUPTED_MARKED = True


def _row_to_job(row: Any, stage_rows: list[Any]) -> JobRecord:
    metrics = _json_loads(row["metrics_json"], {})
    final_counts = _json_loads(row["final_counts_json"], {})
    stages: list[Dict[str, Any]] = []
    for item in stage_rows:
        stages.append(
            {
                "id": int(item["id"]),
                "stage_name": str(item["stage_name"] or ""),
                "status": str(item["status"] or ""),
                "message": str(item["message"] or ""),
                "metrics": _json_loads(item["metrics_json"], {}),
                "started_at": _iso(item["started_at"]),
                "completed_at": _iso(item["completed_at"]),
                "updated_at": _iso(item["updated_at"]),
                "elapsed_sec": float(item["elapsed_sec"] or 0.0),
            }
        )
    return JobRecord(
        job_id=int(row["id"]),
        job_type=str(row["job_type"] or ""),
        job_key=str(row["job_key"] or ""),
        status=str(row["status"] or ""),
        current_stage=str(row["current_stage"] or ""),
        metrics_json=metrics,
        result_summary=str(row["result_summary"] or ""),
        error_text=str(row["error_text"] or ""),
        created_at=_iso(row["created_at"]),
        started_at=_iso(row["started_at"]),
        completed_at=_iso(row["completed_at"]),
        updated_at=_iso(row["updated_at"]),
        elapsed_sec=float(row["elapsed_sec"] or 0.0),
        provider=str(row["provider"] or ""),
        model=str(row["model"] or ""),
        output_language=str(row["output_language"] or ""),
        prompt_style=str(row["prompt_style"] or ""),
        target_entity=str(row["target_entity"] or ""),
        target_date=_iso(row["target_date"]),
        window_start=_iso(row["window_start"]),
        window_end=_iso(row["window_end"]),
        input_char_count=int(row["input_char_count"] or 0),
        input_item_count=int(row["input_item_count"] or 0),
        output_char_count=int(row["output_char_count"] or 0),
        final_counts=final_counts,
        stage_history=stages,
    )


def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    mark_interrupted_jobs()
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM background_job WHERE id = %s", (int(job_id),))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "SELECT * FROM background_job_stage WHERE job_id = %s ORDER BY id ASC",
                (int(job_id),),
            )
            stages = cur.fetchall()
    return _row_to_job(row, stages).__dict__


def find_latest_job(*, job_key: str, include_finished: bool = True) -> Optional[Dict[str, Any]]:
    mark_interrupted_jobs()
    ensure_database_schema()
    where = "WHERE job_key = %s"
    params: list[Any] = [job_key]
    if not include_finished:
        where += " AND status IN ('queued', 'running')"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM background_job {where} ORDER BY created_at DESC, id DESC LIMIT 1",
                tuple(params),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("SELECT * FROM background_job_stage WHERE job_id = %s ORDER BY id ASC", (int(row["id"]),))
            stages = cur.fetchall()
    return _row_to_job(row, stages).__dict__


def _update_elapsed(cur: Any, job_id: int) -> None:
    cur.execute(
        """
        UPDATE background_job
        SET elapsed_sec = COALESCE(EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - started_at)), elapsed_sec, 0),
            updated_at = NOW()
        WHERE id = %s
        """,
        (job_id,),
    )


def create_job(*, job_type: str, job_key: str, provider: str = "", model: str = "", output_language: str = "", prompt_style: str = "", target_entity: str = "", target_date: Optional[date] = None, window_start: Optional[date] = None, window_end: Optional[date] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    mark_interrupted_jobs()
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM background_job WHERE job_key = %s AND status IN ('queued', 'running') ORDER BY created_at DESC, id DESC LIMIT 1",
                (job_key,),
            )
            existing = cur.fetchone()
            if existing:
                conn.rollback()
                job = get_job(int(existing["id"]))
                return {"mode": "already_running", "job": job}
            cur.execute(
                """
                INSERT INTO background_job (
                    job_type, job_key, status, current_stage, metrics_json,
                    provider, model, output_language, prompt_style,
                    target_entity, target_date, window_start, window_end,
                    owner_pid, created_at, updated_at
                )
                VALUES (%s, %s, 'queued', 'queued', %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (
                    job_type,
                    job_key,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    provider,
                    model,
                    output_language,
                    prompt_style,
                    target_entity,
                    target_date,
                    window_start,
                    window_end,
                    _APP_PID,
                ),
            )
            job_id = int(cur.fetchone()["id"])
        conn.commit()
    return {"mode": "started", "job": get_job(job_id)}


class JobTracker:
    def __init__(self, job_id: int):
        self.job_id = int(job_id)

    def mark_running(self, stage: str, *, metrics: Optional[Dict[str, Any]] = None) -> None:
        ensure_database_schema()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE background_job
                    SET status = 'running', current_stage = %s,
                        metrics_json = COALESCE(metrics_json, '{}'::jsonb) || %s::jsonb,
                        started_at = COALESCE(started_at, NOW()), updated_at = NOW(), owner_pid = %s
                    WHERE id = %s
                    """,
                    (stage, json.dumps(metrics or {}, ensure_ascii=False), _APP_PID, self.job_id),
                )
                cur.execute(
                    """
                    INSERT INTO background_job_stage (job_id, stage_name, status, metrics_json, started_at, updated_at)
                    VALUES (%s, %s, 'running', %s::jsonb, NOW(), NOW())
                    RETURNING id
                    """,
                    (self.job_id, stage, json.dumps(metrics or {}, ensure_ascii=False)),
                )
            conn.commit()

    def update(self, *, stage: Optional[str] = None, metrics: Optional[Dict[str, Any]] = None, counts: Optional[Dict[str, Any]] = None, result_summary: Optional[str] = None, input_char_count: Optional[int] = None, input_item_count: Optional[int] = None, output_char_count: Optional[int] = None, error_text: Optional[str] = None) -> None:
        ensure_database_schema()
        with get_connection() as conn:
            with conn.cursor() as cur:
                sets = ["updated_at = NOW()"]
                params: list[Any] = []
                if stage is not None:
                    sets.append("current_stage = %s")
                    params.append(stage)
                if metrics is not None:
                    sets.append("metrics_json = COALESCE(metrics_json, '{}'::jsonb) || %s::jsonb")
                    params.append(json.dumps(metrics, ensure_ascii=False))
                if counts is not None:
                    sets.append("final_counts_json = COALESCE(final_counts_json, '{}'::jsonb) || %s::jsonb")
                    params.append(json.dumps(counts, ensure_ascii=False))
                if result_summary is not None:
                    sets.append("result_summary = %s")
                    params.append(result_summary)
                if input_char_count is not None:
                    sets.append("input_char_count = %s")
                    params.append(int(input_char_count))
                if input_item_count is not None:
                    sets.append("input_item_count = %s")
                    params.append(int(input_item_count))
                if output_char_count is not None:
                    sets.append("output_char_count = %s")
                    params.append(int(output_char_count))
                if error_text is not None:
                    sets.append("error_text = %s")
                    params.append(error_text)
                params.append(self.job_id)
                cur.execute(f"UPDATE background_job SET {', '.join(sets)} WHERE id = %s", tuple(params))
                _update_elapsed(cur, self.job_id)
                cur.execute(
                    """
                    UPDATE background_job_stage
                    SET metrics_json = COALESCE(metrics_json, '{}'::jsonb) || %s::jsonb,
                        message = COALESCE(%s, message),
                        updated_at = NOW(),
                        elapsed_sec = COALESCE(EXTRACT(EPOCH FROM (NOW() - started_at)), elapsed_sec, 0)
                    WHERE id = (
                        SELECT id FROM background_job_stage
                        WHERE job_id = %s AND status IN ('queued', 'running')
                        ORDER BY id DESC LIMIT 1
                    )
                    """,
                    (json.dumps(metrics or {}, ensure_ascii=False), result_summary, self.job_id),
                )
            conn.commit()

    def finish(self, *, status: str, result_summary: str = "", metrics: Optional[Dict[str, Any]] = None, counts: Optional[Dict[str, Any]] = None, input_char_count: Optional[int] = None, input_item_count: Optional[int] = None, output_char_count: Optional[int] = None, error_text: str = "") -> None:
        ensure_database_schema()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE background_job
                    SET status = %s,
                        result_summary = %s,
                        metrics_json = COALESCE(metrics_json, '{}'::jsonb) || %s::jsonb,
                        final_counts_json = COALESCE(final_counts_json, '{}'::jsonb) || %s::jsonb,
                        error_text = %s,
                        completed_at = NOW(),
                        updated_at = NOW(),
                        input_char_count = COALESCE(%s, input_char_count),
                        input_item_count = COALESCE(%s, input_item_count),
                        output_char_count = COALESCE(%s, output_char_count)
                    WHERE id = %s
                    """,
                    (
                        status,
                        result_summary,
                        json.dumps(metrics or {}, ensure_ascii=False),
                        json.dumps(counts or {}, ensure_ascii=False),
                        error_text,
                        input_char_count,
                        input_item_count,
                        output_char_count,
                        self.job_id,
                    ),
                )
                _update_elapsed(cur, self.job_id)
                cur.execute(
                    """
                    UPDATE background_job_stage
                    SET status = %s,
                        message = CASE WHEN %s <> '' THEN %s ELSE message END,
                        metrics_json = COALESCE(metrics_json, '{}'::jsonb) || %s::jsonb,
                        completed_at = NOW(),
                        updated_at = NOW(),
                        elapsed_sec = COALESCE(EXTRACT(EPOCH FROM (NOW() - started_at)), elapsed_sec, 0)
                    WHERE id = (
                        SELECT id FROM background_job_stage
                        WHERE job_id = %s AND status IN ('queued', 'running')
                        ORDER BY id DESC LIMIT 1
                    )
                    """,
                    (status, result_summary or error_text, result_summary or error_text, json.dumps(metrics or {}, ensure_ascii=False), self.job_id),
                )
            conn.commit()

    @contextmanager
    def stage(self, stage_name: str, *, metrics: Optional[Dict[str, Any]] = None):
        self.mark_running(stage_name, metrics=metrics)
        try:
            yield self
        except Exception:
            self.finish(status="failed", error_text=traceback.format_exc())
            raise


def run_job_async(job_id: int, fn: Callable[[JobTracker], Dict[str, Any]]) -> None:
    tracker = JobTracker(job_id)

    def _target() -> None:
        try:
            tracker.mark_running("starting")
            result = fn(tracker) or {}
            tracker.finish(
                status="completed",
                result_summary=str(result.get("result_summary") or result.get("summary") or "Completed."),
                metrics=result.get("metrics") or {},
                counts=result.get("counts") or {},
                input_char_count=result.get("input_char_count"),
                input_item_count=result.get("input_item_count"),
                output_char_count=result.get("output_char_count"),
            )
        except Exception:
            tracker.finish(status="failed", error_text=traceback.format_exc())
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_THREADS.pop(job_id, None)

    thread = threading.Thread(target=_target, daemon=True, name=f"background-job-{job_id}")
    with _ACTIVE_LOCK:
        _ACTIVE_THREADS[job_id] = thread
    thread.start()


__all__ = [
    "JobTracker",
    "create_job",
    "find_latest_job",
    "get_job",
    "mark_interrupted_jobs",
    "run_job_async",
]
