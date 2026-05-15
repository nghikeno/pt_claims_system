from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import csv

import pandas as pd

from app.backup_database import backup_database
from app.config import EXPORTS_DIR, database_provider
from app.database import init_db
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict, rows_to_dicts
from app.student_row_safety import suspicious_student_row_reason
from app.student_word_import import BANK_PATTERNS, ParsedAttendanceSheet, clean_text


def _clean(value: Any) -> str:
    return clean_text(value)


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    text = _clean(value).casefold()
    return 0 if text in {"0", "false", "no", "inactive"} else 1


def _bank_text_found(values: list[str]) -> bool:
    text = " ".join(values).casefold()
    return any(pattern in text for pattern in BANK_PATTERNS)


def _ensure_sqlite_schema() -> None:
    if database_provider() == "sqlite":
        init_db()


def _backup_if_sqlite(prefix: str) -> dict[str, Any]:
    provider = database_provider()
    if provider != "sqlite":
        return {
            "performed": False,
            "mode": provider,
            "safe_message": "Production PostgreSQL mode: local SQLite backup skipped; provider backup/audit applies.",
            "path": None,
        }
    return {
        "performed": True,
        "mode": provider,
        "safe_message": "Local SQLite backup created before student write.",
        "path": backup_database(prefix=prefix),
    }


def _commit(conn: Any) -> None:
    if hasattr(conn, "commit"):
        conn.commit()


def get_group_for_student_upload(staff_number: str, course_code: str, group_id: int) -> dict | None:
    _ensure_sqlite_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("""
            SELECT g.id AS group_id, g.group_name, g.lecturer_id, g.course_id, g.campus, g.study_mode,
                   l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, c.course_name
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND c.course_code = ? AND g.id = ? AND g.lecturer_id IS NOT NULL
            """),
            (_clean(staff_number).replace(" ", ""), _clean(course_code).upper().replace(" ", ""), int(group_id)),
        ).fetchone()
    return row_to_dict(row)


def list_student_enrolments(
    staff_number: str | None = None,
    course_code: str | None = None,
    group_id: int | None = None,
    active: bool | None = None,
) -> pd.DataFrame:
    init_runtime_db()
    where: list[str] = ["g.lecturer_id IS NOT NULL"]
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
        where.append("ge.active = ?")
        params.append(1 if active else 0)
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                f"""
            SELECT ge.id AS enrolment_id, l.staff_number, l.full_name AS lecturer_name,
                   c.course_code, c.course_name, g.id AS group_id, g.group_name,
                   s.student_number, s.surname, s.initials, s.full_name, ge.active
            FROM group_enrolments AS ge
            JOIN students AS s ON s.id = ge.student_id
            JOIN student_groups AS g ON g.id = ge.group_id
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE {" AND ".join(where)}
            ORDER BY l.staff_number, c.course_code, g.group_name, s.surname, s.initials, s.student_number
            """,
            ),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def validate_student_import(
    parsed: ParsedAttendanceSheet,
    staff_number: str,
    course_code: str,
    group_id: int | None,
    confirm_group_mapping: bool = False,
    allow_student_updates: bool = False,
) -> tuple[bool, list[str], list[str], list[dict[str, str]]]:
    errors: list[str] = []
    warnings: list[str] = list(parsed.warnings)
    skipped: list[dict[str, str]] = list(parsed.skipped_rows)

    if group_id is None:
        errors.append("Target group must be selected.")
        group = None
    else:
        group = get_group_for_student_upload(staff_number, course_code, int(group_id))
        if group is None:
            errors.append("Target group must exist, be lecturer-scoped, belong to the selected lecturer, and match the selected course.")

    word_course = _clean(parsed.header.get("course_code")).upper().replace(" ", "")
    if word_course and word_course != _clean(course_code).upper().replace(" ", ""):
        warnings.append(
            f"Word course code {word_course} does not match selected database course {course_code}. "
            "The selected database course will be used."
        )

    word_group = _clean(parsed.header.get("group_label"))
    if word_group and group and not confirm_group_mapping:
        errors.append("Confirm the Word GROUP value maps to the selected database group before import.")

    if _bank_text_found(list(parsed.header.values())):
        errors.append("Bank details must not be imported.")

    seen: set[str] = set()
    valid_students: list[dict[str, str]] = []
    for student in parsed.students:
        student_number = _clean(student.get("student_number"))
        surname = _clean(student.get("surname"))
        initials = _clean(student.get("initials"))
        full_name = _clean(student.get("full_name"))
        if _bank_text_found([student_number, surname, initials, full_name]):
            errors.append("Bank details must not be imported.")
            continue
        if not student_number:
            skipped.append({"row_text": str(student), "reason": "Student number is blank."})
            continue
        row_text = " ".join([student_number, surname, initials, full_name])
        suspicious_reason = suspicious_student_row_reason(student_number, surname, initials, full_name, row_text)
        if suspicious_reason:
            skipped.append({"row_text": str(student), "reason": suspicious_reason})
            continue
        if not surname:
            skipped.append({"row_text": str(student), "reason": "Surname is blank."})
            continue
        if not initials and not full_name:
            skipped.append({"row_text": str(student), "reason": "Initials are blank and full name is not available."})
            continue
        if student_number in seen:
            errors.append(f"Duplicate student number in uploaded file: {student_number}")
            continue
        seen.add(student_number)
        valid_students.append({
            "student_number": student_number,
            "surname": surname,
            "initials": initials,
            "full_name": full_name,
        })

    if not valid_students:
        errors.append("No valid student rows were found.")

    if valid_students:
        with get_runtime_connection() as conn:
            for student in valid_students:
                existing = conn.execute(
                    convert_placeholders("SELECT surname, initials, full_name FROM students WHERE student_number = ?"),
                    (student["student_number"],),
                ).fetchone()
                existing_row = row_to_dict(existing)
                if existing_row and (
                    _clean(existing_row["surname"]) != student["surname"]
                    or _clean(existing_row["initials"]) != student["initials"]
                ):
                    message = f"Student {student['student_number']} already exists with different name details."
                    if allow_student_updates:
                        warnings.append(message)
                    else:
                        errors.append(message + " Confirm updates before import.")

    return len(errors) == 0, errors, warnings, skipped


