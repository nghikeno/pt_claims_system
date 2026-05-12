from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import DB_PATH
from app.postgres_schema import TABLE_ORDER, postgres_schema_sql


CORE_TABLES = [
    "lecturers",
    "courses",
    "student_groups",
    "timetable_entries",
    "academic_calendar",
    "students",
    "group_enrolments",
    "user_accounts",
    "audit_logs",
]


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _table_columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [
        {"name": row[1], "type": row[2], "notnull": bool(row[3]), "default": row[4], "pk": bool(row[5])}
        for row in rows
    ]


def _sqlite_specific_findings(conn: sqlite3.Connection, tables: list[str]) -> list[str]:
    findings: list[str] = []
    for table in tables:
        sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        sql = str(sql_row[0] or "") if sql_row else ""
        lowered = sql.lower()
        if "autoincrement" in lowered:
            findings.append(f"{table}: uses AUTOINCREMENT and needs PostgreSQL identity handling.")
        if "pragma" in lowered or "sqlite_master" in lowered:
            findings.append(f"{table}: contains SQLite-specific schema text.")
    return findings


def build_migration_plan(db_path: str | Path = DB_PATH) -> dict[str, Any]:
    db_path = Path(db_path)
    if not db_path.exists():
        return {
            "status": "BLOCK",
            "source_db": str(db_path),
            "tables": {},
            "row_counts": {},
            "warnings": [],
            "blockers": ["Source SQLite database does not exist."],
            "required_backup_steps": [],
            "message": "Production migration dry-run failed before schema inspection.",
        }

    with sqlite3.connect(db_path) as conn:
        tables = _sqlite_tables(conn)
        row_counts = {table: _count_rows(conn, table) for table in tables}
        table_columns = {table: _table_columns(conn, table) for table in tables}
        sqlite_findings = _sqlite_specific_findings(conn, tables)

    expected_tables = set(TABLE_ORDER)
    current_tables = set(tables)
    missing_expected = sorted(expected_tables - current_tables)
    extra_tables = sorted(current_tables - expected_tables)
    schema_sql = postgres_schema_sql().lower()
    postgres_schema_warnings = []
    for token in ["autoincrement", "sqlite_master", "pragma"]:
        if token in schema_sql:
            postgres_schema_warnings.append(f"Expected PostgreSQL schema still contains SQLite-specific token: {token}.")

    warnings = []
    if extra_tables:
        warnings.append("SQLite source has extra tables not in the current PostgreSQL table order: " + ", ".join(extra_tables))
    if sqlite_findings:
        warnings.extend(sqlite_findings)
    warnings.extend(postgres_schema_warnings)

    blockers = [
        "This is a dry-run only. Real data migration remains blocked until the guarded real migration command dry-run passes.",
        "Write mode remains blocked until backup is acknowledged, target PostgreSQL is selected, target core tables are empty, object storage is ready, and explicit confirmation is supplied.",
        "Disposable anonymised migration tooling must remain separate from any future real-data migration.",
    ]
    if missing_expected:
        blockers.append("SQLite source is missing expected tables: " + ", ".join(missing_expected))

    return {
        "status": "BLOCK" if blockers else "PASS",
        "source_db": str(db_path),
        "tables_covered": [table for table in CORE_TABLES if table in current_tables],
        "tables_missing": missing_expected,
        "extra_tables": extra_tables,
        "row_counts": row_counts,
        "table_columns": table_columns,
        "warnings": warnings,
        "blockers": blockers,
        "required_backup_steps": [
            "Create a verified offline copy of the real SQLite database before any approved migration.",
            "Verify provider-level PostgreSQL backups and point-in-time recovery before loading real data.",
            "Run anonymised staging migration and runtime validation before any real-data attempt.",
            "Run access-control and document-storage readiness checks before opening the app to users.",
        ],
        "risky_fields": [
            "user_accounts.password_hash and password_salt must migrate without plaintext exposure.",
            "lecturer ID/passport, PAYE, contact, and address fields are sensitive.",
            "student names and numbers are sensitive institutional data.",
            "audit_logs.details_json must not contain secrets.",
        ],
        "message": "Production migration dry-run inspected SQLite schema and counts without writing to PostgreSQL.",
        "real_migration_command": "python -m app.production_migrate_real_data --dry-run",
        "guarded_write_command": "python -m app.production_migrate_real_data --yes --backup-acknowledged --confirm-real-production-migration I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES",
    }


def render_text_report(plan: dict[str, Any]) -> str:
    lines = [
        "Production Migration Dry-Run Plan",
        "=================================",
        f"Status: {plan['status']}",
        f"Source SQLite DB: {plan['source_db']}",
        "",
        "Tables covered:",
    ]
    for table in plan.get("tables_covered", []):
        lines.append(f"- {table}: {plan['row_counts'].get(table, 0)} rows")
    if plan.get("tables_missing"):
        lines.extend(["", "Missing expected tables:"])
        lines.extend(f"- {table}" for table in plan["tables_missing"])
    if plan.get("warnings"):
        lines.extend(["", "Warnings:"])
        lines.extend(f"[WARN] {warning}" for warning in plan["warnings"])
    if plan.get("blockers"):
        lines.extend(["", "Blockers:"])
        lines.extend(f"[BLOCK] {blocker}" for blocker in plan["blockers"])
    if plan.get("real_migration_command"):
        lines.extend(["", "Guarded real migration command:"])
        lines.append(plan["real_migration_command"])
        lines.append("Write mode command, do not run until approved:")
        lines.append(plan["guarded_write_command"])
    lines.extend(["", "Required backup steps:"])
    lines.extend(f"- {step}" for step in plan.get("required_backup_steps", []))
    lines.extend(["", plan["message"]])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run a real production PostgreSQL migration plan without writing data.")
    parser.add_argument("--dry-run", action="store_true", help="Required. Inspect only; do not write to PostgreSQL.")
    parser.add_argument("--source", type=Path, default=DB_PATH, help="SQLite source path to inspect.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    if not args.dry_run:
        raise SystemExit("This command is dry-run only. Re-run with --dry-run.")
    plan = build_migration_plan(args.source)
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_text_report(plan))


if __name__ == "__main__":
    main()
