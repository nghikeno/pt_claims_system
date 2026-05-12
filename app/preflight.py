import argparse
from pathlib import Path

from app.config import DB_PATH
from app.database import get_connection, init_db
from app.import_master_data import import_master_data, read_workbook, validate_workbook
from app.session_generator import month_bounds


def _count(query: str, params: tuple = ()) -> int:
    with get_connection() as conn:
        return int(conn.execute(query, params).fetchone()["count"])


def run_preflight(file_path: str | Path, year: int, month: int) -> tuple[str, list[str]]:
    messages: list[str] = []
    status = "PASS"

    workbook = read_workbook(file_path)
    errors = validate_workbook(workbook)
    if errors:
        messages.append(f"Dry-run validation failed with {len(errors)} error(s).")
        messages.extend(error.format() for error in errors)
        status = "FAIL"
    else:
        import_master_data(file_path, dry_run=True)
        messages.append("Dry-run validation passed.")

    if not DB_PATH.exists():
        messages.append(f"Database does not exist at {DB_PATH}.")
        status = "FAIL"
        return status, messages

    init_db()
    checks = [
        ("active lecturers", "SELECT COUNT(*) AS count FROM lecturers WHERE active = 1"),
        ("active courses", "SELECT COUNT(*) AS count FROM courses WHERE active = 1"),
        ("active groups", "SELECT COUNT(*) AS count FROM student_groups WHERE active = 1"),
    ]
    for label, query in checks:
        count = _count(query)
        messages.append(f"{label}: {count}")
        if count == 0 and status != "FAIL":
            status = "WARNING"

    start, end = month_bounds(year, month)
    timetable_count = _count(
        """
        SELECT COUNT(*) AS count
        FROM timetable_entries
        WHERE active = 1
          AND date(effective_start_date) <= date(?)
          AND date(effective_end_date) >= date(?)
        """,
        (end.isoformat(), start.isoformat()),
    )
    calendar_count = _count(
        """
        SELECT COUNT(*) AS count
        FROM academic_calendar
        WHERE date(start_date) <= date(?)
          AND date(end_date) >= date(?)
        """,
        (end.isoformat(), start.isoformat()),
    )
    messages.append(f"timetable entries for selected month: {timetable_count}")
    messages.append(f"academic calendar entries for selected month: {calendar_count}")
    if timetable_count == 0 and status != "FAIL":
        status = "WARNING"
    if calendar_count == 0 and status != "FAIL":
        status = "WARNING"
    return status, messages


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preflight checks before session/document generation.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    status, messages = run_preflight(args.file, args.year, args.month)
    print(f"Preflight status: {status}")
    for message in messages:
        print(f"- {message}")
    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
