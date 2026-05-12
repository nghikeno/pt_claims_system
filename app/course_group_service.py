from __future__ import annotations

from typing import Any

import pandas as pd

from app.data_validation import parse_bool
from app.config import database_provider
from app.database import init_db
from app.db_provider import convert_placeholders, get_runtime_connection, row_to_dict, rows_to_dicts
from app.lecturer_service import lecturer_exists, reject_bank_detail_text


STUDY_MODE_OPTIONS = {"Full-time", "Part-time", "Extra-curricular", "Distance / Online"}
COURSE_COLUMNS = ["course_code", "course_name", "faculty", "department", "budget_allocation", "active"]
GROUP_COLUMNS = ["group_name", "course_code", "campus", "study_mode", "active"]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_course_code(value: Any) -> str:
    return _clean(value).upper().replace(" ", "")


def _normalise_course_data(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_code": _clean_course_code(data.get("course_code")),
        "course_name": _clean(data.get("course_name")),
        "faculty": _clean(data.get("faculty")),
        "department": _clean(data.get("department")),
        "budget_allocation": _clean(data.get("budget_allocation")),
        "active": parse_bool(data.get("active", 1)),
    }


def _normalise_group_data(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_name": _clean(data.get("group_name")),
        "course_code": _clean_course_code(data.get("course_code")),
        "campus": _clean(data.get("campus")),
        "study_mode": _clean(data.get("study_mode")),
        "active": parse_bool(data.get("active", 1)),
    }


def _ensure_local_schema() -> None:
    if database_provider() == "sqlite":
        init_db()


def _df_from_rows(rows: list[Any]) -> pd.DataFrame:
    return pd.DataFrame(rows_to_dicts(rows))


def list_courses() -> pd.DataFrame:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, course_code, course_name, faculty, department, budget_allocation, active
            FROM courses
            ORDER BY course_code
            """
        ).fetchall()
    return _df_from_rows(rows)


def get_course_by_code(course_code: str) -> dict | None:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT * FROM courses WHERE course_code = ?"),
            (_clean_course_code(course_code),),
        ).fetchone()
    return row_to_dict(row)


def course_exists(course_code: str) -> bool:
    return get_course_by_code(course_code) is not None


def validate_course_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = reject_bank_detail_text(data)
    cleaned = _normalise_course_data(data)
    if not cleaned["course_code"]:
        errors.append("Course code is required.")
    if not cleaned["course_name"]:
        errors.append("Course name is required.")
    if not cleaned["faculty"]:
        errors.append("Faculty is required.")
    if not cleaned["department"]:
        errors.append("Department is required.")
    if not cleaned["budget_allocation"]:
        errors.append("Budget allocation is required.")
    if cleaned["active"] is None:
        errors.append("Active must be true/false, yes/no, or 1/0.")
    return len(errors) == 0, errors


def create_course(data: dict[str, Any]) -> dict:
    is_valid, errors = validate_course_data(data)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_course_data(data)
    if course_exists(cleaned["course_code"]):
        raise ValueError("Course with this course code already exists. Use Update Course.")
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """),
            tuple(cleaned[column] for column in COURSE_COLUMNS),
        )
    return get_course_by_code(cleaned["course_code"])


def update_course(course_code: str, data: dict[str, Any]) -> dict:
    target_course_code = _clean_course_code(course_code)
    if not target_course_code or not course_exists(target_course_code):
        raise ValueError("Course with this course code does not exist.")
    data_for_validation = dict(data) | {"course_code": target_course_code}
    is_valid, errors = validate_course_data(data_for_validation)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_course_data(data_for_validation)
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            UPDATE courses
            SET course_name = ?, faculty = ?, department = ?, budget_allocation = ?, active = ?
            WHERE course_code = ?
            """),
            (
                cleaned["course_name"],
                cleaned["faculty"],
                cleaned["department"],
                cleaned["budget_allocation"],
                cleaned["active"],
                target_course_code,
            ),
        )
    return get_course_by_code(target_course_code)


def list_groups() -> pd.DataFrame:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT g.group_name, c.course_code, c.course_name, g.campus, g.study_mode, g.active
            FROM student_groups AS g
            JOIN courses AS c ON c.id = g.course_id
            WHERE g.lecturer_id IS NULL
            ORDER BY c.course_code, g.group_name
            """
        ).fetchall()
    return _df_from_rows(rows)


def get_group(group_name: str, course_code: str) -> dict | None:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("""
            SELECT g.*, c.course_code, c.course_name
            FROM student_groups AS g
            JOIN courses AS c ON c.id = g.course_id
            WHERE g.group_name = ? AND c.course_code = ? AND g.lecturer_id IS NULL
            """),
            (_clean(group_name), _clean_course_code(course_code)),
        ).fetchone()
    return row_to_dict(row)


