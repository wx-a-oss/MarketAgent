"""Central database bootstrap that applies runtime migrations."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable

from psycopg2.extras import DictCursor
import psycopg2

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAPPED_DSN: set[str] = set()


def _build_dsn() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", "market_agent")
    password = os.getenv("PGPASSWORD", "market_agent_password")
    database = os.getenv("PGDATABASE", "market_agent")
    return (
        f"host={host} port={port} user={user} password={password} dbname={database}"
    )


def get_connection():
    return psycopg2.connect(_build_dsn(), cursor_factory=DictCursor)


def _migration_files() -> Iterable[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "postgres" / "migrations"
    if migrations_dir.is_dir():
        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name.startswith("._"):
                continue
            yield path


def _include_base_schema() -> bool:
    return str(os.getenv("BOOTSTRAP_BASE_SCHEMA", "0")).strip() == "1"


def _schema_files() -> Iterable[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    postgres_dir = repo_root / "postgres"
    if _include_base_schema():
        yield postgres_dir / "init.sql"
    yield from _migration_files()


def ensure_database_schema() -> None:
    dsn = _build_dsn()
    with _BOOTSTRAP_LOCK:
        if dsn in _BOOTSTRAPPED_DSN:
            return
        with get_connection() as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                for path in _schema_files():
                    sql_text = path.read_text(encoding="utf-8").strip()
                    if not sql_text:
                        continue
                    cur.execute(sql_text)
            conn.commit()
        _BOOTSTRAPPED_DSN.add(dsn)


__all__ = ["ensure_database_schema", "get_connection"]
