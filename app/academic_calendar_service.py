from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.audit_service import log_audit_event
from app.backup_database import backup_database
from app.config import database_provider
from app.data_validation import parse_bool, parse_date_value, parse_time_value
from app.db_provider import convert_placeholders, get_runtime_connection, row_to_dict, rows_to_dicts
from app.database import init_db
from app.validators import parse_date


CALENDAR_TYPES = [
    "Public Holiday",
    "Institutional Holiday",
    "Mid-Semester Break",
    "Mid-Year Recess",
    "Academic Recess",
    "Unexpected Class Cancellation",
    "Other",
]
SCOPE_TYPES = ["all", "lecturer", "course", "group"]


NUST_2026_REFERENCE_ITEMS = [
    {"title": "New Year's Day", "start_date": "2026-01-01", "end_date": "2026-01-01", "category": "Public Holiday"},
    {"title": "Semester 1 Exam Based Courses", "start_date": "2026-02-09", "end_date": "2026-05-13", "category": "Reference"},
    {"title": "Semester 1 CASS Courses", "start_date": "2026-02-09", "end_date": "2026-06-05", "category": "Reference"},
    {"title": "Independence Day", "start_date": "2026-03-21", "end_date": "2026-03-21", "category": "Public Holiday"},
    {"title": "Semester 1 Mid-Semester Break", "start_date": "2026-03-30", "end_date": "2026-04-02", "category": "Mid-Semester Break"},
    {"title": "Good Friday", "start_date": "2026-04-03", "end_date": "2026-04-03", "category": "Public Holiday"},
    {"title": "Easter Sunday", "start_date": "2026-04-05", "end_date": "2026-04-05", "category": "Public Holiday"},
    {"title": "Easter Monday", "start_date": "2026-04-06", "end_date": "2026-04-06", "category": "Public Holiday"},
    {"title": "Workers' Day", "start_date": "2026-05-01", "end_date": "2026-05-01", "category": "Public Holiday"},
    {"title": "Cassinga Day", "start_date": "2026-05-04", "end_date": "2026-05-04", "category": "Public Holiday"},
    {"title": "Ascension Day", "start_date": "2026-05-14", "end_date": "2026-05-14", "category": "Public Holiday"},
    {"title": "Africa Day", "start_date": "2026-05-25", "end_date": "2026-05-25", "category": "Public Holiday"},
    {"title": "Genocide Remembrance Day", "start_date": "2026-05-28", "end_date": "2026-05-28", "category": "Public Holiday"},
    {"title": "Institutional Holiday", "start_date": "2026-05-29", "end_date": "2026-05-29", "category": "Institutional Holiday"},
    {"title": "Mid-Year Recess for Students", "start_date": "2026-06-15", "end_date": "2026-07-10", "category": "Mid-Year Recess"},
    {"title": "Semester 2 Exam Based Courses", "start_date": "2026-07-13", "end_date": "2026-10-09", "category": "Reference"},
    {"title": "Semester 2 CASS Courses", "start_date": "2026-07-13", "end_date": "2026-11-06", "category": "Reference"},
    {"title": "Heroes' Day", "start_date": "2026-08-26", "end_date": "2026-08-26", "category": "Public Holiday"},
    {"title": "Semester 2 Mid-Semester Break", "start_date": "2026-09-07", "end_date": "2026-09-11", "category": "Mid-Semester Break"},
    {"title": "End of Academic Activities", "start_date": "2026-12-09", "end_date": "2026-12-09", "category": "Reference"},
    {"title": "Day of the Namibian Women and International Human Rights Day", "start_date": "2026-12-10", "end_date": "2026-12-10", "category": "Public Holiday"},
    {"title": "Christmas Day", "start_date": "2026-12-25", "end_date": "2026-12-25", "category": "Public Holiday"},
    {"title": "Family Day", "start_date": "2026-12-26", "end_date": "2026-12-26", "category": "Public Holiday"},
]


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_category(value: Any) -> str:
    text = _clean(value)
    return text if text in CALENDAR_TYPES else text.replace("_", " ").title()


def _calendar_type_slug(value: Any) -> str:
    return _normalise_category(value).lower().replace(" ", "_").replace("-", "_")


def _calendar_result(success: bool, stage: str, safe_message: str, **extra) -> dict[str, Any]:
    return {
        "success": success,
        "stage": stage,
        "safe_message": safe_message,
        "warnings": extra.pop("warnings", []),
        **extra,
    }


