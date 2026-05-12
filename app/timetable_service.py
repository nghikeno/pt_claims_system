from __future__ import annotations

from typing import Any

import pandas as pd

from app.backup_database import backup_database
from app.data_validation import DAY_NAMES, parse_bool, parse_date_value, parse_time_value
from app.database import get_connection, init_db
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, rows_to_dicts


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_data(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "staff_number": _clean(data.get("staff_number")).replace(" ", ""),
        "group_id": int(data["group_id"]) if _clean(data.get("group_id")).isdigit() else None,
        "day_of_week": _clean(data.get("day_of_week")),
        "start_time": parse_time_value(data.get("start_time")),
        "end_time": parse_time_value(data.get("end_time")),
        "effective_start_date": parse_date_value(data.get("effective_start_date")),
        "effective_end_date": parse_date_value(data.get("effective_end_date")),
        "active": parse_bool(data.get("active", 1)),
    }


DELETE_TIMETABLE_CONFIRMATION_PHRASE = "DELETE TIMETABLE ENTRY"


def hard_delete_confirmation_valid(confirmed: bool, phrase: str) -> bool:
    return bool(confirmed and _clean(phrase) == DELETE_TIMETABLE_CONFIRMATION_PHRASE)


def list_groups_for_timetable(staff_number: str) -> pd.DataFrame:
    init_runtime_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                """
            SELECT g.id AS group_id, g.group_name, c.id AS course_id, c.course_code,
                   c.course_name, g.campus, g.study_mode, g.active
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND g.lecturer_id IS NOT NULL
            ORDER BY c.course_code, g.group_name
            """,
            ),
            (_clean(staff_number).replace(" ", ""),),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def _group_for_lecturer(staff_number: str, group_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT g.id AS group_id, g.group_name, g.lecturer_id, g.course_id,
                   l.id AS lecturer_id, l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, c.course_name
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND g.id = ? AND g.lecturer_id IS NOT NULL
            """,
            (_clean(staff_number).replace(" ", ""), int(group_id)),
        ).fetchone()
    return dict(row) if row else None


def list_timetable_entries(
    staff_number: str | None = None,
    course_code: str | None = None,
    group_id: int | None = None,
    active: bool | None = None,
) -> pd.DataFrame:
    init_runtime_db()
    where: list[str] = []
    params: list[Any] = []
    if staff_number:
        where.append("l.staff_number = ?")
        params.append(_clean(staff_number).replace(" ", ""))
    if course_code:
        where.append("c.course_code = ?")
        params.append(_clean(course_code).upper().replace(" ", ""))
    if group_id is not None:
        where.append("g.id = ?")
        params.append(int(group_id))
    if active is not None:
        where.append("t.active = ?")
        params.append(1 if active else 0)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                f"""
            SELECT t.id, l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, c.course_name, g.id AS group_id, g.group_name,
                   t.day_of_week, t.start_time, t.end_time,
                   t.effective_start_date, t.effective_end_date, t.active
            FROM timetable_entries AS t
            JOIN lecturers AS l ON l.id = t.lecturer_id
            JOIN student_groups AS g ON g.id = t.group_id
            JOIN courses AS c ON c.id = g.course_id
            {where_sql}
            ORDER BY l.staff_number, c.course_code, g.group_name, t.day_of_week, t.start_time
            """,
            ),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def list_timetable_entries_for_lecturer(staff_number: str) -> pd.DataFrame:
    return list_timetable_entries(staff_number=staff_number)


def _duplicate_exists(cleaned: dict[str, Any], exclude_id: int | None = None) -> bool:
    group = _group_for_lecturer(cleaned["staff_number"], cleaned["group_id"])
    if not group:
        return False
    params: list[Any] = [
        int(group["lecturer_id"]),
        cleaned["group_id"],
        cleaned["day_of_week"],
        cleaned["start_time"],
        cleaned["end_time"],
        cleaned["effective_start_date"],
        cleaned["effective_end_date"],
    ]
    exclude_sql = ""
    if exclude_id is not None:
        exclude_sql = "AND id <> ?"
        params.append(int(exclude_id))
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT 1
            FROM timetable_entries
            WHERE lecturer_id = ? AND group_id = ? AND day_of_week = ?
              AND start_time = ? AND end_time = ?
              AND effective_start_date = ? AND effective_end_date = ?
              AND active = 1
              {exclude_sql}
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    return row is not None


def detect_timetable_overlaps(data: dict[str, Any], exclude_id: int | None = None) -> pd.DataFrame:
    cleaned = _normalise_data(data)
    if any(
        cleaned[key] in (None, "")
        for key in ("staff_number", "group_id", "day_of_week", "start_time", "end_time", "effective_start_date", "effective_end_date")
    ):
        return pd.DataFrame()
    group = _group_for_lecturer(cleaned["staff_number"], cleaned["group_id"])
    if not group:
        return pd.DataFrame()
    params: list[Any] = [
        int(group["lecturer_id"]),
        cleaned["group_id"],
        cleaned["day_of_week"],
        cleaned["effective_end_date"],
        cleaned["effective_start_date"],
        cleaned["end_time"],
        cleaned["start_time"],
    ]
    exclude_sql = ""
    if exclude_id is not None:
        exclude_sql = "AND t.id <> ?"
        params.append(int(exclude_id))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, g.group_name, t.day_of_week,
                   t.start_time, t.end_time, t.effective_start_date, t.effective_end_date,
                   CASE WHEN t.lecturer_id = ? THEN 'lecturer' ELSE 'group' END AS overlap_scope
            FROM timetable_entries AS t
            JOIN lecturers AS l ON l.id = t.lecturer_id
            JOIN student_groups AS g ON g.id = t.group_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE (t.lecturer_id = ? OR t.group_id = ?)
              AND t.active = 1
              AND t.day_of_week = ?
              AND t.effective_start_date <= ?
              AND t.effective_end_date >= ?
              AND t.start_time < ?
              AND t.end_time > ?
              {exclude_sql}
            ORDER BY t.id
            """,
            (int(group["lecturer_id"]), *params),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def validate_timetable_entry(data: dict[str, Any], exclude_id: int | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    cleaned = _normalise_data(data)
    if not cleaned["staff_number"]:
        errors.append("Lecturer must be selected.")
    if cleaned["group_id"] is None:
        errors.append("Group must be selected.")
    elif cleaned["staff_number"] and _group_for_lecturer(cleaned["staff_number"], cleaned["group_id"]) is None:
        errors.append("Group must belong to the selected lecturer.")
    if cleaned["day_of_week"] not in DAY_NAMES:
        errors.append("Day of week must be valid.")
    if cleaned["start_time"] is None:
        errors.append("Start time must be a valid HH:MM time.")
    if cleaned["end_time"] is None:
        errors.append("End time must be a valid HH:MM time.")
    if cleaned["start_time"] and cleaned["end_time"] and cleaned["start_time"] >= cleaned["end_time"]:
        errors.append("Start time must be before end time.")
    if cleaned["effective_start_date"] is None:
        errors.append("Effective start date must be valid.")
    if cleaned["effective_end_date"] is None:
        errors.append("Effective end date must be valid.")
    if (
        cleaned["effective_start_date"]
        and cleaned["effective_end_date"]
        and cleaned["effective_start_date"] > cleaned["effective_end_date"]
    ):
        errors.append("Effective start date must be before or equal to effective end date.")
    if cleaned["active"] is None:
        errors.append("Active must be true/false, yes/no, or 1/0.")
    if not errors and cleaned["active"] == 1 and _duplicate_exists(cleaned, exclude_id=exclude_id):
        errors.append("Duplicate timetable entry already exists.")
    if not errors and cleaned["active"] == 1 and not detect_timetable_overlaps(data, exclude_id=exclude_id).empty:
        errors.append("Overlapping timetable entry exists for this lecturer or group.")
    return len(errors) == 0, errors


def create_timetable_entry(data: dict[str, Any]) -> dict:
    is_valid, errors = validate_timetable_entry(data)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_data(data)
    group = _group_for_lecturer(cleaned["staff_number"], cleaned["group_id"])
    backup_database(prefix="pt_claims_before_timetable_save")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(group["lecturer_id"]),
                cleaned["group_id"],
                cleaned["day_of_week"],
                cleaned["start_time"],
                cleaned["end_time"],
                cleaned["effective_start_date"],
                cleaned["effective_end_date"],
                cleaned["active"],
            ),
        )
        entry_id = cursor.lastrowid
    return get_timetable_entry(entry_id)


