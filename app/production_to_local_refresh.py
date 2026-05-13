from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.config import DATA_DIR, DB_PATH, database_provider, database_url
from app.db_provider import close_postgres_pool, get_runtime_connection, rows_to_dicts
from app.local_first_sync import EXCLUDED_TABLES, SUPPORTED_TABLES, open_sqlite, table_counts


COPY_CONFIRMATION = "I_UNDERSTAND_THIS_WILL_COPY_PRODUCTION_OPERATIONAL_DATA_TO_LOCAL"
REPLACE_CONFIRMATION = "I_UNDERSTAND_THIS_WILL_REPLACE_LOCAL_OPERATIONAL_DATA_WITH_PRODUCTION"
DELETE_ORDER = [
    "group_enrolments",
    "timetable_entries",
    "student_groups",
    "students",
    "academic_calendar",
    "courses",
    "lecturers",
]
INSERT_ORDER = [
    "lecturers",
    "courses",
    "students",
    "student_groups",
    "timetable_entries",
    "group_enrolments",
    "academic_calendar",
]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _connect_sqlite(path: str | Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: Any, table: str) -> list[str]:
    return [row[1] if not isinstance(row, sqlite3.Row) else row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def fetch_plain_rows(conn: Any, table: str) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall())


def fetch_production_rows(prod_conn: Any, tables: Iterable[str] = SUPPORTED_TABLES) -> dict[str, list[dict[str, Any]]]:
    return {table: fetch_plain_rows(prod_conn, table) for table in tables}


def validate_local_path(local_path: Path, allow_training_local: bool = False) -> list[str]:
    blockers = []
    if not local_path.exists():
        blockers.append(f"Local SQLite file is missing: {local_path}")
    lowered = str(local_path).replace("\\", "/").lower()
    if "/data/training/" in lowered and not allow_training_local:
        blockers.append("Local path appears to be a training database. Use an explicit training workflow instead.")
    return blockers


def validate_output_path(output_path: Path | None, local_path: Path, replace_local: bool = False) -> list[str]:
    blockers = []
    if output_path is None:
        return blockers
    if output_path.suffix.lower() != ".db":
        blockers.append("Output path must be a .db SQLite file.")
    if output_path.resolve() == local_path.resolve() and not replace_local:
        blockers.append("Output path cannot be the active local DB unless --replace-local is used.")
    forbidden_markers = {".streamlit", ".env", "secrets.toml"}
    lowered = str(output_path).lower()
    if any(marker in lowered for marker in forbidden_markers):
        blockers.append("Output path is not safe for a refreshed database.")
    return blockers


def require_production_read_available() -> list[str]:
    blockers = []
    if not database_url():
        blockers.append("DATABASE_URL is not configured.")
    if database_provider() != "postgresql":
        blockers.append("Production refresh requires DATABASE_URL configured for PostgreSQL.")
    return blockers