def group_exists(group_name: str, course_code: str) -> bool:
    return get_group(group_name, course_code) is not None


def validate_group_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = reject_bank_detail_text(data)
    cleaned = _normalise_group_data(data)
    if not cleaned["group_name"]:
        errors.append("Group name is required.")
    if not cleaned["course_code"]:
        errors.append("Course code is required.")
    elif not course_exists(cleaned["course_code"]):
        errors.append("Course code must reference an existing course.")
    if not cleaned["campus"]:
        errors.append("Campus is required.")
    if cleaned["study_mode"] not in STUDY_MODE_OPTIONS:
        errors.append("Study mode must be one of Full-time, Part-time, Extra-curricular, or Distance / Online.")
    if cleaned["active"] is None:
        errors.append("Active must be true/false, yes/no, or 1/0.")
    return len(errors) == 0, errors


def _course_id_for_code(course_code: str) -> int:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT id FROM courses WHERE course_code = ?"),
            (_clean_course_code(course_code),),
        ).fetchone()
    if row is None:
        raise ValueError("Course code must reference an existing course.")
    return int((row_to_dict(row) or {})["id"])


def create_group(data: dict[str, Any]) -> dict:
    is_valid, errors = validate_group_data(data)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_group_data(data)
    if group_exists(cleaned["group_name"], cleaned["course_code"]):
        raise ValueError("Group with this name already exists for the selected course. Use Update Group.")
    course_id = _course_id_for_code(cleaned["course_code"])
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            INSERT INTO student_groups (group_name, course_id, campus, study_mode, active)
            VALUES (?, ?, ?, ?, ?)
            """),
            (cleaned["group_name"], course_id, cleaned["campus"], cleaned["study_mode"], cleaned["active"]),
        )
    return get_group(cleaned["group_name"], cleaned["course_code"])


def update_group(group_name: str, course_code: str, data: dict[str, Any]) -> dict:
    target_group_name = _clean(group_name)
    target_course_code = _clean_course_code(course_code)
    if not target_group_name or not target_course_code or not group_exists(target_group_name, target_course_code):
        raise ValueError("Group with this name and course code does not exist.")
    data_for_validation = dict(data) | {"group_name": target_group_name, "course_code": target_course_code}
    is_valid, errors = validate_group_data(data_for_validation)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_group_data(data_for_validation)
    course_id = _course_id_for_code(target_course_code)
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            UPDATE student_groups
            SET campus = ?, study_mode = ?, active = ?
            WHERE group_name = ? AND course_id = ?
            """),
            (
                cleaned["campus"],
                cleaned["study_mode"],
                cleaned["active"],
                target_group_name,
                course_id,
            ),
        )
    return get_group(target_group_name, target_course_code)


