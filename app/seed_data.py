import argparse
import sys

from app.backup_database import backup_database
from app.config import DB_PATH, REAL_DB_PATH
from app.database import get_connection, init_db

REAL_SEED_PHRASE = "I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA"


def _is_real_database() -> bool:
    return DB_PATH.resolve() == REAL_DB_PATH.resolve()


def _lecturer_count() -> int:
    if not DB_PATH.exists():
        return 0
    init_db()
    with get_connection(DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) AS count FROM lecturers").fetchone()["count"])


def _assert_seed_allowed(confirm_real_seed: bool = False, confirmation_phrase: str = "") -> None:
    if not _is_real_database():
        return
    if confirm_real_seed and confirmation_phrase == REAL_SEED_PHRASE:
        return
    detail = " because lecturer records exist" if _lecturer_count() > 0 else ""
    raise RuntimeError(
        f"Refusing to seed real data/pt_claims.db{detail}. "
        "Seed data must not be written to the real database without explicit confirmation. "
        "To proceed intentionally, pass --confirm-real-seed "
        f"--phrase {REAL_SEED_PHRASE}"
    )


def seed_database(confirm_real_seed: bool = False, confirmation_phrase: str = "") -> None:
    _assert_seed_allowed(confirm_real_seed, confirmation_phrase)
    init_db()
    if DB_PATH.exists():
        backup_database(prefix="pt_claims_before_seed_data")
    with get_connection(DB_PATH) as conn:
        conn.executescript(
            """
            DELETE FROM group_enrolments;
            DELETE FROM students;
            DELETE FROM academic_calendar;
            DELETE FROM timetable_entries;
            DELETE FROM student_groups;
            DELETE FROM courses;
            DELETE FROM lecturers;
            DELETE FROM sqlite_sequence WHERE name IN (
                'academic_calendar',
                'timetable_entries',
                'student_groups',
                'courses',
                'lecturers',
                'students',
                'group_enrolments'
            );
            """
        )

        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "100718",
                "Ms.",
                "Lonia Nghitotelwa",
                "Bachelor of Computer Science in System Administration",
                "DUMMY-ID-0001",
                "DUMMY-PAYE-0001",
                "P.O. Box 000, Eenhana",
                "0810000000",
                410,
                "Eenhana Satellite Campus",
                "2026-02-01",
                "2026-02-28",
                1,
            ),
        )

        conn.execute(
            """
            INSERT INTO courses (
                course_code, course_name, faculty, department, budget_allocation, active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "CUS411S",
                "Computer User Skills",
                "Faculty of Computing and Informatics",
                "Department of Informatics and Journalism",
                "0183-0102",
                1,
            ),
        )

        course_id = conn.execute("SELECT id FROM courses WHERE course_code = 'CUS411S'").fetchone()["id"]
        for group_num in range(1, 12):
            conn.execute(
                """
                INSERT INTO student_groups (group_name, course_id, campus, study_mode, active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"Group {group_num}", course_id, "Eenhana Satellite Campus", "Part-time", 1),
            )

        lecturer_id = conn.execute("SELECT id FROM lecturers WHERE staff_number = '100718'").fetchone()["id"]
        groups = {
            row["group_name"]: row["id"]
            for row in conn.execute("SELECT id, group_name FROM student_groups").fetchall()
        }

        timetable_entries = [
            ("Group 1", "Monday", "08:00", "10:00"),
            ("Group 2", "Monday", "10:00", "12:00"),
            ("Group 3", "Tuesday", "09:00", "11:00"),
            ("Group 4", "Wednesday", "13:00", "15:00"),
            ("Group 5", "Thursday", "08:00", "10:00"),
            ("Group 6", "Friday", "14:00", "16:00"),
            ("Group 7", "Saturday", "09:00", "12:00"),
            ("Group 8", "Monday", "09:30", "11:30"),  # Deliberate clash with Group 1 and 2.
            ("Group 9", "Tuesday", "11:00", "12:00"),  # Back-to-back with Group 3.
            ("Group 10", "Sunday", "09:00", "11:00"),  # Excluded by default.
            ("Group 11", "Wednesday", "15:00", "17:00"),
        ]
        for group_name, day_of_week, start_time, end_time in timetable_entries:
            conn.execute(
                """
                INSERT INTO timetable_entries (
                    lecturer_id, group_id, day_of_week, start_time, end_time,
                    effective_start_date, effective_end_date, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lecturer_id,
                    groups[group_name],
                    day_of_week,
                    start_time,
                    end_time,
                    "2026-02-01",
                    "2026-02-28",
                    1,
                ),
            )

        calendar_rows = [
            (
                "Constitution Day observed",
                "2026-02-09",
                "2026-02-09",
                "public_holiday",
                "exclude",
                0,
            ),
            (
                "Institutional systems closure",
                "2026-02-18",
                "2026-02-19",
                "institutional_closure",
                "exclude",
                0,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO academic_calendar (
                title, start_date, end_date, calendar_type, action, allow_override
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            calendar_rows,
        )


def seed_clean_demo_data(confirm_real_seed: bool = False, confirmation_phrase: str = "") -> None:
    _assert_seed_allowed(confirm_real_seed, confirmation_phrase)
    init_db()
    if DB_PATH.exists():
        backup_database(prefix="pt_claims_before_seed_clean_demo_data")
    with get_connection(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(staff_number) DO UPDATE SET
                title = excluded.title,
                full_name = excluded.full_name,
                highest_qualification = excluded.highest_qualification,
                id_or_passport_number = excluded.id_or_passport_number,
                paye_number = excluded.paye_number,
                physical_address = excluded.physical_address,
                contact_number = excluded.contact_number,
                tariff_per_hour = excluded.tariff_per_hour,
                campus = excluded.campus,
                contract_start_date = excluded.contract_start_date,
                contract_end_date = excluded.contract_end_date,
                active = excluded.active
            """,
            (
                "200001",
                "Ms",
                "Demo Clean Lecturer",
                "Dummy Qualification",
                "DUMMY-ID-200001",
                "DUMMY-PAYE-200001",
                "P.O. Box 000, Windhoek",
                "0810000001",
                410,
                "Windhoek Main Campus",
                "2026-02-01",
                "2026-02-28",
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO courses (
                course_code, course_name, faculty, department, budget_allocation, active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(course_code) DO UPDATE SET
                course_name = excluded.course_name,
                faculty = excluded.faculty,
                department = excluded.department,
                budget_allocation = excluded.budget_allocation,
                active = excluded.active
            """,
            (
                "CUS411S",
                "Computer User Skills",
                "Computing and Informatics",
                "Informatics and Journalism",
                "0183-0102",
                1,
            ),
        )
        course_id = conn.execute("SELECT id FROM courses WHERE course_code = 'CUS411S'").fetchone()["id"]
        lecturer_id = conn.execute("SELECT id FROM lecturers WHERE staff_number = '200001'").fetchone()["id"]

        demo_groups = [
            ("Demo Group A", "Monday", "08:00", "09:00"),
            ("Demo Group B", "Tuesday", "10:00", "11:00"),
            ("Demo Group C", "Thursday", "14:00", "15:00"),
        ]
        for group_name, _, _, _ in demo_groups:
            exists = conn.execute(
                "SELECT id FROM student_groups WHERE group_name = ? AND course_id = ?",
                (group_name, course_id),
            ).fetchone()
            if exists is None:
                conn.execute(
                    """
                    INSERT INTO student_groups (group_name, course_id, campus, study_mode, active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (group_name, course_id, "Windhoek Main Campus", "Part-time", 1),
                )

        for group_name, day_of_week, start_time, end_time in demo_groups:
            group_id = conn.execute(
                "SELECT id FROM student_groups WHERE group_name = ? AND course_id = ?",
                (group_name, course_id),
            ).fetchone()["id"]
            exists = conn.execute(
                """
                SELECT id FROM timetable_entries
                WHERE lecturer_id = ? AND group_id = ? AND day_of_week = ?
                  AND start_time = ? AND end_time = ?
                  AND effective_start_date = '2026-02-01'
                  AND effective_end_date = '2026-02-28'
                """,
                (lecturer_id, group_id, day_of_week, start_time, end_time),
            ).fetchone()
            if exists is None:
                conn.execute(
                    """
                    INSERT INTO timetable_entries (
                        lecturer_id, group_id, day_of_week, start_time, end_time,
                        effective_start_date, effective_end_date, active
                    )
                    VALUES (?, ?, ?, ?, ?, '2026-02-01', '2026-02-28', 1)
                    """,
                    (lecturer_id, group_id, day_of_week, start_time, end_time),
                )

        exists = conn.execute(
            """
            SELECT id FROM academic_calendar
            WHERE title = 'Clean demo institutional closure'
              AND start_date = '2026-02-10'
              AND end_date = '2026-02-10'
            """
        ).fetchone()
        if exists is None:
            conn.execute(
                """
                INSERT INTO academic_calendar (
                    title, start_date, end_date, calendar_type, action, allow_override
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Clean demo institutional closure",
                    "2026-02-10",
                    "2026-02-10",
                    "institutional_closure",
                    "exclude",
                    0,
                ),
            )

        surnames = {
            "Demo Group A": [
                "Amunyela",
                "Haingura",
                "Iileka",
                "Kambonde",
                "Mubita",
                "Nangolo",
                "Shikongo",
                "Tjombe",
                "Uushona",
                "Vatileni",
                "YaNdapewa",
                "Zorondo",
            ],
            "Demo Group B": [
                "Amutenya",
                "Hamukoto",
                "Iipinge",
                "Kandjimi",
                "Mbango",
                "Nghipandulwa",
                "Shihepo",
                "Tjituka",
                "Uugwanga",
                "Vilho",
                "Yambeka",
                "Zimba",
            ],
            "Demo Group C": [
                "Andima",
                "Haufiku",
                "Iita",
                "Kavari",
                "Moses",
                "Namene",
                "Shipanga",
                "Tobias",
                "Uirab",
                "Viljoen",
                "YaToivo",
                "Zenze",
            ],
        }
        student_number = 900000001
        for group_name, names in surnames.items():
            group_id = conn.execute(
                "SELECT id FROM student_groups WHERE group_name = ? AND course_id = ?",
                (group_name, course_id),
            ).fetchone()["id"]
            for offset, surname in enumerate(names):
                number = str(student_number)
                initials = f"{chr(65 + (offset % 26))}."
                full_name = f"{initials} {surname}"
                conn.execute(
                    """
                    INSERT INTO students (student_number, surname, initials, full_name, active)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(student_number) DO UPDATE SET
                        surname = excluded.surname,
                        initials = excluded.initials,
                        full_name = excluded.full_name,
                        active = excluded.active
                    """,
                    (number, surname, initials, full_name),
                )
                student_id = conn.execute(
                    "SELECT id FROM students WHERE student_number = ?",
                    (number,),
                ).fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO group_enrolments (student_id, group_id, active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(student_id, group_id) DO UPDATE SET active = excluded.active
                    """,
                    (student_id, group_id),
                )
                student_number += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-real-seed", action="store_true")
    parser.add_argument("--phrase", default="")
    args = parser.parse_args()
    try:
        seed_database(confirm_real_seed=args.confirm_real_seed, confirmation_phrase=args.phrase)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(f"Seeded database at {DB_PATH}")


if __name__ == "__main__":
    main()
