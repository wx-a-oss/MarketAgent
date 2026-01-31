"""Postgres connection helpers for the news system."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import DictCursor


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


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(_build_dsn(), cursor_factory=DictCursor)
    try:
        yield conn
    finally:
        conn.close()
