from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.anonymise_staging_data import DEFAULT_OUTPUT, table_counts, validate_anonymised_db
from app.config import REAL_DB_PATH
from app.postgres_schema import POSTGRES_SCHEMA_SQL, REVERSE_TABLE_ORDER, TABLE_ORDER


DEFAULT_TARGET_ENV = "PT_CLAIMS_TEST_DATABASE_URL"
SAFETY_WARNING = "This migration is for anonymised staging data only."


def is_real_database_source(path: Path) -> bool:
    try:
        return Path(path).resolve() == REAL_DB_PATH.resolve()
    except FileNotFoundError:
        return False


def ensure_safe_source(path: Path) -> None:
    source = Path(path)
    if is_real_database_source(source):
        raise ValueError("Refusing to migrate real data/pt_claims.db. Use the anonymised staging database only.")
    if "staging" not in [part.lower() for part in source.resolve().parts]:
        raise ValueError("Source must be an anonymised staging database under data/staging/.")


def target_url_from_env(target_env: str = DEFAULT_TARGET_ENV) -> str:
    url = os.environ.get(target_env, "").strip()
    if not url:
        raise RuntimeError(
            f"{target_env} is not configured. Set it to a disposable PostgreSQL URL before migration."
        )
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError(f"{target_env} must start with postgresql:// or postgresql+psycopg://")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
    return row is not None


def dry_run(source: Path = DEFAULT_OUTPUT, target_env: str = DEFAULT_TARGET_ENV) -> dict[str, Any]:
    source = Path(source)
    ensure_safe_source(source)
    if not source.exists():
        raise FileNotFoundError(f"Anonymised staging database not found: {source}")
    validation = validate_anonymised_db(source)
    url_configured = bool(os.environ.get(target_env, "").strip())
    return {
        "warning": SAFETY_WARNING,
        "source": str(source),
        "target_env": target_env,
        "target_configured": url_configured,
        "counts": table_counts(source),
        "source_validation": validation,
        "writes_postgres": False,
    }


def _connect_postgres(url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for PostgreSQL staging migration.") from exc
    return psycopg.connect(url)


def _execute_postgres_schema(pg_conn) -> None:
    with pg_conn.cursor() as cur:
        for table in REVERSE_TABLE_ORDER:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        cur.execute(POSTGRES_SCHEMA_SQL)


def _load_table(sqlite_conn: sqlite3.Connection, pg_conn, table_name: str) -> int:
    if not sqlite_table_exists(sqlite_conn, table_name):
        return 0
    columns = sqlite_table_columns(sqlite_conn, table_name)
    if not columns:
        return 0
    rows = sqlite_conn.execute(f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id").fetchall()
    if not rows:
        return 0
    placeholders = ", ".join(["%s"] * len(columns))
    columns_sql = ", ".join(columns)
    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})",
                tuple(row[column] for column in columns),
            )
    return len(rows)


def _reset_identity(pg_conn, table_name: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_serial_sequence(%s, 'id')
            """,
            (table_name,),
        )
        sequence_row = cur.fetchone()
        sequence_name = sequence_row[0] if sequence_row else None
        if sequence_name:
            cur.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table_name}), 1), true)", (sequence_name,))


def migrate(source: Path = DEFAULT_OUTPUT, target_env: str = DEFAULT_TARGET_ENV, *, confirm_disposable: bool = False, yes: bool = False) -> dict[str, Any]:
    source = Path(source)
    ensure_safe_source(source)
    if not confirm_disposable:
        raise PermissionError("--confirm-disposable is required for PostgreSQL migration.")
    if not yes:
        raise PermissionError("--yes is required for PostgreSQL migration.")
    validation = validate_anonymised_db(source)
    if not validation["valid"]:
        raise ValueError(f"Source anonymised staging validation failed: {validation['failures']}")
    target_url = target_url_from_env(target_env)
    inserted: dict[str, int] = {}
    with sqlite3.connect(source) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        with _connect_postgres(target_url) as pg_conn:
            _execute_postgres_schema(pg_conn)
            for table in TABLE_ORDER:
                inserted[table] = _load_table(sqlite_conn, pg_conn, table)
            for table in TABLE_ORDER:
                _reset_identity(pg_conn, table)
            pg_conn.commit()
    return {"warning": SAFETY_WARNING, "source": str(source), "target_env": target_env, "inserted": inserted}


def print_dry_run(result: dict[str, Any]) -> None:
    print(result["warning"])
    print(f"Source DB: {result['source']}")
    print(f"Target env: {result['target_env']}")
    print(f"Target configured: {result['target_configured']}")
    print(f"Counts: {result['counts']}")
    print(f"Source validation: {result['source_validation']['valid']}")
    print("Dry-run only. No PostgreSQL writes were performed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate anonymised staging SQLite data to disposable PostgreSQL.")
    parser.add_argument("--source", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--target-env", default=DEFAULT_TARGET_ENV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-disposable", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print_dry_run(dry_run(Path(args.source), args.target_env))
        return

    result = migrate(
        source=Path(args.source),
        target_env=args.target_env,
        confirm_disposable=args.confirm_disposable,
        yes=args.yes,
    )
    print(result["warning"])
    print(f"Source DB: {result['source']}")
    print(f"Target env: {result['target_env']}")
    print(f"Inserted row counts: {result['inserted']}")


if __name__ == "__main__":
    main()
