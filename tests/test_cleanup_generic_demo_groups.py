import sqlite3

from app.database import init_db
from tools.cleanup_generic_demo_groups import analyse_generic_groups, cleanup_generic_groups


def _seed_cleanup_fixture(db_path):
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES ('300001', 'Ms', 'Real Lecturer', 'Qualification', 'ID', 'PAYE', 'Address', '081', 410,
                    'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active)
            VALUES ('CUS411S', 'Computer User Skills', 'Computing and Informatics', 'Informatics', '0183-0102', 1)
            """
        )
        lecturer_id = conn.execute("SELECT id FROM lecturers WHERE staff_number = '300001'").fetchone()["id"]
        course_id = conn.execute("SELECT id FROM courses WHERE course_code = 'CUS411S'").fetchone()["id"]
        conn.execute(
            "INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active) VALUES (?, ?, NULL, ?, ?, 1)",
            ("Group 1", course_id, "Windhoek Main Campus", "Part-time"),
        )
        generic_group_id = conn.execute("SELECT id FROM student_groups WHERE group_name = 'Group 1'").fetchone()["id"]
        conn.execute(
            "INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active) VALUES (?, ?, ?, ?, ?, 1)",
            ("REAL_GROUP", course_id, lecturer_id, "Windhoek Main Campus", "Part-time"),
        )
        scoped_group_id = conn.execute("SELECT id FROM student_groups WHERE group_name = 'REAL_GROUP'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (?, ?, 'Monday', '08:00', '09:00', '2026-01-01', '2026-12-31', 1)
            """,
            (lecturer_id, generic_group_id),
        )
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (?, ?, 'Tuesday', '10:00', '11:00', '2026-01-01', '2026-12-31', 1)
            """,
            (lecturer_id, scoped_group_id),
        )
        conn.execute(
            "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('9001', 'Student', 'S.', 'S. Student', 1)"
        )
        student_id = conn.execute("SELECT id FROM students WHERE student_number = '9001'").fetchone()["id"]
        conn.execute(
            "INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)",
            (student_id, generic_group_id),
        )


def test_generic_demo_cleanup_dry_run_does_not_modify_db(tmp_path):
    db_path = tmp_path / "cleanup.db"
    _seed_cleanup_fixture(db_path)

    result = cleanup_generic_groups(db_path, yes=False)
    after_analysis = analyse_generic_groups(db_path)

    assert result["changed"] is False
    assert result["before"]["counts"]["generic_groups"] == 1
    assert after_analysis["counts"]["generic_groups"] == 1
    assert after_analysis["counts"]["linked_timetable_entries"] == 1
    assert after_analysis["counts"]["linked_group_enrolments"] == 1


def test_generic_demo_cleanup_yes_deletes_only_generic_groups_and_links(tmp_path):
    db_path = tmp_path / "cleanup.db"
    _seed_cleanup_fixture(db_path)

    result = cleanup_generic_groups(db_path, yes=True)

    assert result["changed"] is True
    assert result["backup"]
    assert (tmp_path / "pt_claims_BEFORE_GENERIC_GROUP_CLEANUP_20260511.db").exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM lecturers").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM student_groups WHERE lecturer_id IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM student_groups WHERE lecturer_id IS NOT NULL").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM group_enrolments").fetchone()[0] == 0