def _student_id(conn, student_number: str) -> int | None:
    row = conn.execute(convert_placeholders("SELECT id FROM students WHERE student_number = ?"), (student_number,)).fetchone()
    row_dict = row_to_dict(row)
    return int(row_dict["id"]) if row_dict else None


def import_students_for_group(
    parsed: ParsedAttendanceSheet,
    staff_number: str,
    course_code: str,
    group_id: int,
    confirm_group_mapping: bool = False,
    allow_student_updates: bool = False,
) -> dict[str, Any]:
    is_valid, errors, warnings, skipped = validate_student_import(
        parsed,
        staff_number,
        course_code,
        group_id,
        confirm_group_mapping=confirm_group_mapping,
        allow_student_updates=allow_student_updates,
    )
    if not is_valid:
        raise ValueError("; ".join(errors))

    group = get_group_for_student_upload(staff_number, course_code, group_id)
    backup_result = _backup_if_sqlite(prefix="pt_claims_before_student_import")
    summary = {
        "file_name": parsed.source_name,
        "target_lecturer": f"{group['staff_number']} - {group['lecturer_name']}",
        "target_course": f"{group['course_code']} - {group['course_name']}",
        "target_group": group["group_name"],
        "rows_parsed": len(parsed.students),
        "rows_valid": 0,
        "students_inserted": 0,
        "students_updated": 0,
        "enrolments_inserted": 0,
        "enrolments_reactivated": 0,
        "enrolments_already_existing": 0,
        "rows_skipped": len(skipped),
        "validation_warnings": warnings,
    }
    with get_runtime_connection() as conn:
        conn.execute("BEGIN")
        try:
            for student in parsed.students:
                student_number = _clean(student.get("student_number"))
                surname = _clean(student.get("surname"))
                initials = _clean(student.get("initials"))
                full_name = _clean(student.get("full_name"))
                row_text = " ".join([student_number, surname, initials, full_name])
                if suspicious_student_row_reason(student_number, surname, initials, full_name, row_text):
                    continue
                if not student_number or not surname or (not initials and not full_name):
                    continue
                summary["rows_valid"] += 1
                student_id = _student_id(conn, student_number)
                if student_id is None:
                    insert_sql = "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)"
                    if database_provider() != "sqlite":
                        insert_sql += " RETURNING id"
                    cursor = conn.execute(convert_placeholders(insert_sql), (student_number, surname, initials, full_name))
                    if database_provider() == "sqlite":
                        student_id = int(cursor.lastrowid)
                    else:
                        student_id = int(row_to_dict(cursor.fetchone())["id"])
                    summary["students_inserted"] += 1
                else:
                    existing = conn.execute(
                        convert_placeholders("SELECT surname, initials, full_name FROM students WHERE id = ?"),
                        (student_id,),
                    ).fetchone()
                    existing_row = row_to_dict(existing) or {}
                    if (
                        _clean(existing_row["surname"]) != surname
                        or _clean(existing_row["initials"]) != initials
                        or _clean(existing_row["full_name"]) != full_name
                    ):
                        conn.execute(
                            convert_placeholders("UPDATE students SET surname = ?, initials = ?, full_name = ?, active = 1 WHERE id = ?"),
                            (surname, initials, full_name, student_id),
                        )
                        summary["students_updated"] += 1
                enrolment = conn.execute(
                    convert_placeholders("SELECT id, active FROM group_enrolments WHERE student_id = ? AND group_id = ?"),
                    (student_id, int(group_id)),
                ).fetchone()
                enrolment_row = row_to_dict(enrolment)
                if enrolment_row is None:
                    conn.execute(
                        convert_placeholders("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)"),
                        (student_id, int(group_id)),
                    )
                    summary["enrolments_inserted"] += 1
                elif int(enrolment_row["active"]) == 0:
                    conn.execute(convert_placeholders("UPDATE group_enrolments SET active = 1 WHERE id = ?"), (int(enrolment_row["id"]),))
                    summary["enrolments_reactivated"] += 1
                else:
                    summary["enrolments_already_existing"] += 1
            _commit(conn)
        except Exception:
            conn.rollback()
            raise
    summary["backup"] = backup_result
    return summary


