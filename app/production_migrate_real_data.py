from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, REAL_DB_PATH
from app.document_storage import validate_storage_config
from app.postgres_schema import POSTGRES_SCHEMA_SQL, TABLE_ORDER


CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES"
DEFAULT_TARGET_ENV = "DATABASE_URL"
BACKUPS_DIR = DATA_DIR / "backups"
CORE_TABLES = list(TABLE_ORDER)


def normalise_postgres_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _status_rank(status: str) -> int:
    return {"PASS": 0, "WARN": 1, "BLOCK": 2}[status]


def _final_status(checks: list[dict[str, Any]]) -> str:
    return max((check["status"] for check in checks), key=_status_rank) if checks else "PASS"


def _check(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **extra}


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def sqlite_counts(source: str | Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(source) as conn:
        conn.row_factory = sqlite3.Row
        for table in CORE_TABLES:
            if sqlite_table_exists(conn, table):
                counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            else:
                counts[table] = 0
    return counts


def migration_order(skip_audit_logs: bool = False) -> list[str]:
    return [table for table in CORE_TABLES if not (skip_audit_logs and table == "audit_logs")]


def identity_reset_sql(table: str) -> str:
    if table not in CORE_TABLES:
        raise ValueError(f"Unsupported table for identity reset: {table}")
    return (
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
    )


def identity_reset_plan(skip_audit_logs: bool = False) -> list[dict[str, str]]:
    return [{"table": table, "sql": identity_reset_sql(table)} for table in migration_order(skip_audit_logs)]


def target_url_from_env(target_env: str = DEFAULT_TARGET_ENV, env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    url = str(env.get(target_env, "") or "").strip()
    if not url:
        raise RuntimeError(f"{target_env} is not configured.")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError(f"{target_env} must be a PostgreSQL URL.")
    return normalise_postgres_url(url)


def _connect_postgres(url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for real PostgreSQL migration.") from exc
    return psycopg.connect(url)


def _execute_schema(pg_conn) -> None:
    with pg_conn.cursor() as cur:
        for statement in [part.strip() for part in POSTGRES_SCHEMA_SQL.split(";") if part.strip()]:
            cur.execute(statement)


def _target_table_exists(pg_conn, table: str) -> bool:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
            """,
            (table,),
        )
        row = cur.fetchone()
    return bool(row[0] if not isinstance(row, dict) else row.get("exists"))


def target_counts(pg_conn, tables: list[str] | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    tables = tables or CORE_TABLES
    with pg_conn.cursor() as cur:
        for table in tables:
            if _target_table_exists(pg_conn, table):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                row = cur.fetchone()
                counts[table] = int(row[0] if not isinstance(row, dict) else row.get("count", 0))
            else:
                counts[table] = 0
    return counts


def target_is_empty(counts: dict[str, int]) -> bool:
    return all(value == 0 for value in counts.values())


def create_sqlite_backup(source: str | Path = REAL_DB_PATH) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"pt_claims_before_real_postgres_migration_{timestamp}.db"
    shutil.copy2(source, backup_path)
    return backup_path


def _load_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str) -> int:
    if not sqlite_table_exists(sqlite_conn, table):
        return 0
    columns = sqlite_columns(sqlite_conn, table)
    if not columns:
        return 0
    rows = sqlite_conn.execute(f'SELECT {", ".join(columns)} FROM "{table}" ORDER BY id').fetchall()
    if not rows:
        return 0
    placeholders = ", ".join(["%s"] * len(columns))
    columns_sql = ", ".join(columns)
    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})",
                tuple(row[column] for column in columns),
            )
    return len(rows)


def _reset_identity(pg_conn, table: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(identity_reset_sql(table))


def compare_counts(source_counts: dict[str, int], target_count_values: dict[str, int], tables: list[str] | None = None) -> dict[str, Any]:
    tables = tables or CORE_TABLES
    mismatches = {
        table: {"source": source_counts.get(table, 0), "target": target_count_values.get(table, 0)}
        for table in tables
        if source_counts.get(table, 0) != target_count_values.get(table, 0)
    }
    return {"matches": not mismatches, "mismatches": mismatches}


def build_dry_run_report(
    source: str | Path = REAL_DB_PATH,
    target_env: str = DEFAULT_TARGET_ENV,
    env: dict[str, str] | None = None,
    skip_audit_logs: bool = False,
) -> dict[str, Any]:
    env = env or dict(os.environ)
    source = Path(source)
    checks: list[dict[str, Any]] = []
    if not source.exists():
        checks.append(_check("BLOCK", "Source SQLite database does not exist."))
        counts: dict[str, int] = {}
    else:
        counts = sqlite_counts(source)
        checks.append(_check("PASS", "Source SQLite database exists and counts were inspected."))
    target_set = bool(str(env.get(target_env, "") or "").strip())
    if target_set:
        checks.append(_check("PASS", f"Target env {target_env} is set. Value hidden."))
    else:
        checks.append(_check("BLOCK", f"Target env {target_env} is not set."))
    storage = validate_storage_config(env=env, mode=env.get("DOCUMENT_STORAGE_MODE"))
    if storage.mode == "object_storage" and storage.ready:
        checks.append(_check("PASS", "Object storage readiness check passed."))
    else:
        checks.append(_check("BLOCK", "Object storage is not ready for production migration.", missing_keys=storage.missing_keys))
    checks.append(_check("BLOCK", "Write mode additionally requires --yes, exact confirmation phrase, and --backup-acknowledged."))
    return {
        "status": _final_status(checks),
        "source_db": str(source),
        "target_env": target_env,
        "target_configured": target_set,
        "source_counts": counts,
        "migration_order": migration_order(skip_audit_logs),
        "identity_reset_plan": identity_reset_plan(skip_audit_logs),
        "checks": checks,
        "backup_gate_required": True,
        "writes_postgres": False,
        "recommendation": "Do not run write mode until backups, empty target PostgreSQL, object storage, secrets, and access-control review are confirmed.",
    }


def migrate_real_data(
    source: str | Path = REAL_DB_PATH,
    target_env: str = DEFAULT_TARGET_ENV,
    *,
    yes: bool = False,
    confirmation: str = "",
    backup_acknowledged: bool = False,
    skip_audit_logs: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or dict(os.environ)
    if not yes:
        raise PermissionError("--yes is required for real production migration.")
    if confirmation != CONFIRMATION_PHRASE:
        raise PermissionError(f"--confirm-real-production-migration {CONFIRMATION_PHRASE} is required.")
    if not backup_acknowledged:
        raise PermissionError("--backup-acknowledged is required for real production migration.")
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Source SQLite database not found: {source}")
    target_url = target_url_from_env(target_env, env)
    storage = validate_storage_config(env=env, mode=env.get("DOCUMENT_STORAGE_MODE"))
    if storage.mode != "object_storage" or not storage.ready:
        raise PermissionError("Object storage must be configured before real production migration.")

    source_counts = sqlite_counts(source)
    tables = migration_order(skip_audit_logs)
    backup_path = create_sqlite_backup(source)
    inserted: dict[str, int] = {}
    with sqlite3.connect(source) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        with _connect_postgres(target_url) as pg_conn:
            try:
                _execute_schema(pg_conn)
                before_counts = target_counts(pg_conn, tables)
                if not target_is_empty(before_counts):
                    raise PermissionError("Target PostgreSQL contains data in core tables. Migration is blocked.")
                for table in tables:
                    inserted[table] = _load_table(sqlite_conn, pg_conn, table)
                for table in tables:
                    _reset_identity(pg_conn, table)
                after_counts = target_counts(pg_conn, tables)
                comparison = compare_counts(source_counts, after_counts, tables)
                if not comparison["matches"]:
                    raise RuntimeError(f"Target count comparison failed: {comparison['mismatches']}")
                pg_conn.commit()
            except Exception:
                pg_conn.rollback()
                raise
    return {
        "status": "PASS",
        "source_db": str(source),
        "target_env": target_env,
        "backup_path": str(backup_path),
        "source_counts": {table: source_counts.get(table, 0) for table in tables},
        "inserted": inserted,
        "target_counts": after_counts,
        "count_comparison": comparison,
        "writes_postgres": True,
    }


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "Real PostgreSQL Migration Gate",
        "==============================",
        f"Status: {report['status']}",
        f"Source DB: {report.get('source_db')}",
        f"Target env: {report.get('target_env')}",
        f"Writes PostgreSQL: {'yes' if report.get('writes_postgres') else 'no'}",
        "",
        "Source table counts:",
    ]
    for table, count in report.get("source_counts", {}).items():
        lines.append(f"- {table}: {count}")
    if report.get("migration_order"):
        lines.extend(["", "Migration order:"])
        lines.extend(f"- {table}" for table in report["migration_order"])
    if report.get("checks"):
        lines.extend(["", "Checks:"])
        for check in report["checks"]:
            lines.append(f"[{check['status']}] {check['message']}")
            if check.get("missing_keys"):
                lines.append("Missing keys: " + ", ".join(check["missing_keys"]))
    if report.get("recommendation"):
        lines.extend(["", f"Recommendation: {report['recommendation']}"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded real-data SQLite to PostgreSQL migration command.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect gates only. Default when no write flags are supplied.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source", type=Path, default=REAL_DB_PATH)
    parser.add_argument("--target-env", default=DEFAULT_TARGET_ENV)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--confirm-real-production-migration", default="")
    parser.add_argument("--backup-acknowledged", action="store_true")
    parser.add_argument("--skip-audit-logs", action="store_true")
    args = parser.parse_args()

    write_requested = args.yes or bool(args.confirm_real_production_migration) or args.backup_acknowledged
    if args.dry_run or not write_requested:
        report = build_dry_run_report(args.source, args.target_env, skip_audit_logs=args.skip_audit_logs)
    else:
        try:
            report = migrate_real_data(
                args.source,
                args.target_env,
                yes=args.yes,
                confirmation=args.confirm_real_production_migration,
                backup_acknowledged=args.backup_acknowledged,
                skip_audit_logs=args.skip_audit_logs,
            )
        except Exception as exc:
            report = {
                "status": "BLOCK",
                "source_db": str(args.source),
                "target_env": args.target_env,
                "writes_postgres": False,
                "source_counts": sqlite_counts(args.source) if Path(args.source).exists() else {},
                "checks": [_check("BLOCK", f"Migration refused or failed: {type(exc).__name__}")],
                "recommendation": str(exc),
            }
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(render_text_report(report))
            raise SystemExit(1)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    if report["status"] == "BLOCK" and write_requested:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
