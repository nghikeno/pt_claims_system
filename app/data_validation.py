from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd

from app.database import get_connection
from app.master_data_template import SHEET_COLUMNS


DAY_NAMES = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
CALENDAR_TYPES = {"public_holiday", "recess", "institutional_closure", "special_event"}
CALENDAR_ACTIONS = {"include", "exclude"}
TRUE_VALUES = {"true", "t", "yes", "y", "1", "active"}
FALSE_VALUES = {"false", "f", "no", "n", "0", "inactive"}


@dataclass(frozen=True)
class ValidationError:
    sheet: str
    row: int
    column: str
    problem: str

    def format(self) -> str:
        return f"{self.sheet} row {self.row}, column '{self.column}': {self.problem}"


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def clean_text(value: Any) -> str:
    if is_blank(value):
        return ""
    return str(value).strip()


def parse_bool(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    text = clean_text(value).lower()
    if text in TRUE_VALUES:
        return 1
    if text in FALSE_VALUES:
        return 0
    return None


def parse_date_value(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_blank(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def parse_time_value(value: Any) -> str | None:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime):
        return value.time().strftime("%H:%M")
    if is_blank(value):
        return None
    text = clean_text(value)
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time().strftime("%H:%M")
        except ValueError:
            pass
    return None


def parse_positive_float(value: Any) -> float | None:
    if is_blank(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _row_number(index: int) -> int:
    return index + 2


def validate_required_columns(workbook: dict[str, pd.DataFrame]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for sheet_name, columns in SHEET_COLUMNS.items():
        if sheet_name not in workbook:
            errors.append(ValidationError(sheet_name, 1, "sheet", "Required sheet is missing"))
            continue
        actual_columns = set(workbook[sheet_name].columns)
        for column in columns:
            if column not in actual_columns:
                errors.append(ValidationError(sheet_name, 1, column, "Required column is missing"))
    return errors


def _add_required(errors: list[ValidationError], sheet: str, row: int, column: str, value: Any) -> None:
    if is_blank(value):
        errors.append(ValidationError(sheet, row, column, "Required value is blank"))


def _existing_lookup(conn, table: str, key_column: str) -> set[str]:
    return {row[key_column] for row in conn.execute(f"SELECT {key_column} FROM {table}").fetchall()}


def _group_keys_from_db(conn) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT sg.group_name, c.course_code
        FROM student_groups sg
        JOIN courses c ON c.id = sg.course_id
        """
    ).fetchall()
    return {(row["group_name"], row["course_code"]) for row in rows}


def validate_workbook(workbook: dict[str, pd.DataFrame], db_path: str | Path | None = None) -> list[ValidationError]:
    errors = validate_required_columns(workbook)
    if errors:
        return errors

    conn_args = (db_path,) if db_path is not None else ()
    with get_connection(*conn_args) as conn:
        course_codes = _existing_lookup(conn, "courses", "course_code")
        staff_numbers = _existing_lookup(conn, "lecturers", "staff_number")
        student_numbers = _existing_lookup(conn, "students", "student_number")
        group_keys = _group_keys_from_db(conn)

    imported_courses = {clean_text(row["course_code"]) for _, row in workbook["Courses"].iterrows() if clean_text(row["course_code"])}
    imported_lecturers = {clean_text(row["staff_number"]) for _, row in workbook["Lecturers"].iterrows() if clean_text(row["staff_number"])}
    imported_students = {clean_text(row["student_number"]) for _, row in workbook["Students"].iterrows() if clean_text(row["student_number"])}
    imported_groups = {
        (clean_text(row["group_name"]), clean_text(row["course_code"]))
        for _, row in workbook["Groups"].iterrows()
        if clean_text(row["group_name"]) and clean_text(row["course_code"])
    }

    available_courses = course_codes | imported_courses
    available_lecturers = staff_numbers | imported_lecturers
    available_students = student_numbers | imported_students
    available_groups = group_keys | imported_groups

    _validate_lecturers(workbook["Lecturers"], errors)
    _validate_courses(workbook["Courses"], errors)
    _validate_groups(workbook["Groups"], available_courses, errors)
    _validate_students(workbook["Students"], errors)
    _validate_group_enrolments(workbook["Group_Enrolments"], available_students, available_groups, errors)
    _validate_timetable(workbook["Timetable"], available_lecturers, available_groups, errors)
    _validate_academic_calendar(workbook["Academic_Calendar"], errors)
    return errors


def _validate_lecturers(df: pd.DataFrame, errors: list[ValidationError]) -> None:
    sheet = "Lecturers"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        _add_required(errors, sheet, row_no, "staff_number", row["staff_number"])
        _add_required(errors, sheet, row_no, "full_name", row["full_name"])
        if parse_positive_float(row["tariff_per_hour"]) is None:
            errors.append(ValidationError(sheet, row_no, "tariff_per_hour", "Must be numeric and greater than zero"))
        start = parse_date_value(row["contract_start_date"])
        end = parse_date_value(row["contract_end_date"])
        if start is None:
            errors.append(ValidationError(sheet, row_no, "contract_start_date", "Must be a valid date"))
        if end is None:
            errors.append(ValidationError(sheet, row_no, "contract_end_date", "Must be a valid date"))
        if start and end and end < start:
            errors.append(ValidationError(sheet, row_no, "contract_end_date", "Must not be earlier than contract_start_date"))
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_courses(df: pd.DataFrame, errors: list[ValidationError]) -> None:
    sheet = "Courses"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        _add_required(errors, sheet, row_no, "course_code", row["course_code"])
        _add_required(errors, sheet, row_no, "course_name", row["course_name"])
        _add_required(errors, sheet, row_no, "budget_allocation", row["budget_allocation"])
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_groups(df: pd.DataFrame, available_courses: set[str], errors: list[ValidationError]) -> None:
    sheet = "Groups"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        group_name = clean_text(row["group_name"])
        course_code = clean_text(row["course_code"])
        _add_required(errors, sheet, row_no, "group_name", group_name)
        _add_required(errors, sheet, row_no, "study_mode", row["study_mode"])
        if not course_code:
            errors.append(ValidationError(sheet, row_no, "course_code", "Required value is blank"))
        elif course_code not in available_courses:
            errors.append(ValidationError(sheet, row_no, "course_code", "Course code does not exist"))
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_students(df: pd.DataFrame, errors: list[ValidationError]) -> None:
    sheet = "Students"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        _add_required(errors, sheet, row_no, "student_number", row["student_number"])
        if is_blank(row["surname"]) and is_blank(row["full_name"]):
            errors.append(ValidationError(sheet, row_no, "surname", "Either surname or full_name is required"))
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_group_enrolments(
    df: pd.DataFrame,
    available_students: set[str],
    available_groups: set[tuple[str, str]],
    errors: list[ValidationError],
) -> None:
    sheet = "Group_Enrolments"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        student_number = clean_text(row["student_number"])
        group_key = (clean_text(row["group_name"]), clean_text(row["course_code"]))
        if not student_number:
            errors.append(ValidationError(sheet, row_no, "student_number", "Required value is blank"))
        elif student_number not in available_students:
            errors.append(ValidationError(sheet, row_no, "student_number", "Student number does not exist"))
        if not group_key[0]:
            errors.append(ValidationError(sheet, row_no, "group_name", "Required value is blank"))
        if not group_key[1]:
            errors.append(ValidationError(sheet, row_no, "course_code", "Required value is blank"))
        elif group_key not in available_groups:
            errors.append(ValidationError(sheet, row_no, "group_name", "Group and course combination does not exist"))
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_timetable(
    df: pd.DataFrame,
    available_lecturers: set[str],
    available_groups: set[tuple[str, str]],
    errors: list[ValidationError],
) -> None:
    sheet = "Timetable"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        staff_number = clean_text(row["staff_number"])
        group_key = (clean_text(row["group_name"]), clean_text(row["course_code"]))
        if not staff_number:
            errors.append(ValidationError(sheet, row_no, "staff_number", "Required value is blank"))
        elif staff_number not in available_lecturers:
            errors.append(ValidationError(sheet, row_no, "staff_number", "Staff number does not exist"))
        if group_key not in available_groups:
            errors.append(ValidationError(sheet, row_no, "group_name", "Group and course combination does not exist"))
        day = clean_text(row["day_of_week"])
        if day not in DAY_NAMES:
            errors.append(ValidationError(sheet, row_no, "day_of_week", "Must be a valid weekday name"))
        start = parse_time_value(row["start_time"])
        end = parse_time_value(row["end_time"])
        if start is None:
            errors.append(ValidationError(sheet, row_no, "start_time", "Must be a valid HH:MM time"))
        if end is None:
            errors.append(ValidationError(sheet, row_no, "end_time", "Must be a valid HH:MM time"))
        if start and end and end <= start:
            errors.append(ValidationError(sheet, row_no, "end_time", "Must be after start_time"))
        effective_start = parse_date_value(row["effective_start_date"])
        effective_end = parse_date_value(row["effective_end_date"])
        if effective_start is None:
            errors.append(ValidationError(sheet, row_no, "effective_start_date", "Must be a valid date"))
        if effective_end is None:
            errors.append(ValidationError(sheet, row_no, "effective_end_date", "Must be a valid date"))
        if effective_start and effective_end and effective_end < effective_start:
            errors.append(ValidationError(sheet, row_no, "effective_end_date", "Must not be earlier than effective_start_date"))
        if parse_bool(row["active"]) is None:
            errors.append(ValidationError(sheet, row_no, "active", "Must be true/false, yes/no, or 1/0"))


def _validate_academic_calendar(df: pd.DataFrame, errors: list[ValidationError]) -> None:
    sheet = "Academic_Calendar"
    for index, row in df.iterrows():
        row_no = _row_number(index)
        _add_required(errors, sheet, row_no, "title", row["title"])
        start = parse_date_value(row["start_date"])
        end = parse_date_value(row["end_date"])
        if start is None:
            errors.append(ValidationError(sheet, row_no, "start_date", "Must be a valid date"))
        if end is None:
            errors.append(ValidationError(sheet, row_no, "end_date", "Must be a valid date"))
        if start and end and end < start:
            errors.append(ValidationError(sheet, row_no, "end_date", "Must not be earlier than start_date"))
        if clean_text(row["action"]).lower() not in CALENDAR_ACTIONS:
            errors.append(ValidationError(sheet, row_no, "action", "Must be include or exclude"))
        if clean_text(row["calendar_type"]).lower() not in CALENDAR_TYPES:
            errors.append(ValidationError(sheet, row_no, "calendar_type", "Must be an allowed calendar type"))
        if parse_bool(row["allow_override"]) is None:
            errors.append(ValidationError(sheet, row_no, "allow_override", "Must be true/false, yes/no, or 1/0"))