def _log_calendar_diagnostic(stage: str, exc: Exception) -> None:
    print(f"CALENDAR_WRITE_DIAGNOSTIC stage={stage} exception={type(exc).__name__}")


def ensure_academic_calendar_schema() -> None:
    if database_provider() == "sqlite":
        init_db()


def list_calendar_entries(active: bool | None = None, calendar_type: str | None = None) -> pd.DataFrame:
    ensure_academic_calendar_schema()
    where: list[str] = []
    params: list[Any] = []
    if active is not None:
        where.append("COALESCE(ac.active, 1) = ?")
        params.append(1 if active else 0)
    if calendar_type:
        where.append("lower(ac.calendar_type) = lower(?)")
        params.append(_calendar_type_slug(calendar_type))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(f"""
            SELECT
                ac.id AS id,
                ac.id AS calendar_id,
                ac.title AS title,
                ac.title AS calendar_title,
                ac.start_date AS start_date,
                ac.end_date AS end_date,
                ac.calendar_type AS calendar_type,
                ac.action AS action,
                ac.allow_override AS allow_override,
                ac.start_time AS start_time,
                ac.end_time AS end_time,
                ac.scope_type AS scope_type,
                ac.lecturer_id AS lecturer_id,
                ac.course_id AS course_id,
                ac.group_id AS group_id,
                ac.exclude_from_claims_and_registers AS exclude_from_claims_and_registers,
                ac.notes AS notes,
                COALESCE(ac.active, 1) AS active,
                COALESCE(ac.active, 1) AS calendar_active,
                ac.created_at AS created_at,
                ac.created_at AS calendar_created_at,
                ac.updated_at AS updated_at,
                ac.updated_at AS calendar_updated_at,
                l.staff_number AS staff_number,
                l.full_name AS lecturer_name,
                l.active AS lecturer_active,
                c.course_code AS course_code,
                c.course_name AS course_name,
                c.active AS course_active,
                sg.group_name AS group_name,
                sg.active AS group_active
            FROM academic_calendar AS ac
            LEFT JOIN student_groups AS sg ON sg.id = ac.group_id
            LEFT JOIN lecturers AS l ON l.id = COALESCE(ac.lecturer_id, sg.lecturer_id)
            LEFT JOIN courses AS c ON c.id = COALESCE(ac.course_id, sg.course_id)
            {where_sql}
            ORDER BY ac.start_date DESC, ac.start_time, ac.calendar_type, ac.id DESC
            """),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def calendar_summary_counts() -> pd.DataFrame:
    ensure_academic_calendar_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT ac.calendar_type AS calendar_type, COALESCE(ac.active, 1) AS active, COUNT(*) AS count
            FROM academic_calendar AS ac
            GROUP BY ac.calendar_type, COALESCE(ac.active, 1)
            ORDER BY ac.calendar_type, active DESC
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def get_calendar_entry(entry_id: int) -> dict | None:
    ensure_academic_calendar_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(convert_placeholders("SELECT ac.* FROM academic_calendar AS ac WHERE ac.id = ?"), (int(entry_id),)).fetchone()
    return row_to_dict(row)