def find_duplicate_groups() -> pd.DataFrame:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.course_code, g.group_name, COUNT(*) AS count
            FROM student_groups AS g
            JOIN courses AS c ON c.id = g.course_id
            WHERE g.lecturer_id IS NULL
            GROUP BY c.course_code, g.group_name
            HAVING COUNT(*) > 1
            ORDER BY c.course_code, g.group_name
            """
        ).fetchall()
    return _df_from_rows(rows)


def _lecturer_id_for_staff_number(staff_number: str) -> int:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT id FROM lecturers WHERE staff_number = ?"),
            (_clean(staff_number).replace(" ", ""),),
        ).fetchone()
    if row is None:
        raise ValueError("Staff number must reference an existing lecturer.")
    return int((row_to_dict(row) or {})["id"])


def _normalise_lecturer_group_data(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = _normalise_group_data(data)
    cleaned["staff_number"] = _clean(data.get("staff_number")).replace(" ", "")
    return cleaned


def normalise_editable_group_name(group_name: Any) -> str:
    return _clean(group_name)


def validate_lecturer_group_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = reject_bank_detail_text(data)
    cleaned = _normalise_lecturer_group_data(data)
    if "group_label" in data and not _clean(data.get("group_label")):
        errors.append("Group label is required.")
    if "semester" in data and not _clean(data.get("semester")):
        errors.append("Semester is required.")
    if "year" in data:
        year = _clean(data.get("year"))
        if not year.isdigit() or len(year) != 4:
            errors.append("Year must be a valid four-digit year.")
    if not cleaned["staff_number"]:
        errors.append("Staff number is required.")
    elif not lecturer_exists(cleaned["staff_number"]):
        errors.append("Staff number must reference an existing lecturer.")
    if not cleaned["group_name"]:
        errors.append("Group name is required.")
    if not cleaned["course_code"]:
        errors.append("Course code is required.")
    elif not course_exists(cleaned["course_code"]):
        errors.append("Course code must reference an existing course.")
    if not cleaned["campus"]:
        errors.append("Campus is required.")
    if cleaned["study_mode"] not in STUDY_MODE_OPTIONS:
        errors.append("Study mode must be one of Full-time, Part-time, Extra-curricular, or Distance / Online.")
    if cleaned["active"] is None:
        errors.append("Active must be true/false, yes/no, or 1/0.")
    return len(errors) == 0, errors


def list_lecturer_groups(staff_number: str | None = None, course_code: str | None = None) -> pd.DataFrame:
    _ensure_local_schema()
    params: list[str] = []
    where = ["g.lecturer_id IS NOT NULL"]
    if staff_number:
        where.append("l.staff_number = ?")
        params.append(_clean(staff_number).replace(" ", ""))
    if course_code:
        where.append("c.course_code = ?")
        params.append(_clean_course_code(course_code))
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(f"""
            SELECT g.id AS group_id, l.staff_number, l.full_name AS lecturer_name, c.course_code, c.course_name,
                   g.group_name, g.campus, g.study_mode, g.active
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE {" AND ".join(where)}
            ORDER BY l.staff_number, c.course_code, g.group_name
            """),
            tuple(params),
        ).fetchall()
    return _df_from_rows(rows)


def list_groups_for_lecturer(staff_number: str) -> pd.DataFrame:
    columns = ["group_name", "course_code", "course_name", "campus", "study_mode", "active"]
    groups = list_lecturer_groups(staff_number=staff_number)
    if groups.empty:
        return pd.DataFrame(columns=columns)
    return groups[columns].copy()


def get_lecturer_group(staff_number: str, course_code: str, group_name: str) -> dict | None:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("""
            SELECT g.*, l.staff_number, l.full_name AS lecturer_name, c.course_code, c.course_name
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND c.course_code = ? AND g.group_name = ?
            """),
            (_clean(staff_number).replace(" ", ""), _clean_course_code(course_code), _clean(group_name)),
        ).fetchone()
    return row_to_dict(row)


def lecturer_group_exists(staff_number: str, course_code: str, group_name: str) -> bool:
    return get_lecturer_group(staff_number, course_code, group_name) is not None


def create_lecturer_group(data: dict[str, Any]) -> dict:
    is_valid, errors = validate_lecturer_group_data(data)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_lecturer_group_data(data)
    if lecturer_group_exists(cleaned["staff_number"], cleaned["course_code"], cleaned["group_name"]):
        raise ValueError("Group with this name already exists for the selected lecturer and course.")
    lecturer_id = _lecturer_id_for_staff_number(cleaned["staff_number"])
    course_id = _course_id_for_code(cleaned["course_code"])
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """),
            (
                cleaned["group_name"],
                course_id,
                lecturer_id,
                cleaned["campus"],
                cleaned["study_mode"],
                cleaned["active"],
            ),
        )
    return get_lecturer_group(cleaned["staff_number"], cleaned["course_code"], cleaned["group_name"])


def update_lecturer_group(staff_number: str, course_code: str, group_name: str, data: dict[str, Any]) -> dict:
    target_staff_number = _clean(staff_number).replace(" ", "")
    target_course_code = _clean_course_code(course_code)
    target_group_name = _clean(group_name)
    if not lecturer_group_exists(target_staff_number, target_course_code, target_group_name):
        raise ValueError("Group with this lecturer, course, and group name does not exist.")
    new_group_name = normalise_editable_group_name(data.get("group_name", target_group_name))
    data_for_validation = dict(data) | {
        "staff_number": target_staff_number,
        "course_code": target_course_code,
        "group_name": new_group_name,
    }
    is_valid, errors = validate_lecturer_group_data(data_for_validation)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_lecturer_group_data(data_for_validation)
    lecturer_id = _lecturer_id_for_staff_number(target_staff_number)
    course_id = _course_id_for_code(target_course_code)
    if cleaned["group_name"] != target_group_name and lecturer_group_exists(
        target_staff_number,
        target_course_code,
        cleaned["group_name"],
    ):
        raise ValueError("Group with this name already exists for the selected lecturer and course.")
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("""
            UPDATE student_groups
            SET group_name = ?, campus = ?, study_mode = ?, active = ?
            WHERE lecturer_id = ? AND course_id = ? AND group_name = ?
            """),
            (
                cleaned["group_name"],
                cleaned["campus"],
                cleaned["study_mode"],
                cleaned["active"],
                lecturer_id,
                course_id,
                target_group_name,
            ),
        )
    return get_lecturer_group(target_staff_number, target_course_code, cleaned["group_name"])


def find_duplicate_lecturer_groups() -> pd.DataFrame:
    _ensure_local_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.staff_number, c.course_code, g.group_name, COUNT(*) AS count
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            GROUP BY l.staff_number, c.course_code, g.group_name
            HAVING COUNT(*) > 1
            ORDER BY l.staff_number, c.course_code, g.group_name
            """
        ).fetchall()
    return _df_from_rows(rows)
