from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.config import DB_PATH, database_provider, database_url
from app.db_provider import convert_placeholders, get_runtime_connection, row_to_dict, rows_to_dicts


SUPPORTED_TABLES = [
    "lecturers",
    "courses",
    "student_groups",
    "timetable_entries",
    "students",
    "group_enrolments",
    "academic_calendar",
]
EXCLUDED_TABLES = ["user_accounts", "audit_logs", "generated_documents", "object_storage_objects", "local_backups"]
CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_WILL_WRITE_LOCAL_CHANGES_TO_PRODUCTION"

SENSITIVE_KEYS = {
    "id_or_passport_number",
    "paye_number",
    "physical_address",
    "contact_number",
    "password_hash",
    "password_salt",
}


@dataclass
class Operation:
    action: str
    table: str
    key: str
    identifier: dict[str, Any]
    fields: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class TablePlan:
    table: str
    inserts: list[Operation] = field(default_factory=list)
    updates: list[Operation] = field(default_factory=list)
    skipped: list[Operation] = field(default_factory=list)
    conflicts: list[Operation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "inserts": len(self.inserts),
            "updates": len(self.updates),
            "skipped": len(self.skipped),
            "conflicts": len(self.conflicts),
            "warnings": list(self.warnings),
            "records": {
                "inserts": [_safe_operation(op) for op in self.inserts],
                "updates": [_safe_operation(op) for op in self.updates],
                "conflicts": [_safe_operation(op) for op in self.conflicts],
            },
        }


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: ("[redacted]" if key in SENSITIVE_KEYS else value) for key, value in data.items() if key not in SENSITIVE_KEYS}


def _safe_operation(op: Operation) -> dict[str, Any]:
    return {
        "action": op.action,
        "table": op.table,
        "key": op.key,
        "identifier": _safe_dict(op.identifier),
        "fields": _safe_dict(op.fields),
        "reason": op.reason,
    }


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    return rows_to_dicts(conn.execute(convert_placeholders(sql), params).fetchall())


