import argparse
from datetime import date

import pandas as pd

from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, rows_to_dicts
from app.session_generator import month_bounds


def _print_df(df: pd.DataFrame) -> None:
    if df.empty:
        print("No records found.")
    else:
        print(df.to_string(index=False))


def _mask(value: str) -> str:
    text = "" if value is None else str(value)
    if len(text) <= 4:
        return "****" if text else ""
    return f"{text[:2]}{'*' * max(len(text) - 4, 4)}{text[-2:]}"


def summary_df() -> pd.DataFrame:
    init_runtime_db()
    tables = {
        "lecturers": "lecturers",
        "courses": "courses",
        "groups": "student_groups",
        "students": "students",
        "group_enrolments": "group_enrolments",
        "timetable_entries": "timetable_entries",
        "academic_calendar": "academic_calendar",
    }
    with get_runtime_connection() as conn:
        rows = [
            {"table": label, "rows": conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]}
            for label, table in tables.items()
        ]
    return pd.DataFrame(rows)


def lecturers_df(show_sensitive: bool = False) -> pd.DataFrame:
    init_runtime_db()
    columns = """
        staff_number, title, full_name, campus, tariff_per_hour,
        contract_start_date, contract_end_date, active,
        id_or_passport_number, paye_number
    """
    with get_runtime_connection() as conn:
        rows = rows_to_dicts(conn.execute(f"SELECT {columns} FROM lecturers ORDER BY staff_number").fetchall())
    if not show_sensitive:
        for row in rows:
            row["id_or_passport_number"] = _mask(row["id_or_passport_number"])
            row["paye_number"] = _mask(row["paye_number"])
    return pd.DataFrame(rows)


def groups_df() -> pd.DataFrame:
    init_runtime_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT sg.group_name, c.course_code, sg.campus, sg.study_mode, sg.active
            FROM student_groups sg
            JOIN courses c ON c.id = sg.course_id
            ORDER BY c.course_code, sg.group_name
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def timetable_df(staff_number: str | None = None) -> pd.DataFrame:
    init_runtime_db()
    params = []
    where = ""
    if staff_number:
        where = "WHERE l.staff_number = ?"
        params.append(staff_number)
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                f"""
            SELECT l.staff_number, l.full_name, c.course_code, sg.group_name,
                   te.day_of_week, te.start_time, te.end_time,
                   te.effective_start_date, te.effective_end_date, te.active
            FROM timetable_entries te
            JOIN lecturers l ON l.id = te.lecturer_id
            JOIN student_groups sg ON sg.id = te.group_id
            JOIN courses c ON c.id = sg.course_id
            {where}
            ORDER BY l.staff_number, sg.group_name, te.day_of_week, te.start_time
            """
            ),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def calendar_df(year: int | None = None, month: int | None = None) -> pd.DataFrame:
    init_runtime_db()
    params = []
    where = ""
    if year and month:
        start, end = month_bounds(year, month)
        where = "WHERE date(start_date) <= date(?) AND date(end_date) >= date(?)"
        params = [end.isoformat(), start.isoformat()]
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                f"""
            SELECT title, start_date, end_date, calendar_type, action, allow_override
            FROM academic_calendar
            {where}
            ORDER BY start_date, title
            """
            ),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect pt_claims_system data.")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--lecturers", action="store_true")
    parser.add_argument("--groups", action="store_true")
    parser.add_argument("--timetable", action="store_true")
    parser.add_argument("--calendar", action="store_true")
    parser.add_argument("--staff-number")
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--show-sensitive", action="store_true")
    args = parser.parse_args()

    if args.summary:
        _print_df(summary_df())
    elif args.lecturers:
        _print_df(lecturers_df(args.show_sensitive))
    elif args.groups:
        _print_df(groups_df())
    elif args.timetable:
        _print_df(timetable_df(args.staff_number))
    elif args.calendar:
        _print_df(calendar_df(args.year, args.month))
    else:
        _print_df(summary_df())


if __name__ == "__main__":
    main()