def validate_calendar_data(data: dict[str, Any], exclude_id: int | None = None) -> tuple[bool, list[str]]:
    ensure_academic_calendar_schema()
    errors: list[str] = []
    title = _clean(data.get("title"))
    calendar_type = _normalise_category(data.get("calendar_type"))
    start_date = parse_date_value(data.get("start_date"))
    end_date = parse_date_value(data.get("end_date"))
    start_time = parse_time_value(data.get("start_time")) if _clean(data.get("start_time")) else ""
    end_time = parse_time_value(data.get("end_time")) if _clean(data.get("end_time")) else ""
    scope_type = _clean(data.get("scope_type") or "all").lower()
    if not title:
        errors.append("Title or description is required.")
    if calendar_type not in CALENDAR_TYPES:
        errors.append("Category/type is required.")
    if not start_date:
        errors.append("Start date is required.")
    if not end_date:
        errors.append("End date is required.")
    if start_date and end_date and parse_date(end_date) < parse_date(start_date):
        errors.append("End date must be on or after start date.")
    if bool(start_time) != bool(end_time):
        errors.append("Both start time and end time are required for a time-bound exclusion.")
    if start_time and end_time and start_time >= end_time:
        errors.append("End time must be after start time.")
    if scope_type not in SCOPE_TYPES:
        errors.append("Scope must be all, lecturer, course, or group.")
    with get_runtime_connection() as conn:
        if scope_type == "lecturer":
            if not data.get("lecturer_id"):
                errors.append("Lecturer scope requires a valid lecturer.")
            elif conn.execute(convert_placeholders("SELECT 1 FROM lecturers WHERE id = ?"), (int(data["lecturer_id"]),)).fetchone() is None:
                errors.append("Lecturer scope requires a valid lecturer.")
        if scope_type == "course":
            if not data.get("course_id"):
                errors.append("Course scope requires a valid course.")
            elif conn.execute(convert_placeholders("SELECT 1 FROM courses WHERE id = ?"), (int(data["course_id"]),)).fetchone() is None:
                errors.append("Course scope requires a valid course.")
        if scope_type == "group":
            if not data.get("group_id"):
                errors.append("Group scope requires a valid group.")
            elif conn.execute(convert_placeholders("SELECT 1 FROM student_groups WHERE id = ? AND lecturer_id IS NOT NULL"), (int(data["group_id"]),)).fetchone() is None:
                errors.append("Group scope requires a valid group.")
    if not errors:
        duplicate_params: list[Any] = [
            title,
            start_date,
            end_date,
            start_time or None,
            end_time or None,
            scope_type,
            int(data.get("lecturer_id") or 0),
            int(data.get("course_id") or 0),
            int(data.get("group_id") or 0),
        ]
        exclude_sql = ""
        if exclude_id is not None:
            exclude_sql = "AND ac.id <> ?"
            duplicate_params.append(int(exclude_id))
        with get_runtime_connection() as conn:
            row = conn.execute(
                convert_placeholders(f"""
                SELECT ac.id AS id FROM academic_calendar AS ac
                WHERE ac.title = ? AND ac.start_date = ? AND ac.end_date = ?
                  AND COALESCE(ac.start_time, '') = COALESCE(?, '')
                  AND COALESCE(ac.end_time, '') = COALESCE(?, '')
                  AND COALESCE(ac.scope_type, 'all') = ?
                  AND COALESCE(ac.lecturer_id, 0) = ?
                  AND COALESCE(ac.course_id, 0) = ?
                  AND COALESCE(ac.group_id, 0) = ?
                  AND COALESCE(ac.active, 1) = 1
                  {exclude_sql}
                LIMIT 1
                """),
                tuple(duplicate_params),
            ).fetchone()
        if row:
            errors.append("An active matching calendar exclusion already exists.")
    return not errors, errors


def _clean_payload(data: dict[str, Any]) -> dict[str, Any]:
    scope_type = _clean(data.get("scope_type") or "all").lower()
    return {
        "title": _clean(data.get("title")),
        "start_date": parse_date_value(data.get("start_date")),
        "end_date": parse_date_value(data.get("end_date")),
        "calendar_type": _calendar_type_slug(data.get("calendar_type")),
        "action": "exclude" if parse_bool(data.get("exclude_from_claims_and_registers", True)) else "include",
        "allow_override": 0,
        "start_time": parse_time_value(data.get("start_time")) if _clean(data.get("start_time")) else None,
        "end_time": parse_time_value(data.get("end_time")) if _clean(data.get("end_time")) else None,
        "scope_type": scope_type,
        "lecturer_id": int(data.get("lecturer_id")) if scope_type == "lecturer" and data.get("lecturer_id") else None,
        "course_id": int(data.get("course_id")) if scope_type == "course" and data.get("course_id") else None,
        "group_id": int(data.get("group_id")) if scope_type == "group" and data.get("group_id") else None,
        "exclude_from_claims_and_registers": 1 if parse_bool(data.get("exclude_from_claims_and_registers", True)) else 0,
        "notes": _clean(data.get("notes")),
        "active": 1 if parse_bool(data.get("active", True)) else 0,
    }


def _backup(prefix: str) -> dict[str, Any]:
    provider = database_provider()
    if provider != "sqlite":
        return {
            "performed": False,
            "mode": provider,
            "safe_message": "Production PostgreSQL mode: local SQLite backup skipped; provider backup/audit applies.",
            "path": None,
        }
    path = backup_database(prefix=prefix)
    return {
        "performed": True,
        "mode": provider,
        "safe_message": "Local SQLite backup created before calendar write.",
        "path": path,
    }


def _commit_if_supported(conn: Any) -> None:
    if hasattr(conn, "commit"):
        conn.commit()


def _audit_calendar_event(action: str, entry_id: int, title: str, user: dict | None = None) -> str | None:
    try:
        log_audit_event(
            action,
            user=user,
            entity_type="academic_calendar",
            entity_id=entry_id,
            details={"title": title},
        )
    except Exception as exc:
        _log_calendar_diagnostic("audit", exc)
        return "Audit logging did not complete, but the calendar change was saved."
    return None


