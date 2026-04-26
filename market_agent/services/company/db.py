"""Backward-compatible database helpers for the company news system."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2

from market_agent.db.bootstrap import ensure_database_schema, get_connection as _get_connection


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    conn = _get_connection()
    try:
        yield conn
    finally:
        conn.close()


__all__ = ["ensure_database_schema", "get_connection"]
