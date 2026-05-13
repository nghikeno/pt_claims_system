from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from app.config import REAL_DB_PATH
from app.create_training_database import DEFAULT_TRAINING_DB_PATH, ensure_safe_training_target
from app.production_migrate_real_data import (
    compare_counts,
    migration_order,
    sqlite_counts,
    target_counts,
    target_is_empty,
    target_url_from_env,
    _connect_postgres,
    _execute_schema,
    _load_table,
    _reset_identity,
)


CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_IS_TRAINING_DATA_ONLY"
DEFAULT_TARGET_ENV = "TRAINING_DATABASE_URL"


def ensure_training_source(path: str | Path) -> Path:
    source = Path(path).expanduser().resolve()
    if source == REAL_DB_PATH.resolve() or source.name == "pt_claims.db":
        raise RuntimeError("Refusing to migrate the production SQLite database as training data.")
    ensure_safe_training_target(source)
    if not source.exists():
        raise RuntimeError("Training SQLite source database does not exist.")
    return source


def dry_run(source: str | Path = DEFAULT_TRAINING_DB_PATH, target_env: str = DEFAULT_TARGET_ENV, env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    source_path = ensure_training_source(source)
    return {
        "status": "PASS" if env.get(target_env) else "BLOCK",
        "source": str(source_path),
        "target_env": target_env,
        "target_configured": bool(env.get(target_env)),
        "source_counts": sqlite_counts(source_path),
        "writes_postgres": False,
        "migration_order": migration_order(),
    }


def migrate_training_database(
    source: str | Path = DEFAULT_TRAINING_DB_PATH,
    target_env: str = DEFAULT_TARGET_ENV,
    *,
    yes: bool = False,
    confirmation: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or dict(os.environ)
    source_path = ensure_training_source(source)
    if not yes:
        raise RuntimeError("Training migration write mode requires --yes.")
    if confirmation != CONFIRMATION_PHRASE:
        raise RuntimeError("Training migration requires the exact confirmation phrase.")
    target_url = target_url_from_env(target_env, env)
    source_counts = sqlite_counts(source_path)
    with _connect_postgres(target_url) as pg_conn:
        _execute_schema(pg_conn)
        before_counts = target_counts(pg_conn, migration_order())
        if not target_is_empty(before_counts):
            raise RuntimeError("Target training PostgreSQL database is not empty.")
        import sqlite3

        with sqlite3.connect(source_path) as sqlite_conn:
            sqlite_conn.row_factory = sqlite3.Row
            for table in migration_order():
                _load_table(sqlite_conn, pg_conn, table)
                _reset_identity(pg_conn, table)
        pg_conn.commit()
        after_counts = target_counts(pg_conn, migration_order())
    comparison = compare_counts(source_counts, after_counts, migration_order())
    return {
        "status": "PASS" if comparison["matches"] else "BLOCK",
        "source": str(source_path),
        "target_env": target_env,
        "source_counts": source_counts,
        "target_counts": after_counts,
        "count_comparison": comparison,
        "writes_postgres": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate dummy-only training data to a separate training PostgreSQL database.")
    parser.add_argument("--source", type=Path, default=DEFAULT_TRAINING_DB_PATH)
    parser.add_argument("--target-env", default=DEFAULT_TARGET_ENV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--confirm-training-migration", default="")
    args = parser.parse_args()
    if args.dry_run or not args.yes:
        result = dry_run(args.source, args.target_env)
    else:
        result = migrate_training_database(
            args.source,
            args.target_env,
            yes=args.yes,
            confirmation=args.confirm_training_migration,
        )
    print(f"Training migration status: {result['status']}")
    print(f"Source: {result['source']}")
    print(f"Target env: {result['target_env']} (value hidden)")
    for table, count in result.get("source_counts", {}).items():
        print(f"{table}: {count}")
    print("Writes PostgreSQL:", "yes" if result.get("writes_postgres") else "no")
    print("Secrets printed: no")


if __name__ == "__main__":
    main()
