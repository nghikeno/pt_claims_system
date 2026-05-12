import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from app.data_validation import (
    clean_text,
    parse_bool,
    parse_date_value,
    parse_positive_float,
    parse_time_value,
    validate_workbook,
)
from app.database import get_connection, init_db
from app.master_data_template import DATA_SHEETS, SAMPLE_ROWS, SHEET_COLUMNS, TEMPLATE_PATH


SUMMARY_KEYS = (
    "lecturers",
    "courses",
    "groups",
    "students",
    "enrolments",
    "timetable entries",
    "academic calendar rows",
)


def read_workbook(path: str | Path) -> dict[str, pd.DataFrame]:
    workbook = pd.read_excel(path, sheet_name=None, dtype=object)
    return {sheet: df.where(pd.notna(df), "") for sheet, df in workbook.items()}


def rows_read_per_sheet(workbook: dict[str, pd.DataFrame]) -> dict[str, int]:
    return {sheet: len(df) for sheet, df in workbook.items()}


def database_has_records() -> bool:
    init_db()
    tables = ("lecturers", "courses", "student_groups", "students", "timetable_entries", "academic_calendar")
    with get_connection() as conn:
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            if count:
                return True
    return False


def workbook_looks_like_sample_template(file_path: str | Path, workbook: dict[str, pd.DataFrame]) -> bool:
    path = Path(file_path).resolve()
    template_dir = TEMPLATE_PATH.parent.resolve()
    try:
        in_template_dir = template_dir in path.parents or path == TEMPLATE_PATH.resolve()
    except OSError:
        in_template_dir = False
    if not in_template_dir:
        return False
    for sheet_name, sample_rows in SAMPLE_ROWS.items():
        if sheet_name not in workbook:
            return False
        current = workbook[sheet_name].head(len(sample_rows)).astype(str).to_dict("records")
        expected = pd.DataFrame(sample_rows, columns=SHEET_COLUMNS[sheet_name]).astype(str).to_dict("records")
        if current != expected:
            return False
    return True