def build_report(
    local_path: str | Path = DB_PATH,
    output_path: str | Path | None = None,
    allow_training_local: bool = False,
    production_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    local = Path(local_path)
    output = Path(output_path) if output_path else None
    blockers = []
    blockers.extend(require_production_read_available())
    blockers.extend(validate_local_path(local, allow_training_local=allow_training_local))
    blockers.extend(validate_output_path(output, local))
    local_counts = {}
    production_counts = {}
    if local.exists():
        with open_sqlite(local) as local_conn:
            local_counts = table_counts(local_conn, SUPPORTED_TABLES)
    if production_rows is not None:
        production_counts = {table: len(rows) for table, rows in production_rows.items()}
    elif not blockers:
        with get_runtime_connection() as prod_conn:
            production_rows = fetch_production_rows(prod_conn)
            production_counts = {table: len(rows) for table, rows in production_rows.items()}
    rows_replaced = {table: {"local": local_counts.get(table, 0), "production": production_counts.get(table, 0)} for table in SUPPORTED_TABLES}
    return {
        "provider": database_provider(),
        "production_target_present": bool(database_url()),
        "local_sqlite_path": str(local),
        "output_path": str(output) if output else None,
        "tables_included": list(SUPPORTED_TABLES),
        "excluded_tables": EXCLUDED_TABLES,
        "local_counts": local_counts,
        "production_counts": production_counts,
        "rows_replaced": rows_replaced,
        "warnings": [
            "Production is read-only for this command.",
            "Local user_accounts, password hashes/salts, and audit_logs are preserved.",
            "Local user_accounts may not include newly created production lecturer accounts.",
        ],
        "blockers": blockers,
        "secrets_printed": False,
    }


def _insert_rows(dest_conn: Any, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = _table_columns(dest_conn, table)
    for row in rows:
        insert_columns = [column for column in columns if column in row]
        placeholders = ", ".join("?" for _ in insert_columns)
        column_sql = ", ".join(insert_columns)
        dest_conn.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
            tuple(row.get(column) for column in insert_columns),
        )


def replace_supported_tables(dest_path: str | Path, production_rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    conn = _connect_sqlite(dest_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            for table in DELETE_ORDER:
                conn.execute(f"DELETE FROM {table}")
            for table in INSERT_ORDER:
                _insert_rows(conn, table, production_rows.get(table, []))
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?" for _ in SUPPORTED_TABLES), tuple(SUPPORTED_TABLES))
            for table in SUPPORTED_TABLES:
                conn.execute("INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES (?, COALESCE((SELECT MAX(id) FROM %s), 0))" % table, (table,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
        return table_counts(conn, SUPPORTED_TABLES)
    finally:
        conn.close()


def create_local_backup(local_path: str | Path = DB_PATH) -> Path:
    source = Path(local_path)
    backup_path = source.parent / f"{source.stem}_BEFORE_PRODUCTION_REFRESH_{_timestamp()}{source.suffix}"
    counter = 1
    while backup_path.exists():
        backup_path = source.parent / f"{source.stem}_BEFORE_PRODUCTION_REFRESH_{_timestamp()}_{counter}{source.suffix}"
        counter += 1
    shutil.copy2(source, backup_path)
    return backup_path


def build_refreshed_copy(local_path: str | Path, output_path: str | Path, production_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    source = Path(local_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    counts = replace_supported_tables(output, production_rows)
    expected = {table: len(production_rows.get(table, [])) for table in SUPPORTED_TABLES}
    if counts != expected:
        raise RuntimeError("Refreshed local copy count validation failed.")
    return {"output_path": str(output), "counts": counts}


def run_refresh(args: argparse.Namespace) -> dict[str, Any]:
    local_path = Path(args.local_path or DB_PATH)
    if args.replace_local:
        if not args.backup_local:
            raise PermissionError("--replace-local requires --backup-local.")
        if args.confirm_refresh != REPLACE_CONFIRMATION:
            raise PermissionError("Replacing local DB requires the exact replace-local confirmation phrase.")
    else:
        if args.confirm_refresh != COPY_CONFIRMATION:
            raise PermissionError("Creating a refreshed local copy requires the exact copy confirmation phrase.")
    blockers = require_production_read_available()
    blockers.extend(validate_local_path(local_path, allow_training_local=args.allow_training_local))
    output_path = Path(args.output) if args.output else DATA_DIR / "pt_claims_FROM_PRODUCTION_REFRESHED.db"
    blockers.extend(validate_output_path(output_path, local_path, replace_local=args.replace_local))
    if blockers:
        raise RuntimeError("; ".join(blockers))
    with get_runtime_connection() as prod_conn:
        production_rows = fetch_production_rows(prod_conn)
    backup_path = None
    if args.replace_local:
        backup_path = create_local_backup(local_path)
        temp_path = local_path.parent / f"{local_path.stem}_REFRESH_BUILD_{_timestamp()}{local_path.suffix}"
        result = build_refreshed_copy(local_path, temp_path, production_rows)
        try:
            os.replace(temp_path, local_path)
        except PermissionError:
            local_path.unlink()
            os.replace(temp_path, local_path)
        result["output_path"] = str(local_path)
    else:
        result = build_refreshed_copy(local_path, output_path, production_rows)
    report = build_report(local_path, result["output_path"], allow_training_local=args.allow_training_local, production_rows=production_rows)
    report["refresh_result"] = result
    report["backup_path"] = str(backup_path) if backup_path else None
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "Production-to-Local Refresh Report",
        "==================================",
        f"Provider mode: {report['provider']}",
        f"Production target present: {'yes' if report['production_target_present'] else 'no'}",
        f"Local SQLite path: {report['local_sqlite_path']}",
        f"Output path: {report.get('output_path') or 'not specified'}",
        f"Tables included: {', '.join(report['tables_included'])}",
        f"Excluded tables: {', '.join(report['excluded_tables'])}",
        "",
        "Counts:",
    ]
    for table in SUPPORTED_TABLES:
        local_count = report.get("local_counts", {}).get(table, 0)
        production_count = report.get("production_counts", {}).get(table, 0)
        lines.append(f"- {table}: local={local_count} production={production_count}")
    if report.get("backup_path"):
        lines.append("")
        lines.append(f"Local backup created: {report['backup_path']}")
    if report.get("blockers"):
        lines.append("")
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    if report.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    lines.append("Secrets printed: no")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh a local SQLite DB from production PostgreSQL operational data.")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--replace-local", action="store_true")
    parser.add_argument("--backup-local", action="store_true")
    parser.add_argument("--confirm-refresh", default="")
    parser.add_argument("--local-path", default="")
    parser.add_argument("--allow-training-local", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.yes:
            report = run_refresh(args)
        else:
            report = build_report(args.local_path or DB_PATH, args.output or None, allow_training_local=args.allow_training_local)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            print(render_text_report(report))
        return 0 if not report.get("blockers") else 2
    except Exception as exc:
        print(f"Production-to-local refresh failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        close_postgres_pool()


if __name__ == "__main__":
    raise SystemExit(main())
