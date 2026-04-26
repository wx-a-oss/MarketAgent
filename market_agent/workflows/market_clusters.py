"""Daily clustering of market news."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List

from market_agent.db.bootstrap import ensure_database_schema, get_connection
from market_agent.services.company._helpers import (
    _build_output_language_line,
    _parse_json_object,
)
from market_agent.llms.news_registry import get_news_provider
from market_agent.schema_fields import (
    COL_OUTPUT_LANGUAGE,
    TBL_MARKET_NEWS_DAILY_CLUSTER,
)

from market_agent.workflows.market_news import (
    DEFAULT_MARKET_PROVIDER,
    DEFAULT_MARKET_MODEL,
    list_market_raw_news,
)
from market_agent.workflows.market_stories import (
    _normalize_market_story_key,
)

logger = logging.getLogger("uvicorn.error")


def list_market_daily_clusters(
    *,
    target_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> List[Dict[str, Any]]:
    ensure_database_schema()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {TBL_MARKET_NEWS_DAILY_CLUSTER}
                WHERE cluster_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY updated_at DESC, id DESC
                """,
                (target_date, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [
        {
            "id": int(row["id"]),
            "cluster_date": row["cluster_date"].isoformat(),
            "cluster_key": row["cluster_key"],
            "cluster_title": row["cluster_title"],
            "cluster_summary": row["cluster_summary"] or "",
            "source_news": row["source_news_json"] or [],
            "provider": row["provider"],
            "model": row["model"],
            "prompt_style": row["prompt_style"],
            "output_language": row[COL_OUTPUT_LANGUAGE],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


def refresh_market_daily_clusters(
    *,
    target_date: date,
    provider_name: str = DEFAULT_MARKET_PROVIDER,
    model: str = DEFAULT_MARKET_MODEL,
    prompt_style: str = "simple",
    output_language: str = "zh-CN",
) -> Dict[str, Any]:
    items = list_market_raw_news(target_date=target_date, limit=250)
    if not items:
        return {"generated": False, "cluster_count": 0, "target_date": target_date.isoformat(), "input_item_count": 0, "prompt_char_count": 0, "output_char_count": 0}
    provider = get_news_provider(provider_name, model=model, temperature=0.2, timeout_sec=180)
    prompt = _build_market_daily_cluster_prompt(
        target_date=target_date,
        items=items,
        output_language=output_language,
    )
    payload = _parse_json_object(provider.generate_text(prompt=prompt)) or {}
    clusters = _normalize_market_cluster_rows(target_date=target_date, payload=payload)
    _replace_market_daily_clusters(
        target_date=target_date,
        clusters=clusters,
        provider_name=provider_name,
        model=model,
        prompt_style=prompt_style,
        output_language=output_language,
        input_payload={"items": items, "prompt": prompt},
    )
    return {
        "generated": True,
        "cluster_count": len(clusters),
        "target_date": target_date.isoformat(),
        "input_item_count": len(items),
        "prompt_char_count": len(prompt),
        "output_char_count": len(json.dumps(payload, ensure_ascii=False)),
    }


def _build_market_daily_cluster_prompt(
    *,
    target_date: date,
    items: List[Dict[str, Any]],
    output_language: str,
) -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    language_line = _build_output_language_line(output_language)
    return (
        f"Cluster the market news for {target_date.isoformat()} into a small set of distinct daily market narratives.\n"
        "Goal:\n"
        "- Group duplicate or overlapping news into one cluster.\n"
        "- Produce 3 to 10 meaningful clusters for the day if possible.\n"
        "- Each cluster should have a short title and a compact summary.\n"
        "- Return JSON only.\n"
        f"{language_line}"
        "Output JSON schema:\n"
        "{\n"
        '  "clusters": [\n'
        "    {\n"
        '      "cluster_key": "short-stable-key",\n'
        '      "cluster_title": "short title",\n'
        '      "cluster_summary": "one compact summary paragraph",\n'
        '      "source_news": [{"headline": "...", "url": "...", "datetime_text": "..."}]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"News items JSON:\n{items_json}\n"
    )


def _normalize_market_cluster_rows(*, target_date: date, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = payload.get("clusters")
    if not isinstance(rows, list):
        rows = []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        title = str(item.get("cluster_title") or "").strip()
        summary = str(item.get("cluster_summary") or "").strip()
        if not title:
            continue
        cluster_key = _normalize_market_story_key(item.get("cluster_key"), fallback_title=title, fallback_index=index)
        if cluster_key in seen:
            continue
        seen.add(cluster_key)
        source_news = item.get("source_news") if isinstance(item.get("source_news"), list) else []
        normalized.append(
            {
                "cluster_date": target_date,
                "cluster_key": cluster_key,
                "cluster_title": title,
                "cluster_summary": summary or title,
                "source_news": source_news,
            }
        )
    return normalized


def _replace_market_daily_clusters(
    *,
    target_date: date,
    clusters: List[Dict[str, Any]],
    provider_name: str,
    model: str,
    prompt_style: str,
    output_language: str,
    input_payload: Dict[str, Any],
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TBL_MARKET_NEWS_DAILY_CLUSTER}
                WHERE cluster_date = %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                """,
                (target_date, provider_name, prompt_style, output_language),
            )
            for item in clusters:
                cur.execute(
                    f"""
                    INSERT INTO {TBL_MARKET_NEWS_DAILY_CLUSTER}
                        (cluster_date, cluster_key, cluster_title, cluster_summary, source_news_json,
                         provider, model, prompt_style, {COL_OUTPUT_LANGUAGE}, input_payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                    """,
                    (
                        item["cluster_date"],
                        item["cluster_key"],
                        item["cluster_title"],
                        item["cluster_summary"],
                        json.dumps(item.get("source_news") or [], ensure_ascii=False),
                        provider_name,
                        model,
                        prompt_style,
                        output_language,
                        json.dumps(input_payload, ensure_ascii=False),
                    ),
                )
        conn.commit()


def _build_market_story_cluster_input_items(
    *,
    start_date: date,
    end_date: date,
    provider_name: str,
    prompt_style: str,
    output_language: str,
) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cluster_date, cluster_key, cluster_title, cluster_summary, source_news_json
                FROM {TBL_MARKET_NEWS_DAILY_CLUSTER}
                WHERE cluster_date >= %s
                  AND cluster_date <= %s
                  AND provider = %s
                  AND prompt_style = %s
                  AND {COL_OUTPUT_LANGUAGE} = %s
                ORDER BY cluster_date ASC, updated_at ASC, id ASC
                """,
                (start_date, end_date, provider_name, prompt_style, output_language),
            )
            rows = cur.fetchall()
    return [
        {
            "cluster_date": row["cluster_date"].isoformat(),
            "cluster_key": row["cluster_key"],
            "cluster_title": row["cluster_title"],
            "cluster_summary": row["cluster_summary"] or "",
            "source_news": row["source_news_json"] or [],
        }
        for row in rows
    ]
