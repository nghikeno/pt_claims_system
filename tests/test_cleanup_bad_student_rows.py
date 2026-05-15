from app.cleanup_bad_student_rows import CONFIRMATION_PHRASE, cleanup_suspicious_student_rows, main
from app.course_group_service import create_course, create_lecturer_group
from app.database import get_connection
from app.dev_reset import dev_reset
from app.lecturer_service import create_lecturer


def setup_cleanup_data():
    dev_reset()
    create_lecturer(
        {
            "staff_number": "300001",
            "title": "Ms",
            "full_name": "Cleanup Lecturer",
            "highest_qualification": "MSc",
            "id_or_passport_number": "ID300001",
            "paye_number": "PAYE300001",
            "physical_address": "P.O. Box 1",
            "contact_number": "0810000001",
            "tariff_per_hour": 410,
            "campus": "Windhoek Main Campus",
            "contract_start_date": "2026-01-01",
            "contract_end_date": "2026-12-31",
            "active": "Yes",
        }
    )
    create_course(
        {
            "course_code": "TST999S",
            "course_name": "Test Student Skills",
            "faculty": "Computing and Informatics",
            "department": "Informatics",
            "budget_allocation": "0183-0102",
            "active": "Yes",
        }
    )
    create_lecturer_group(
        {
            "staff_number": "300001",
            "course_code": "TST999S",
            "group_name": "CLEANUP_GROUP",
            "campus": "Windhoek Main Campus",
            "study_mode": "Full-time",
            "active": "Yes",
        }
    )
    with get_connection() as conn:
        group_id = conn.execute("SELECT id FROM student_groups WHERE group_name = 'CLEANUP_GROUP'").fetchone()["id"]
        conn.execute(
            "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)",
            ("18402000", "STUDENT SURNAME & INIT...", "TIME:", "STUDENT SURNAME & INIT... TIME:"),
        )
        bad_id = conn.execute("SELECT id FROM students WHERE student_number = '18402000'").fetchone()["id"]
        conn.execute(
            "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)",
            ("226173453", "Haukongo", "JL", "Haukongo JL"),
        )
        good_id = conn.execute("SELECT id FROM students WHERE student_number = '226173453'").fetchone()["id"]
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)", (bad_id, group_id))
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)", (good_id, group_id))


def test_cleanup_dry_run_finds_only_bogus_header_row_student():
    setup_cleanup_data()

    report = cleanup_suspicious_student_rows(write=False)

    assert report["status"] == "DRY_RUN"
    assert report["matched_count"] == 1
    assert report["rows"][0]["student_number"] == "18402000"
    with get_connection() as conn:
        assert conn.execute("SELECT active FROM students WHERE student_number = '18402000'").fetchone()["active"] == 1
        assert conn.execute("SELECT active FROM students WHERE student_number = '226173453'").fetchone()["active"] == 1


def test_cleanup_write_requires_exact_confirmation():
    setup_cleanup_data()

    exit_code = main(["--yes", "--confirm-cleanup", "WRONG"])

    assert exit_code == 2
    with get_connection() as conn:
        assert conn.execute("SELECT active FROM students WHERE student_number = '18402000'").fetchone()["active"] == 1


def test_cleanup_write_deactivates_only_bogus_rows():
    setup_cleanup_data()

    exit_code = main(["--yes", "--confirm-cleanup", CONFIRMATION_PHRASE])

    assert exit_code == 0
    with get_connection() as conn:
        assert conn.execute("SELECT active FROM students WHERE student_number = '18402000'").fetchone()["active"] == 0
        assert conn.execute("SELECT active FROM students WHERE student_number = '226173453'").fetchone()["active"] == 1