def _lookup_id(conn, query: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise ValueError(f"Lookup failed for query: {query}")
    return int(row["id"])


def _upsert(conn, select_sql: str, select_params: tuple, insert_sql: str, insert_params: tuple, update_sql: str, update_params: tuple) -> str:
    exists = conn.execute(select_sql, select_params).fetchone()
    if exists is None:
        conn.execute(insert_sql, insert_params)
        return "inserted"
    conn.execute(update_sql, update_params)
    return "updated"


def empty_summary() -> dict[str, dict[str, int]]:
    return {key: {"inserted": 0, "updated": 0, "skipped": 0} for key in SUMMARY_KEYS}


def import_master_data(file_path: str | Path, dry_run: bool = False) -> dict[str, dict[str, int]]:
    init_db()
    workbook = read_workbook(file_path)
    errors = validate_workbook(workbook)
    if errors:
        message = ["Import validation failed:"]
        message.extend(f"- {error.format()}" for error in errors)
        raise ValueError("\n".join(message))

    summary = empty_summary()
    with get_connection() as conn:
        conn.execute("BEGIN")
        try:
            _import_lecturers(conn, workbook["Lecturers"], summary)
            _import_courses(conn, workbook["Courses"], summary)
            _import_groups(conn, workbook["Groups"], summary)
            _import_students(conn, workbook["Students"], summary)
            _import_group_enrolments(conn, workbook["Group_Enrolments"], summary)
            _import_timetable(conn, workbook["Timetable"], summary)
            _import_academic_calendar(conn, workbook["Academic_Calendar"], summary)
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
    return summary


def _bump(summary: dict[str, dict[str, int]], key: str, result: str) -> None:
    summary[key][result] += 1


def _import_lecturers(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        values = (
            clean_text(row["staff_number"]),
            clean_text(row["title"]),
            clean_text(row["full_name"]),
            clean_text(row["highest_qualification"]),
            clean_text(row["id_or_passport_number"]),
            clean_text(row["paye_number"]),
            clean_text(row["physical_address"]),
            clean_text(row["contact_number"]),
            parse_positive_float(row["tariff_per_hour"]),
            clean_text(row["campus"]),
            parse_date_value(row["contract_start_date"]),
            parse_date_value(row["contract_end_date"]),
            parse_bool(row["active"]),
        )
        result = _upsert(
            conn,
            "SELECT id FROM lecturers WHERE staff_number = ?",
            (values[0],),
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
            """
            UPDATE lecturers
            SET title = ?, full_name = ?, highest_qualification = ?, id_or_passport_number = ?,
                paye_number = ?, physical_address = ?, contact_number = ?, tariff_per_hour = ?,
                campus = ?, contract_start_date = ?, contract_end_date = ?, active = ?
            WHERE staff_number = ?
            """,
            values[1:] + (values[0],),
        )
        _bump(summary, "lecturers", result)


def _import_courses(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        values = (
            clean_text(row["course_code"]),
            clean_text(row["course_name"]),
            clean_text(row["faculty"]),
            clean_text(row["department"]),
            clean_text(row["budget_allocation"]),
            parse_bool(row["active"]),
        )
        result = _upsert(
            conn,
            "SELECT id FROM courses WHERE course_code = ?",
            (values[0],),
            """
            INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
            """
            UPDATE courses
            SET course_name = ?, faculty = ?, department = ?, budget_allocation = ?, active = ?
            WHERE course_code = ?
            """,
            values[1:] + (values[0],),
        )
        _bump(summary, "courses", result)


def _course_id(conn, course_code: str) -> int:
    return _lookup_id(conn, "SELECT id FROM courses WHERE course_code = ?", (course_code,))


def _group_id(conn, group_name: str, course_code: str) -> int:
    return _lookup_id(
        conn,
        """
        SELECT sg.id
        FROM student_groups sg
        JOIN courses c ON c.id = sg.course_id
        WHERE sg.group_name = ? AND c.course_code = ?
        """,
        (group_name, course_code),
    )


def _import_groups(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        course_code = clean_text(row["course_code"])
        course_id = _course_id(conn, course_code)
        group_name = clean_text(row["group_name"])
        values = (
            group_name,
            course_id,
            clean_text(row["campus"]),
            clean_text(row["study_mode"]),
            parse_bool(row["active"]),
        )
        result = _upsert(
            conn,
            "SELECT id FROM student_groups WHERE group_name = ? AND course_id = ?",
            (group_name, course_id),
            """
            INSERT INTO student_groups (group_name, course_id, campus, study_mode, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            values,
            """
            UPDATE student_groups
            SET campus = ?, study_mode = ?, active = ?
            WHERE group_name = ? AND course_id = ?
            """,
            (values[2], values[3], values[4], group_name, course_id),
        )
        _bump(summary, "groups", result)


def _import_students(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        values = (
            clean_text(row["student_number"]),
            clean_text(row["surname"]),
            clean_text(row["initials"]),
            clean_text(row["full_name"]),
            parse_bool(row["active"]),
        )
        result = _upsert(
            conn,
            "SELECT id FROM students WHERE student_number = ?",
            (values[0],),
            """
            INSERT INTO students (student_number, surname, initials, full_name, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            values,
            """
            UPDATE students
            SET surname = ?, initials = ?, full_name = ?, active = ?
            WHERE student_number = ?
            """,
            values[1:] + (values[0],),
        )
        _bump(summary, "students", result)


def _student_id(conn, student_number: str) -> int:
    return _lookup_id(conn, "SELECT id FROM students WHERE student_number = ?", (student_number,))


def _import_group_enrolments(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        student_id = _student_id(conn, clean_text(row["student_number"]))
        group_id = _group_id(conn, clean_text(row["group_name"]), clean_text(row["course_code"]))
        active = parse_bool(row["active"])
        result = _upsert(
            conn,
            "SELECT id FROM group_enrolments WHERE student_id = ? AND group_id = ?",
            (student_id, group_id),
            """
            INSERT INTO group_enrolments (student_id, group_id, active)
            VALUES (?, ?, ?)
            """,
            (student_id, group_id, active),
            """
            UPDATE group_enrolments
            SET active = ?
            WHERE student_id = ? AND group_id = ?
            """,
            (active, student_id, group_id),
        )
        _bump(summary, "enrolments", result)


def _lecturer_id(conn, staff_number: str) -> int:
    return _lookup_id(conn, "SELECT id FROM lecturers WHERE staff_number = ?", (staff_number,))


def _import_timetable(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        lecturer_id = _lecturer_id(conn, clean_text(row["staff_number"]))
        group_id = _group_id(conn, clean_text(row["group_name"]), clean_text(row["course_code"]))
        day = clean_text(row["day_of_week"])
        start = parse_time_value(row["start_time"])
        end = parse_time_value(row["end_time"])
        effective_start = parse_date_value(row["effective_start_date"])
        effective_end = parse_date_value(row["effective_end_date"])
        active = parse_bool(row["active"])
        natural_key = (lecturer_id, group_id, day, start, end, effective_start, effective_end)
        result = _upsert(
            conn,
            """
            SELECT id FROM timetable_entries
            WHERE lecturer_id = ? AND group_id = ? AND day_of_week = ? AND start_time = ?
              AND end_time = ? AND effective_start_date = ? AND effective_end_date = ?
            """,
            natural_key,
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            natural_key + (active,),
            """
            UPDATE timetable_entries
            SET active = ?
            WHERE lecturer_id = ? AND group_id = ? AND day_of_week = ? AND start_time = ?
              AND end_time = ? AND effective_start_date = ? AND effective_end_date = ?
            """,
            (active,) + natural_key,
        )
        _bump(summary, "timetable entries", result)


def _import_academic_calendar(conn, df: pd.DataFrame, summary: dict[str, dict[str, int]]) -> None:
    for _, row in df.iterrows():
        title = clean_text(row["title"])
        start = parse_date_value(row["start_date"])
        end = parse_date_value(row["end_date"])
        calendar_type = clean_text(row["calendar_type"]).lower()
        action = clean_text(row["action"]).lower()
        allow_override = parse_bool(row["allow_override"])
        natural_key = (title, start, end)
        result = _upsert(
            conn,
            "SELECT id FROM academic_calendar WHERE title = ? AND start_date = ? AND end_date = ?",
            natural_key,
            """
            INSERT INTO academic_calendar (title, start_date, end_date, calendar_type, action, allow_override)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            natural_key + (calendar_type, action, allow_override),
            """
            UPDATE academic_calendar
            SET calendar_type = ?, action = ?, allow_override = ?
            WHERE title = ? AND start_date = ? AND end_date = ?
            """,
            (calendar_type, action, allow_override) + natural_key,
        )
        _bump(summary, "academic calendar rows", result)


def print_summary(summary: dict[str, dict[str, int]]) -> None:
    print("Import succeeded:")
    for key in SUMMARY_KEYS:
        counts = summary[key]
        print(f"- {key}: {counts['inserted']} inserted, {counts['updated']} updated, {counts['skipped']} skipped")


def print_import_report(
    workbook_path: str | Path,
    workbook: dict[str, pd.DataFrame],
    validation_status: str,
    write_mode: str,
    summary: dict[str, dict[str, int]] | None,
    error_count: int,
) -> None:
    print("Master Data Import Report")
    print(f"Workbook path: {Path(workbook_path)}")
    print(f"Sheets found: {', '.join(workbook.keys())}")
    print("Rows read per sheet:")
    for sheet, row_count in rows_read_per_sheet(workbook).items():
        print(f"- {sheet}: {row_count}")
    print(f"Validation status: {validation_status}")
    print(f"Database write mode: {write_mode}")
    if summary is None:
        summary = empty_summary()
    for key in SUMMARY_KEYS:
        counts = summary[key]
        print(f"- {key}: {counts['inserted']} inserted, {counts['updated']} updated, {counts['skipped']} skipped")
    print(f"Error count: {error_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import master data from an Excel workbook.")
    parser.add_argument("--file", required=True, help="Path to master data Excel workbook.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan import without writing to the database.")
    parser.add_argument("--yes", action="store_true", help="Confirm import when the database already contains records.")
    args = parser.parse_args()

    workbook = read_workbook(args.file)
    sample_warning = workbook_looks_like_sample_template(args.file, workbook)
    if sample_warning:
        print("WARNING: This workbook appears to be the sample dummy template in data/templates.")
        print("Replace sample rows with real approved master data before production import.")
    errors = validate_workbook(workbook)
    if errors:
        print_import_report(args.file, workbook, "FAILED", "Dry run" if args.dry_run else "Import", None, len(errors))
        print("Validation errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error.format()}", file=sys.stderr)
        sys.exit(1)
    print("Validation passed.")

    if args.dry_run:
        summary = import_master_data(args.file, dry_run=True)
        print_import_report(args.file, workbook, "PASSED", "Dry run", summary, 0)
        print("DRY RUN PASSED. No database changes were made.")
        sys.exit(0)

    if database_has_records() and not args.yes:
        response = input("Database already contains records. Continue with import? Type YES to continue: ")
        if response.strip() != "YES":
            print("Import cancelled. No database changes were made.")
            sys.exit(1)

    try:
        summary = import_master_data(args.file)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print_import_report(args.file, workbook, "PASSED", "Import", summary, 0)
    print_summary(summary)


if __name__ == "__main__":
    main()