def _one(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict | None:
    return row_to_dict(conn.execute(convert_placeholders(sql), params).fetchone())


def open_sqlite(path: str | Path = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_counts(conn: Any, tables: Iterable[str] = SUPPORTED_TABLES) -> dict[str, int]:
    counts = {}
    for table in tables:
        try:
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            counts[table] = 0
    return counts


def fetch_records(conn: Any, table: str) -> list[dict[str, Any]]:
    if table == "lecturers":
        return _rows(conn, "SELECT * FROM lecturers")
    if table == "courses":
        return _rows(conn, "SELECT * FROM courses")
    if table == "students":
        return _rows(conn, "SELECT * FROM students")
    if table == "student_groups":
        return _rows(
            conn,
            """
            SELECT sg.*, l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, c.course_name
            FROM student_groups AS sg
            LEFT JOIN lecturers AS l ON l.id = sg.lecturer_id
            JOIN courses AS c ON c.id = sg.course_id
            """,
        )
    if table == "timetable_entries":
        return _rows(
            conn,
            """
            SELECT te.*, l.staff_number, c.course_code, sg.group_name
            FROM timetable_entries AS te
            JOIN lecturers AS l ON l.id = te.lecturer_id
            JOIN student_groups AS sg ON sg.id = te.group_id
            JOIN courses AS c ON c.id = sg.course_id
            """,
        )
    if table == "group_enrolments":
        return _rows(
            conn,
            """
            SELECT ge.*, s.student_number, l.staff_number, c.course_code, sg.group_name
            FROM group_enrolments AS ge
            JOIN students AS s ON s.id = ge.student_id
            JOIN student_groups AS sg ON sg.id = ge.group_id
            JOIN lecturers AS l ON l.id = sg.lecturer_id
            JOIN courses AS c ON c.id = sg.course_id
            """,
        )
    if table == "academic_calendar":
        return _rows(
            conn,
            """
            SELECT ac.*, l.staff_number, c.course_code, sg.group_name
            FROM academic_calendar AS ac
            LEFT JOIN lecturers AS l ON l.id = ac.lecturer_id
            LEFT JOIN courses AS c ON c.id = ac.course_id
            LEFT JOIN student_groups AS sg ON sg.id = ac.group_id
            """,
        )
    raise ValueError(f"Unsupported table: {table}")


def natural_key(table: str, row: dict[str, Any]) -> str:
    if table == "lecturers":
        return _clean(row.get("staff_number"))
    if table == "courses":
        return _clean(row.get("course_code")).upper()
    if table == "students":
        return _clean(row.get("student_number")).upper()
    if table == "student_groups":
        return "|".join([_clean(row.get("staff_number")), _clean(row.get("course_code")).upper(), _clean(row.get("group_name"))])
    if table == "timetable_entries":
        return "|".join(
            [
                _clean(row.get("staff_number")),
                _clean(row.get("course_code")).upper(),
                _clean(row.get("group_name")),
                _clean(row.get("day_of_week")),
                _clean(row.get("start_time")),
                _clean(row.get("end_time")),
                _clean(row.get("effective_start_date")),
                _clean(row.get("effective_end_date")),
            ]
        )
    if table == "group_enrolments":
        return "|".join(
            [
                _clean(row.get("student_number")).upper(),
                _clean(row.get("staff_number")),
                _clean(row.get("course_code")).upper(),
                _clean(row.get("group_name")),
            ]
        )
    if table == "academic_calendar":
        return "|".join(
            [
                _clean(row.get("title")),
                _clean(row.get("calendar_type")),
                _clean(row.get("start_date")),
                _clean(row.get("end_date")),
                _clean(row.get("scope_type") or "all"),
                _clean(row.get("staff_number")),
                _clean(row.get("course_code")),
                _clean(row.get("group_name")),
            ]
        )
    raise ValueError(f"Unsupported table: {table}")


def safe_identifier(table: str, row: dict[str, Any]) -> dict[str, Any]:
    if table == "lecturers":
        return {"staff_number": row.get("staff_number"), "full_name": row.get("full_name")}
    if table == "courses":
        return {"course_code": row.get("course_code")}
    if table == "students":
        return {"student_number": row.get("student_number")}
    if table == "student_groups":
        return {"staff_number": row.get("staff_number"), "course_code": row.get("course_code"), "group_name": row.get("group_name")}
    if table == "timetable_entries":
        return {
            "staff_number": row.get("staff_number"),
            "course_code": row.get("course_code"),
            "group_name": row.get("group_name"),
            "day_of_week": row.get("day_of_week"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "effective_start_date": row.get("effective_start_date"),
            "effective_end_date": row.get("effective_end_date"),
        }
    if table == "group_enrolments":
        return {
            "student_number": row.get("student_number"),
            "staff_number": row.get("staff_number"),
            "course_code": row.get("course_code"),
            "group_name": row.get("group_name"),
        }
    if table == "academic_calendar":
        return {
            "title": row.get("title"),
            "calendar_type": row.get("calendar_type"),
            "start_date": row.get("start_date"),
            "end_date": row.get("end_date"),
            "scope_type": row.get("scope_type") or "all",
        }
    return {"key": natural_key(table, row)}


def duplicate_keys(rows: list[dict], table: str) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for row in rows:
        key = natural_key(table, row)
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return dupes


def _diff_fields(local: dict, production: dict, fields: list[str]) -> dict[str, dict[str, Any]]:
    diff = {}
    for field_name in fields:
        if _clean(local.get(field_name)) != _clean(production.get(field_name)):
            diff[field_name] = {"local": local.get(field_name), "production": production.get(field_name)}
    return diff


def _time_overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return _clean(a_start) < _clean(b_end) and _clean(a_end) > _clean(b_start)


def _date_overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return _clean(a_start) <= _clean(b_end) and _clean(a_end) >= _clean(b_start)


def timetable_overlap_conflict(local_row: dict, production_rows: list[dict]) -> str | None:
    for prod in production_rows:
        same_key = natural_key("timetable_entries", local_row) == natural_key("timetable_entries", prod)
        same_lecturer = _clean(local_row.get("staff_number")) == _clean(prod.get("staff_number"))
        same_group = (
            _clean(local_row.get("staff_number")) == _clean(prod.get("staff_number"))
            and _clean(local_row.get("course_code")) == _clean(prod.get("course_code"))
            and _clean(local_row.get("group_name")) == _clean(prod.get("group_name"))
        )
        if same_key or not (same_lecturer or same_group):
            continue
        if _clean(local_row.get("day_of_week")) != _clean(prod.get("day_of_week")):
            continue
        if _date_overlaps(local_row["effective_start_date"], local_row["effective_end_date"], prod["effective_start_date"], prod["effective_end_date"]) and _time_overlaps(
            local_row["start_time"], local_row["end_time"], prod["start_time"], prod["end_time"]
        ):
            return "Local timetable entry overlaps an existing production timetable entry."
    return None


def build_table_plan(table: str, local_rows: list[dict], production_rows: list[dict], all_local: dict[str, list[dict]], all_prod: dict[str, list[dict]]) -> TablePlan:
    plan = TablePlan(table)
    local_dupes = duplicate_keys(local_rows, table)
    prod_dupes = duplicate_keys(production_rows, table)
    prod_by_key = {natural_key(table, row): row for row in production_rows}

    for duplicate in sorted(local_dupes):
        plan.conflicts.append(Operation("conflict", table, duplicate, {"natural_key": duplicate}, reason="Duplicate natural key exists in local data."))
    for duplicate in sorted(prod_dupes):
        plan.conflicts.append(Operation("conflict", table, duplicate, {"natural_key": duplicate}, reason="Duplicate natural key exists in production data."))

    for row in local_rows:
        key = natural_key(table, row)
        if key in local_dupes or key in prod_dupes:
            continue
        identifier = safe_identifier(table, row)
        prod = prod_by_key.get(key)
        if table == "student_groups" and not row.get("lecturer_id"):
            plan.conflicts.append(Operation("conflict", table, key, identifier, reason="Generic groups are not supported by Phase 14.9 sync."))
            continue
        if prod is None:
            if table == "timetable_entries":
                overlap = timetable_overlap_conflict(row, production_rows)
                if overlap:
                    plan.conflicts.append(Operation("conflict", table, key, identifier, reason=overlap))
                    continue
            plan.inserts.append(Operation("insert", table, key, identifier))
            continue
        conflict_fields = []
        update_fields = []
        if table == "lecturers":
            conflict_fields = ["full_name"]
            update_fields = ["title", "highest_qualification", "tariff_per_hour", "campus", "contract_start_date", "contract_end_date", "active"]
        elif table == "courses":
            conflict_fields = ["course_name", "department", "budget_allocation"]
            update_fields = ["faculty", "active"]
        elif table == "students":
            conflict_fields = ["surname", "initials", "full_name"]
            update_fields = ["active"]
        elif table == "student_groups":
            conflict_fields = ["staff_number", "course_code"]
            update_fields = ["campus", "study_mode", "active"]
        elif table == "timetable_entries":
            update_fields = ["active"]
        elif table == "group_enrolments":
            update_fields = ["active"]
        elif table == "academic_calendar":
            update_fields = ["calendar_type", "action", "allow_override", "start_time", "end_time", "exclude_from_claims_and_registers", "notes", "active"]
        conflicts = _diff_fields(row, prod, conflict_fields)
        if conflicts:
            plan.conflicts.append(Operation("conflict", table, key, identifier, fields=conflicts, reason="Natural key exists with conflicting production values."))
            continue
        updates = _diff_fields(row, prod, update_fields)
        if updates:
            plan.updates.append(Operation("update", table, key, identifier, fields=updates))
        else:
            plan.skipped.append(Operation("skip", table, key, identifier, reason="Already in sync."))
    return plan


def parse_tables(value: str | None) -> list[str]:
    if not value:
        return list(SUPPORTED_TABLES)
    tables = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [table for table in tables if table not in SUPPORTED_TABLES]
    if unknown:
        raise ValueError(f"Unsupported table(s): {', '.join(unknown)}")
    return tables


def build_sync_plan(local_conn: Any, production_conn: Any | None, tables: list[str]) -> dict[str, Any]:
    all_local = {table: fetch_records(local_conn, table) for table in tables}
    all_prod = {table: fetch_records(production_conn, table) if production_conn is not None else [] for table in tables}
    table_plans = [build_table_plan(table, all_local[table], all_prod[table], all_local, all_prod) for table in tables]
    blockers = []
    if production_conn is None:
        blockers.append("Production PostgreSQL connection is not configured; dry-run cannot compare target records.")
    for table_plan in table_plans:
        if table_plan.conflicts:
            blockers.append(f"{table_plan.table} has {len(table_plan.conflicts)} conflict(s).")
    return {
        "provider": database_provider(),
        "local_sqlite_path": str(DB_PATH),
        "production_target_present": bool(database_url()),
        "tables_included": tables,
        "excluded_tables": EXCLUDED_TABLES,
        "plans": [table_plan.summary() for table_plan in table_plans],
        "blockers": blockers,
        "warnings": ["No deletes are supported in Phase 14.9.", "user_accounts, password hashes, audit logs, generated documents, and object-storage objects are excluded."],
        "secrets_printed": False,
    }


def _lookup_id(conn: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    row = _one(conn, f"SELECT id FROM {table} WHERE {where_sql}", params)
    if not row:
        raise RuntimeError(f"Required production reference missing in {table}.")
    return int(row["id"])


def _lookup_group_id(conn: Any, row: dict[str, Any]) -> int:
    data = _one(
        conn,
        """
        SELECT sg.id
        FROM student_groups AS sg
        JOIN lecturers AS l ON l.id = sg.lecturer_id
        JOIN courses AS c ON c.id = sg.course_id
        WHERE l.staff_number = ? AND c.course_code = ? AND sg.group_name = ?
        """,
        (_clean(row.get("staff_number")), _clean(row.get("course_code")), _clean(row.get("group_name"))),
    )
    if not data:
        raise RuntimeError("Required production group reference missing.")
    return int(data["id"])


def _update_by_id(conn: Any, table: str, row_id: int, values: dict[str, Any]) -> None:
    if not values:
        return
    assignments = ", ".join(f"{field_name} = ?" for field_name in values)
    conn.execute(convert_placeholders(f"UPDATE {table} SET {assignments} WHERE id = ?"), (*values.values(), int(row_id)))


def _apply_table(conn: Any, table: str, operations: list[Operation], local_rows: dict[str, dict]) -> None:
    for op in operations:
        row = local_rows[op.key]
        if table == "lecturers" and op.action == "insert":
            conn.execute(
                convert_placeholders(
                    """
                    INSERT INTO lecturers (staff_number, title, full_name, highest_qualification, id_or_passport_number,
                    paye_number, physical_address, contact_number, tariff_per_hour, campus, contract_start_date, contract_end_date, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                tuple(row.get(field) for field in ["staff_number", "title", "full_name", "highest_qualification", "id_or_passport_number", "paye_number", "physical_address", "contact_number", "tariff_per_hour", "campus", "contract_start_date", "contract_end_date", "active"]),
            )
        elif table == "courses" and op.action == "insert":
            conn.execute(
                convert_placeholders("INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active) VALUES (?, ?, ?, ?, ?, ?)"),
                tuple(row.get(field) for field in ["course_code", "course_name", "faculty", "department", "budget_allocation", "active"]),
            )
        elif table == "students" and op.action == "insert":
            conn.execute(
                convert_placeholders("INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, ?)"),
                tuple(row.get(field) for field in ["student_number", "surname", "initials", "full_name", "active"]),
            )
        elif table == "student_groups" and op.action == "insert":
            lecturer_id = _lookup_id(conn, "lecturers", "staff_number = ?", (row["staff_number"],))
            course_id = _lookup_id(conn, "courses", "course_code = ?", (row["course_code"],))
            conn.execute(
                convert_placeholders("INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active) VALUES (?, ?, ?, ?, ?, ?)"),
                (row["group_name"], course_id, lecturer_id, row["campus"], row["study_mode"], row["active"]),
            )
        elif table == "timetable_entries" and op.action == "insert":
            lecturer_id = _lookup_id(conn, "lecturers", "staff_number = ?", (row["staff_number"],))
            group_id = _lookup_group_id(conn, row)
            conn.execute(
                convert_placeholders(
                    """
                    INSERT INTO timetable_entries (
                        lecturer_id, group_id, day_of_week, start_time, end_time,
                        effective_start_date, effective_end_date, active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    lecturer_id,
                    group_id,
                    row["day_of_week"],
                    row["start_time"],
                    row["end_time"],
                    row["effective_start_date"],
                    row["effective_end_date"],
                    row["active"],
                ),
            )
        elif table == "group_enrolments" and op.action == "insert":
            student_id = _lookup_id(conn, "students", "student_number = ?", (row["student_number"],))
            group_id = _lookup_group_id(conn, row)
            conn.execute(
                convert_placeholders("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, ?)"),
                (student_id, group_id, row["active"]),
            )
        elif table == "academic_calendar" and op.action == "insert":
            lecturer_id = _lookup_id(conn, "lecturers", "staff_number = ?", (row["staff_number"],)) if row.get("staff_number") else None
            course_id = _lookup_id(conn, "courses", "course_code = ?", (row["course_code"],)) if row.get("course_code") else None
            group_id = _lookup_group_id(conn, row) if row.get("staff_number") and row.get("course_code") and row.get("group_name") else None
            conn.execute(
                convert_placeholders(
                    """
                    INSERT INTO academic_calendar (
                        title, start_date, end_date, calendar_type, action, allow_override,
                        start_time, end_time, scope_type, lecturer_id, course_id, group_id,
                        exclude_from_claims_and_registers, notes, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                tuple(row.get(field) for field in ["title", "start_date", "end_date", "calendar_type", "action", "allow_override", "start_time", "end_time", "scope_type"])
                + (
                    lecturer_id,
                    course_id,
                    group_id,
                    row.get("exclude_from_claims_and_registers"),
                    row.get("notes"),
                    row.get("active"),
                    row.get("created_at"),
                    row.get("updated_at"),
                ),
            )
        elif op.action == "update":
            if table == "lecturers":
                row_id = _lookup_id(conn, "lecturers", "staff_number = ?", (row["staff_number"],))
            elif table == "courses":
                row_id = _lookup_id(conn, "courses", "course_code = ?", (row["course_code"],))
            elif table == "students":
                row_id = _lookup_id(conn, "students", "student_number = ?", (row["student_number"],))
            elif table == "student_groups":
                row_id = _lookup_group_id(conn, row)
            elif table == "timetable_entries":
                row_id = _lookup_id(
                    conn,
                    "timetable_entries",
                    """
                    lecturer_id = (SELECT id FROM lecturers WHERE staff_number = ?)
                    AND group_id = ? AND day_of_week = ? AND start_time = ? AND end_time = ?
                    AND effective_start_date = ? AND effective_end_date = ?
                    """,
                    (
                        row["staff_number"],
                        _lookup_group_id(conn, row),
                        row["day_of_week"],
                        row["start_time"],
                        row["end_time"],
                        row["effective_start_date"],
                        row["effective_end_date"],
                    ),
                )
            elif table == "group_enrolments":
                row_id = _lookup_id(
                    conn,
                    "group_enrolments",
                    "student_id = (SELECT id FROM students WHERE student_number = ?) AND group_id = ?",
                    (row["student_number"], _lookup_group_id(conn, row)),
                )
            elif table == "academic_calendar":
                row_id = _lookup_id(conn, "academic_calendar", "title = ? AND start_date = ? AND end_date = ?", (row["title"], row["start_date"], row["end_date"]))
            else:
                raise RuntimeError(f"Unsupported update table: {table}")
            _update_by_id(conn, table, row_id, {field_name: row.get(field_name) for field_name in op.fields})
        else:
            raise RuntimeError(f"Unsupported sync operation: {op.action} on {table}.")


def apply_sync_plan(local_conn: Any, production_conn: Any, plan: dict[str, Any]) -> dict[str, Any]:
    if plan["blockers"]:
        raise RuntimeError("Cannot apply sync while blockers exist.")
    local_by_table = {table: {natural_key(table, row): row for row in fetch_records(local_conn, table)} for table in plan["tables_included"]}
    try:
        for table_plan in plan["plans"]:
            table = table_plan["table"]
            ops = [Operation(item["action"], table, item["key"], item["identifier"], item.get("fields", {}), item.get("reason", "")) for item in table_plan["records"]["inserts"]]
            ops.extend(Operation(item["action"], table, item["key"], item["identifier"], item.get("fields", {}), item.get("reason", "")) for item in table_plan["records"]["updates"])
            _apply_table(production_conn, table, ops, local_by_table[table])
        if hasattr(production_conn, "commit"):
            production_conn.commit()
    except Exception:
        if hasattr(production_conn, "rollback"):
            production_conn.rollback()
        raise
    return {"applied": True}


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "Local-First Sync Report",
        "=======================",
        f"Provider mode: {report['provider']}",
        f"Local SQLite path: {report['local_sqlite_path']}",
        f"Production target present: {'yes' if report['production_target_present'] else 'no'}",
        f"Tables included: {', '.join(report['tables_included'])}",
        f"Excluded tables: {', '.join(report['excluded_tables'])}",
        "",
        "Plan:",
    ]
    for plan in report["plans"]:
        lines.append(
            f"- {plan['table']}: inserts={plan['inserts']} updates={plan['updates']} skipped={plan['skipped']} conflicts={plan['conflicts']}"
        )
        for warning in plan["warnings"]:
            lines.append(f"  WARN: {warning}")
        for item in plan["records"]["inserts"][:5]:
            lines.append(f"  INSERT {item['identifier']}")
        for item in plan["records"]["updates"][:5]:
            lines.append(f"  UPDATE {item['identifier']}")
        for item in plan["records"]["conflicts"][:5]:
            lines.append(f"  CONFLICT {item['identifier']}: {item['reason']}")
    if report["blockers"]:
        lines.append("")
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    lines.append("Secrets printed: no")
    return "\n".join(lines)


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    tables = parse_tables(args.tables)
    with open_sqlite(DB_PATH) as local_conn:
        if args.summary:
            production_counts = {}
            if database_provider() == "postgresql" and database_url():
                with get_runtime_connection() as prod_conn:
                    production_counts = table_counts(prod_conn, tables)
            return {
                "provider": database_provider(),
                "local_sqlite_path": str(DB_PATH),
                "production_target_present": bool(database_url()),
                "tables_included": tables,
                "excluded_tables": EXCLUDED_TABLES,
                "local_counts": table_counts(local_conn, tables),
                "production_counts": production_counts,
                "plans": [],
                "blockers": [],
                "warnings": [],
                "secrets_printed": False,
            }
        prod_conn = None
        if database_provider() == "postgresql" and database_url():
            with get_runtime_connection() as conn:
                return build_sync_plan(local_conn, conn, tables)
        return build_sync_plan(local_conn, prod_conn, tables)


def run_apply(args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise PermissionError("Write mode requires --yes.")
    if not args.backup_acknowledged:
        raise PermissionError("Write mode requires --backup-acknowledged.")
    if args.confirm_sync != CONFIRMATION_PHRASE:
        raise PermissionError("Write mode requires the exact --confirm-sync phrase.")
    if database_provider() != "postgresql" or not database_url():
        raise RuntimeError("Write mode requires DATABASE_URL configured for PostgreSQL.")
    tables = parse_tables(args.tables)
    with open_sqlite(DB_PATH) as local_conn:
        with get_runtime_connection() as prod_conn:
            plan = build_sync_plan(local_conn, prod_conn, tables)
            result = apply_sync_plan(local_conn, prod_conn, plan)
    return {**plan, "write_result": result}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and apply guarded local SQLite to production PostgreSQL sync.")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--backup-acknowledged", action="store_true")
    parser.add_argument("--confirm-sync", default="")
    parser.add_argument("--tables", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.yes:
            report = run_apply(args)
        else:
            report = command_report(args)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            print(render_text_report(report))
        return 0 if not report.get("blockers") else 2
    except Exception as exc:
        print(f"Local-first sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