def get_timetable_entry(entry_id: int) -> dict:
    rows = list_timetable_entries()
    match = rows[rows["id"] == int(entry_id)] if not rows.empty else pd.DataFrame()
    if match.empty:
        raise ValueError("Timetable entry could not be loaded.")
    return match.iloc[0].to_dict()


def update_timetable_entry(entry_id: int, data: dict[str, Any]) -> dict:
    is_valid, errors = validate_timetable_entry(data, exclude_id=entry_id)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_data(data)
    group = _group_for_lecturer(cleaned["staff_number"], cleaned["group_id"])
    backup_database(prefix="pt_claims_before_timetable_update")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE timetable_entries
            SET lecturer_id = ?, group_id = ?, day_of_week = ?, start_time = ?, end_time = ?,
                effective_start_date = ?, effective_end_date = ?, active = ?
            WHERE id = ?
            """,
            (
                int(group["lecturer_id"]),
                cleaned["group_id"],
                cleaned["day_of_week"],
                cleaned["start_time"],
                cleaned["end_time"],
                cleaned["effective_start_date"],
                cleaned["effective_end_date"],
                cleaned["active"],
                int(entry_id),
            ),
        )
    return get_timetable_entry(entry_id)


def deactivate_timetable_entry(entry_id: int) -> dict:
    current = get_timetable_entry(entry_id)
    backup_database(prefix="pt_claims_before_timetable_deactivate")
    with get_connection() as conn:
        conn.execute("UPDATE timetable_entries SET active = 0 WHERE id = ?", (int(entry_id),))
    return get_timetable_entry(entry_id)


def reactivate_timetable_entry(entry_id: int) -> dict:
    current = get_timetable_entry(entry_id)
    data = {
        "staff_number": current["staff_number"],
        "group_id": current["group_id"],
        "day_of_week": current["day_of_week"],
        "start_time": current["start_time"],
        "end_time": current["end_time"],
        "effective_start_date": current["effective_start_date"],
        "effective_end_date": current["effective_end_date"],
        "active": True,
    }
    is_valid, errors = validate_timetable_entry(data, exclude_id=int(entry_id))
    if not is_valid:
        raise ValueError("; ".join(errors))
    backup_database(prefix="pt_claims_before_timetable_reactivate")
    with get_connection() as conn:
        conn.execute("UPDATE timetable_entries SET active = 1 WHERE id = ?", (int(entry_id),))
    return get_timetable_entry(entry_id)


def delete_timetable_entry(entry_id: int) -> None:
    get_timetable_entry(entry_id)
    backup_database(prefix="pt_claims_before_timetable_delete")
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries WHERE id = ?", (int(entry_id),))
