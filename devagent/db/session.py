"""PostgreSQL connection helpers shared across the package."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from devagent.config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    """Lazily-opened connection pool for short-lived queries."""
    settings = get_settings()
    pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=8,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    return pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool for the duration of the block."""
    with get_pool().connection() as conn:
        yield conn


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def execute(sql: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
