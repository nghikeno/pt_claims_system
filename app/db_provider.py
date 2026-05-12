from __future__ import annotations

import sqlite3
import importlib.util
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import DB_PATH, database_provider, database_url
from app.postgres_schema import POSTGRES_SCHEMA_SQL


_POSTGRES_POOL = None


def current_database_summary() -> dict[str, str]:
    provider = database_provider()
    summary = {"provider": provider}
    if provider == "postgresql":
        summary["detail"] = "PostgreSQL configured via DATABASE_URL"
    else:
        summary["detail"] = str(DB_PATH)
    return summary


def postgresql_configured() -> bool:
    return database_provider() == "postgresql" and bool(database_url())


def psycopg_available() -> bool:
    return importlib.util.find_spec("psycopg") is not None


def psycopg_pool_available() -> bool:
    return importlib.util.find_spec("psycopg_pool") is not None


def db_perf_debug_enabled() -> bool:
    return str(os.environ.get("DB_PERF_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def db_perf_span(label: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        if db_perf_debug_enabled():
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"DB_PERF {label}: {elapsed_ms:.1f} ms")


def require_postgresql_dependency() -> None:
    if database_provider() == "postgresql" and not psycopg_available():
        raise RuntimeError(
            "DATABASE_URL is configured for PostgreSQL, but the psycopg dependency is not installed. "
            "Install project requirements before enabling PostgreSQL mode."
        )


def postgresql_readiness_status() -> dict[str, object]:
    provider = database_provider()
    sqlite_specific_notes = [
        "app.database currently creates SQLite schema with INTEGER PRIMARY KEY AUTOINCREMENT.",
        "Several modules use SQLite metadata such as sqlite_master and PRAGMA table_info.",
        "Most service queries use sqlite3 parameter style and require PostgreSQL validation before production use.",
    ]
    return {
        "provider": provider,
        "postgresql_configured": postgresql_configured(),
        "psycopg_available": psycopg_available(),
        "psycopg_pool_available": psycopg_pool_available(),
        "status": "partial" if provider == "postgresql" else "sqlite-local-default",
        "notes": sqlite_specific_notes,
    }


def normalize_postgres_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def sql_placeholder() -> str:
    return "%s" if database_provider() == "postgresql" else "?"


def convert_placeholders(sql: str) -> str:
    if database_provider() == "postgresql":
        return sql.replace("?", "%s")
    return sql


def row_to_dict(row: Any) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def rows_to_dicts(rows: list[Any]) -> list[dict]:
    return [row_to_dict(row) or {} for row in rows]


def get_runtime_connection(db_path: str | Path = DB_PATH):
    if database_provider() == "postgresql":
        require_postgresql_dependency()
        pool = get_postgres_pool()
        if pool is not None:
            return pool.connection()
        return connect_postgres_direct()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_postgres_direct():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(normalize_postgres_url(database_url()), row_factory=dict_row)


def get_postgres_pool():
    global _POSTGRES_POOL
    if database_provider() != "postgresql" or not psycopg_pool_available():
        return None
    if str(os.environ.get("DB_POOL_DISABLE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return None
    if _POSTGRES_POOL is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        min_size = max(1, int(os.environ.get("DB_POOL_MIN_SIZE", "1")))
        max_size = max(min_size, int(os.environ.get("DB_POOL_MAX_SIZE", "4")))
        _POSTGRES_POOL = ConnectionPool(
            conninfo=normalize_postgres_url(database_url()),
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _POSTGRES_POOL


def close_postgres_pool() -> None:
    global _POSTGRES_POOL
    if _POSTGRES_POOL is not None:
        _POSTGRES_POOL.close()
        _POSTGRES_POOL = None


def init_runtime_db() -> None:
    if database_provider() == "postgresql":
        require_postgresql_dependency()
        with get_runtime_connection() as conn:
            with conn.cursor() as cur:
                for statement in [part.strip() for part in POSTGRES_SCHEMA_SQL.split(";") if part.strip()]:
                    cur.execute(statement)
            conn.commit()
        return
    from app.database import init_db

    init_db()
