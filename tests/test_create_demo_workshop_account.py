from app.auth_service import authenticate_user
from app.create_demo_workshop_account import (
    DEMO_FULL_NAME,
    DEMO_GROUP_NAME,
    DEMO_STAFF_NUMBER,
    DEMO_USERNAME,
    create_demo_workshop_account,
)
from app.database import get_connection, init_db
from app.student_service import list_student_enrolments
from app.timetable_service import list_groups_for_timetable


def _clear_demo_test_db() -> None:
    init_db()
    with get_connection() as conn:
        for table in [
            "audit_logs",
            "user_accounts",
            "group_enrolments",
            "students",
            "timetable_entries",
            "student_groups",
            "courses",
            "lecturers",
        ]:
            conn.execute(f"DELETE FROM {table}")


def test_demo_workshop_dry_run_does_not_write():
    _clear_demo_test_db()

    summary = create_demo_workshop_account(dry_run=True)

    assert summary.dry_run is True
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM lecturers").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0] == 0


def test_demo_workshop_yes_creates_demo_data_and_login():
    _clear_demo_test_db()

    summary = create_demo_workshop_account(dry_run=False, password="DemoPass@2026")

    assert summary.lecturer_action == "created"
    assert summary.students_created == 5
    assert summary.enrolments_created == 5
    user = authenticate_user(DEMO_USERNAME, "DemoPass@2026")
    assert user is not None
    assert user["staff_number"] == DEMO_STAFF_NUMBER
    assert user["must_change_password"] is True

    groups = list_groups_for_timetable(DEMO_STAFF_NUMBER)
    enrolments = list_student_enrolments(staff_number=DEMO_STAFF_NUMBER, active=True)
    assert list(groups["group_name"]) == [DEMO_GROUP_NAME]
    assert len(enrolments) == 5
    assert set(enrolments["lecturer_name"]) == {DEMO_FULL_NAME}


def test_demo_workshop_creation_is_idempotent():
    _clear_demo_test_db()

    create_demo_workshop_account(dry_run=False, password="DemoPass@2026")
    second = create_demo_workshop_account(dry_run=False, password="DemoPass@2026")

    assert second.lecturer_action == "exists"
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM lecturers WHERE staff_number = ?", (DEMO_STAFF_NUMBER,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM group_enrolments").fetchone()[0] == 5


def test_demo_workshop_data_has_no_bank_or_real_sensitive_values():
    _clear_demo_test_db()
    create_demo_workshop_account(dry_run=False, password="DemoPass@2026")

    with get_connection() as conn:
        lecturer = conn.execute("SELECT * FROM lecturers WHERE staff_number = ?", (DEMO_STAFF_NUMBER,)).fetchone()
        students = conn.execute("SELECT student_number, surname, full_name FROM students").fetchall()

    text = " ".join(str(value) for value in dict(lecturer).values())
    assert "bank" not in text.casefold()
    assert "account" not in text.casefold()
    assert "DEMO-ID" in lecturer["id_or_passport_number"]
    assert "DEMO-PAYE" in lecturer["paye_number"]
    assert all(str(row["student_number"]).startswith("DEMO-STU-") for row in students)
    assert all(str(row["surname"]).startswith("DemoSurname") for row in students)