def create_calendar_entry_result(data: dict[str, Any], user: dict | None = None) -> dict[str, Any]:
    is_valid, errors = validate_calendar_data(data)
    if not is_valid:
        return _calendar_result(False, "validation", "; ".join(errors))
    payload = _clean_payload(data)
    now = _now()
    try:
        backup_result = _backup("pt_claims_before_calendar_add")
    except Exception as exc:
        _log_calendar_diagnostic("backup", exc)
        return _calendar_result(False, "backup", "Calendar exclusion could not be saved during local backup.")
    try:
        insert_sql = """
            INSERT INTO academic_calendar (
                title, start_date, end_date, calendar_type, action, allow_override,
                start_time, end_time, scope_type, lecturer_id, course_id, group_id,
                exclude_from_claims_and_registers, notes, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if database_provider() != "sqlite":
            insert_sql += " RETURNING id"
        with get_runtime_connection() as conn:
            cur = conn.execute(
                convert_placeholders(insert_sql),
                (
                    payload["title"], payload["start_date"], payload["end_date"], payload["calendar_type"],
                    payload["action"], payload["allow_override"], payload["start_time"], payload["end_time"],
                    payload["scope_type"], payload["lecturer_id"], payload["course_id"], payload["group_id"],
                    payload["exclude_from_claims_and_registers"], payload["notes"], payload["active"], now, now,
                ),
            )
            if database_provider() == "sqlite":
                entry_id = int(cur.lastrowid)
            else:
                inserted = row_to_dict(cur.fetchone())
                entry_id = int(inserted["id"])
            _commit_if_supported(conn)
    except Exception as exc:
        _log_calendar_diagnostic("calendar_insert", exc)
        return _calendar_result(False, "calendar_insert", "Calendar exclusion could not be saved during calendar insert.")

    warnings: list[str] = []
    audit_warning = _audit_calendar_event("calendar_add", entry_id, payload["title"], user=user)
    if audit_warning:
        warnings.append(audit_warning)
    return _calendar_result(
        True,
        "complete",
        "Calendar exclusion saved.",
        entry_id=entry_id,
        backup_result=backup_result,
        warnings=warnings,
    )


def create_calendar_entry(data: dict[str, Any], user: dict | None = None) -> int:
    result = create_calendar_entry_result(data, user=user)
    if not result["success"]:
        raise ValueError(result["safe_message"])
    return int(result["entry_id"])


def update_calendar_entry_result(entry_id: int, data: dict[str, Any], user: dict | None = None) -> dict[str, Any]:
    if get_calendar_entry(entry_id) is None:
        return _calendar_result(False, "lookup", "Calendar entry not found.")
    is_valid, errors = validate_calendar_data(data, exclude_id=int(entry_id))
    if not is_valid:
        return _calendar_result(False, "validation", "; ".join(errors), entry_id=int(entry_id))
    payload = _clean_payload(data)
    try:
        backup_result = _backup("pt_claims_before_calendar_update")
    except Exception as exc:
        _log_calendar_diagnostic("backup", exc)
        return _calendar_result(False, "backup", "Calendar exclusion could not be updated during local backup.", entry_id=int(entry_id))
    try:
        with get_runtime_connection() as conn:
            conn.execute(
                convert_placeholders(
                    """
                    UPDATE academic_calendar
                    SET title = ?, start_date = ?, end_date = ?, calendar_type = ?, action = ?,
                        start_time = ?, end_time = ?, scope_type = ?, lecturer_id = ?, course_id = ?,
                        group_id = ?, exclude_from_claims_and_registers = ?, notes = ?, active = ?, updated_at = ?
                    WHERE id = ?
                    """
                ),
                (
                    payload["title"], payload["start_date"], payload["end_date"], payload["calendar_type"],
                    payload["action"], payload["start_time"], payload["end_time"], payload["scope_type"],
                    payload["lecturer_id"], payload["course_id"], payload["group_id"],
                    payload["exclude_from_claims_and_registers"], payload["notes"], payload["active"], _now(), int(entry_id),
                ),
            )
            _commit_if_supported(conn)
    except Exception as exc:
        _log_calendar_diagnostic("calendar_update", exc)
        return _calendar_result(False, "calendar_update", "Calendar exclusion could not be updated during calendar update.", entry_id=int(entry_id))
    warnings: list[str] = []
    audit_warning = _audit_calendar_event("calendar_update", int(entry_id), payload["title"], user=user)
    if audit_warning:
        warnings.append(audit_warning)
    return _calendar_result(
        True,
        "complete",
        "Calendar exclusion updated.",
        entry_id=int(entry_id),
        backup_result=backup_result,
        warnings=warnings,
    )


def update_calendar_entry(entry_id: int, data: dict[str, Any], user: dict | None = None) -> int:
    result = update_calendar_entry_result(entry_id, data, user=user)
    if not result["success"]:
        raise ValueError(result["safe_message"])
    return int(result["entry_id"])


def set_calendar_entry_active_result(entry_id: int, active: bool, user: dict | None = None) -> dict[str, Any]:
    current = get_calendar_entry(entry_id)
    if current is None:
        return _calendar_result(False, "lookup", "Calendar entry not found.", entry_id=int(entry_id))
    try:
        backup_result = _backup("pt_claims_before_calendar_reactivate" if active else "pt_claims_before_calendar_deactivate")
    except Exception as exc:
        _log_calendar_diagnostic("backup", exc)
        return _calendar_result(False, "backup", "Calendar exclusion status could not be changed during local backup.", entry_id=int(entry_id))
    try:
        with get_runtime_connection() as conn:
            conn.execute(
                convert_placeholders("UPDATE academic_calendar SET active = ?, updated_at = ? WHERE id = ?"),
                (1 if active else 0, _now(), int(entry_id)),
            )
            _commit_if_supported(conn)
    except Exception as exc:
        _log_calendar_diagnostic("calendar_status_update", exc)
        return _calendar_result(False, "calendar_status_update", "Calendar exclusion status could not be changed during calendar update.", entry_id=int(entry_id))
    action = "calendar_reactivate" if active else "calendar_deactivate"
    warnings: list[str] = []
    audit_warning = _audit_calendar_event(action, int(entry_id), str(current.get("title") or ""), user=user)
    if audit_warning:
        warnings.append(audit_warning)
    return _calendar_result(
        True,
        "complete",
        "Calendar exclusion reactivated." if active else "Calendar exclusion deactivated.",
        entry_id=int(entry_id),
        backup_result=backup_result,
        warnings=warnings,
    )


def set_calendar_entry_active(entry_id: int, active: bool, user: dict | None = None) -> None:
    result = set_calendar_entry_active_result(entry_id, active, user=user)
    if not result["success"]:
        raise ValueError(result["safe_message"])


def reference_calendar_df() -> pd.DataFrame:
    return pd.DataFrame(NUST_2026_REFERENCE_ITEMS)


def _time_ranges_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    return start_a < end_b and end_a > start_b


def calendar_exclusion_applies(row: dict[str, Any], session: dict[str, Any]) -> bool:
    active_value = row.get("active", 1)
    if int(active_value if active_value is not None else 1) != 1:
        return False
    if str(row.get("action", "")).lower() != "exclude":
        return False
    exclude_value = row.get("exclude_from_claims_and_registers", 1)
    if int(exclude_value if exclude_value is not None else 1) != 1:
        return False
    session_date = parse_date(session["session_date"])
    if not (parse_date(row["start_date"]) <= session_date <= parse_date(row["end_date"])):
        return False
    scope_type = _clean(row.get("scope_type") or "all").lower()
    if scope_type == "lecturer" and int(row.get("lecturer_id") or 0) != int(session.get("lecturer_id") or 0):
        return False
    if scope_type == "course" and int(row.get("course_id") or 0) != int(session.get("course_id") or 0):
        return False
    if scope_type == "group" and int(row.get("group_id") or 0) != int(session.get("group_id") or 0):
        return False
    start_time = _clean(row.get("start_time"))
    end_time = _clean(row.get("end_time"))
    if start_time or end_time:
        if not (start_time and end_time):
            return False
        return _time_ranges_overlap(start_time, end_time, session["start_time"], session["end_time"])
    return True


def fetch_calendar_exclusions_for_period(start_date: str, end_date: str) -> list[dict[str, Any]]:
    ensure_academic_calendar_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT ac.*
            FROM academic_calendar AS ac
            WHERE lower(ac.action) = 'exclude'
              AND COALESCE(ac.active, 1) = 1
              AND COALESCE(ac.exclude_from_claims_and_registers, 1) = 1
              AND date(ac.start_date) <= date(?)
              AND date(ac.end_date) >= date(?)
            """),
            (end_date, start_date),
        ).fetchall()
    return rows_to_dicts(rows)
