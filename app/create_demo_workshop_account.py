from __future__ import annotations

import argparse
from dataclasses import dataclass

from app.auth_service import create_or_update_user_account, lecturer_id_for_staff_number
from app.database import get_connection, init_db


DEMO_USERNAME = "demo_lecturer"
DEMO_STAFF_NUMBER = "900999"
DEMO_FULL_NAME = "Demo Lecturer (Demo/Training)"
DEMO_COURSE_CODE = "DEMO101"
DEMO_GROUP_NAME = "DEMO_LECTURER_GROUP_FT_SEM1_2026"


@dataclass
class DemoCreationSummary:
    dry_run: bool
    lecturer_action: str
    account_action: str
    course_action: str
    group_action: str
    timetable_action: str
    students_created: int
    enrolments_created: int


def _exists(conn, sql: str, params: tuple = ()) -> bool:
    return conn.execute(sql, params).fetchone() is not None


def create_demo_workshop_account(*, dry_run: bool = True, password: str | None = None) -> DemoCreationSummary:
    if not dry_run and not password:
        raise ValueError("A temporary demo password is required when writing demo workshop data.")
    init_db()
    with get_connection() as conn:
        lecturer_exists = _exists(conn, "SELECT 1 FROM lecturers WHERE staff_number = ?", (DEMO_STAFF_NUMBER,))
        course_exists = _exists(conn, "SELECT 1 FROM courses WHERE course_code = ?", (DEMO_COURSE_CODE,))
        group_exists = _exists(
            conn,
            """
            SELECT 1
            FROM student_groups AS g
            JOIN courses AS c ON c.id = g.course_id
            WHERE g.group_name = ? AND c.course_code = ?
            """,
            (DEMO_GROUP_NAME, DEMO_COURSE_CODE),
        )
    if dry_run:
        return DemoCreationSummary(
            dry_run=True,
            lecturer_action="exists" if lecturer_exists else "would_create",
            account_action="would_upsert",
            course_action="exists" if course_exists else "would_create",
            group_action="exists" if group_exists else "would_create",
            timetable_action="would_create_if_missing",
            students_created=0,
            enrolments_created=0,
        )

    with get_connection() as conn:
        if not lecturer_exists:
            conn.execute(
                """
                INSERT INTO lecturers (
                    staff_number, title, full_name, highest_qualification, id_or_passport_number,
                    paye_number, physical_address, contact_number, tariff_per_hour, campus,
                    contract_start_date, contract_end_date, active
                )
                VALUES (?, 'Mx', ?, 'Demo qualification', 'DEMO-ID-0000', 'DEMO-PAYE-0000',
                        'Demo training address', '0800000000', 440, 'Demo Campus',
                        '2026-01-01', '2026-12-31', 1)
                """,
                (DEMO_STAFF_NUMBER, DEMO_FULL_NAME),
            )
        if not course_exists:
            conn.execute(
                """
                INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active)
                VALUES (?, 'Demo Training Course', 'Demo Faculty', 'Demo Department', 'DEMO-BUDGET', 1)
                """,
                (DEMO_COURSE_CODE,),
            )
        lecturer_id = conn.execute("SELECT id FROM lecturers WHERE staff_number = ?", (DEMO_STAFF_NUMBER,)).fetchone()["id"]
        course_id = conn.execute("SELECT id FROM courses WHERE course_code = ?", (DEMO_COURSE_CODE,)).fetchone()["id"]
        if not group_exists:
            conn.execute(
                """
                INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
                VALUES (?, ?, ?, 'Demo Campus', 'Full-time', 1)
                """,
                (DEMO_GROUP_NAME, course_id, lecturer_id),
            )
        group_id = conn.execute(
            "SELECT id FROM student_groups WHERE group_name = ? AND course_id = ? AND lecturer_id = ?",
            (DEMO_GROUP_NAME, course_id, lecturer_id),
        ).fetchone()["id"]
        timetable_created = "exists"
        if not _exists(conn, "SELECT 1 FROM timetable_entries WHERE lecturer_id = ? AND group_id = ?", (lecturer_id, group_id)):
            conn.execute(
                """
                INSERT INTO timetable_entries (
                    lecturer_id, group_id, day_of_week, start_time, end_time,
                    effective_start_date, effective_end_date, active
                )
                VALUES (?, ?, 'Monday', '10:00', '11:30', '2026-02-01', '2026-11-30', 1)
                """,
                (lecturer_id, group_id),
            )
            timetable_created = "created"
        students_created = 0
        enrolments_created = 0
        for idx in range(1, 6):
            student_number = f"DEMO-STU-{idx:03d}"
            if not _exists(conn, "SELECT 1 FROM students WHERE student_number = ?", (student_number,)):
                conn.execute(
                    "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)",
                    (student_number, f"DemoSurname{idx:03d}", "D", f"Demo Student {idx:03d}"),
                )
                students_created += 1
            student_id = conn.execute("SELECT id FROM students WHERE student_number = ?", (student_number,)).fetchone()["id"]
            if not _exists(conn, "SELECT 1 FROM group_enrolments WHERE student_id = ? AND group_id = ?", (student_id, group_id)):
                conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)", (student_id, group_id))
                enrolments_created += 1

    lecturer_id = lecturer_id_for_staff_number(DEMO_STAFF_NUMBER)
    account_action = create_or_update_user_account(
        DEMO_USERNAME,
        str(password),
        "lecturer",
        lecturer_id,
        must_change_password=True,
        active=True,
    )
    return DemoCreationSummary(
        dry_run=False,
        lecturer_action="exists" if lecturer_exists else "created",
        account_action=account_action,
        course_action="exists" if course_exists else "created",
        group_action="exists" if group_exists else "created",
        timetable_action=timetable_created,
        students_created=students_created,
        enrolments_created=enrolments_created,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create demo-only workshop lecturer data.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without writing data.")
    parser.add_argument("--yes", action="store_true", help="Write demo workshop data.")
    parser.add_argument("--password", default="", help="Temporary password for demo_lecturer. Required with --yes.")
    args = parser.parse_args()
    if args.yes == args.dry_run:
        raise SystemExit("Use exactly one of --dry-run or --yes.")
    summary = create_demo_workshop_account(dry_run=args.dry_run, password=args.password or None)
    print(summary)


if __name__ == "__main__":
    main()