TEMPLATE_COLUMNS = [
    "staff_number",
    "course_code",
    "group_name",
    "student_number",
    "surname",
    "initials",
    "full_name",
    "active",
]


def import_student_template_file(path: str | Path, allow_student_updates: bool = False) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.casefold() == ".csv":
        df = pd.read_csv(source, dtype=str).fillna("")
    elif source.suffix.casefold() in {".xlsx", ".xls"}:
        df = pd.read_excel(source, dtype=str).fillna("")
    else:
        raise ValueError("Student template upload must be .csv or .xlsx.")
    missing = [column for column in TEMPLATE_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Student template is missing required columns: {', '.join(missing)}")
    if _bank_text_found([str(value) for value in df.columns] + [str(value) for value in df.astype(str).to_numpy().ravel()]):
        raise ValueError("Bank details must not be imported.")

    summaries: list[dict[str, Any]] = []
    for (staff_number, course_code, group_name), group_df in df.groupby(["staff_number", "course_code", "group_name"], sort=True):
        _ensure_sqlite_schema()
        with get_runtime_connection() as conn:
            row = conn.execute(
                convert_placeholders("""
                SELECT g.id
                FROM student_groups AS g
                JOIN lecturers AS l ON l.id = g.lecturer_id
                JOIN courses AS c ON c.id = g.course_id
                WHERE l.staff_number = ? AND c.course_code = ? AND g.group_name = ? AND g.lecturer_id IS NOT NULL
                """),
                (_clean(staff_number).replace(" ", ""), _clean(course_code).upper().replace(" ", ""), _clean(group_name)),
            ).fetchone()
        row_dict = row_to_dict(row)
        if row_dict is None:
            raise ValueError(f"No lecturer-scoped group found for {staff_number} / {course_code} / {group_name}.")
        parsed = ParsedAttendanceSheet(
            source_name=source.name,
            header={"course_code": _clean(course_code), "group_label": _clean(group_name)},
            students=[
                {
                    "student_number": _clean(record["student_number"]),
                    "surname": _clean(record["surname"]),
                    "initials": _clean(record["initials"]),
                    "full_name": _clean(record["full_name"]),
                }
                for record in group_df.to_dict("records")
                if _bool_int(record.get("active", 1)) == 1
            ],
        )
        summaries.append(
            import_students_for_group(
                parsed,
                _clean(staff_number),
                _clean(course_code),
                int(row_dict["id"]),
                confirm_group_mapping=True,
                allow_student_updates=allow_student_updates,
            )
        )
    return summaries


def deactivate_enrolment(enrolment_id: int) -> dict:
    get_enrolment(enrolment_id)
    _backup_if_sqlite(prefix="pt_claims_before_student_enrolment_update")
    with get_runtime_connection() as conn:
        conn.execute(convert_placeholders("UPDATE group_enrolments SET active = 0 WHERE id = ?"), (int(enrolment_id),))
        _commit(conn)
    return get_enrolment(enrolment_id)


def reactivate_enrolment(enrolment_id: int) -> dict:
    get_enrolment(enrolment_id)
    _backup_if_sqlite(prefix="pt_claims_before_student_enrolment_update")
    with get_runtime_connection() as conn:
        conn.execute(convert_placeholders("UPDATE group_enrolments SET active = 1 WHERE id = ?"), (int(enrolment_id),))
        _commit(conn)
    return get_enrolment(enrolment_id)


def get_enrolment(enrolment_id: int) -> dict:
    rows = list_student_enrolments()
    match = rows[rows["enrolment_id"] == int(enrolment_id)] if not rows.empty else pd.DataFrame()
    if match.empty:
        raise ValueError("Student enrolment could not be loaded.")
    return match.iloc[0].to_dict()


def export_student_enrolments_to_csv(path: str | Path | None = None) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(path) if path else EXPORTS_DIR / f"student_enrolments_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df = list_student_enrolments()
    columns = [
        "staff_number",
        "lecturer_name",
        "course_code",
        "group_name",
        "student_number",
        "surname",
        "initials",
        "full_name",
        "active",
    ]
    if df.empty:
        pd.DataFrame(columns=columns).to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    else:
        df[columns].to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    return output_path
