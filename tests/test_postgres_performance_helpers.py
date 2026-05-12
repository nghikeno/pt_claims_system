from app.account_admin_service import list_user_accounts
from app.audit_service import list_audit_events, log_audit_event
from app.auth_service import create_or_update_user_account, lecturer_id_for_staff_number
from app.database import get_connection, init_db
from app.db_provider import db_perf_debug_enabled, psycopg_pool_available
from app.dev_reset import dev_reset
from app.performance_queries import admin_dashboard_counts, lecturer_dashboard_counts


def _insert_minimal_lecturer_dataset():
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES ('900001', 'Ms', 'Demo Lecturer One', 'MSc', 'ID', 'PAYE', 'Address',
                    '0810000000', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """
        )
        conn.execute(
            "INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active) VALUES ('ZZZ999', 'Demo Course', 'Faculty', 'Department', '0183-0102', 1)"
        )
        conn.execute(
            "INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active) VALUES ('DEMO_GROUP_001', (SELECT id FROM courses WHERE course_code = 'ZZZ999'), (SELECT id FROM lecturers WHERE staff_number = '900001'), 'Windhoek Main Campus', 'Full-time', 1)"
        )
        conn.execute(
            "INSERT INTO timetable_entries (lecturer_id, group_id, day_of_week, start_time, end_time, effective_start_date, effective_end_date, active) VALUES ((SELECT id FROM lecturers WHERE staff_number = '900001'), (SELECT id FROM student_groups WHERE group_name = 'DEMO_GROUP_001'), 'Monday', '08:00', '09:00', '2026-01-01', '2026-06-30', 1)"
        )
        conn.execute("INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('STU000001', 'DemoSurname001', 'A', 'DemoSurname001 A', 1)")
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES ((SELECT id FROM students WHERE student_number = 'STU000001'), (SELECT id FROM student_groups WHERE group_name = 'DEMO_GROUP_001'), 1)")


def test_admin_dashboard_counts_use_single_helper():
    dev_reset()
    _insert_minimal_lecturer_dataset()

    counts = admin_dashboard_counts()

    assert counts["lecturers"] >= 1
    assert counts["courses"] >= 1
    assert counts["groups"] >= 1
    assert counts["students"] >= 1
    assert counts["timetable entries"] >= 1


def test_lecturer_dashboard_counts_are_scoped():
    dev_reset()
    _insert_minimal_lecturer_dataset()

    counts = lecturer_dashboard_counts("900001")

    assert counts["groups"] == 1
    assert counts["timetable entries"] == 1
    assert counts["active enrolments"] == 1


def test_audit_log_query_is_limited():
    dev_reset()
    for index in range(5):
        log_audit_event("test_event", user={"username": f"user{index}", "role": "admin"})

    events = list_audit_events(limit=3)

    assert len(events) == 3


def test_account_management_does_not_expose_password_hashes():
    dev_reset()
    _insert_minimal_lecturer_dataset()
    lecturer_id = lecturer_id_for_staff_number("900001")
    create_or_update_user_account("900001", "Staging@2026", "lecturer", lecturer_id)

    users = list_user_accounts()

    assert "password_hash" not in users.columns
    assert "password_salt" not in users.columns


def test_perf_debug_env_flag(monkeypatch):
    monkeypatch.setenv("DB_PERF_DEBUG", "true")
    assert db_perf_debug_enabled() is True


def test_pool_dependency_detection_returns_boolean():
    assert isinstance(psycopg_pool_available(), bool)
