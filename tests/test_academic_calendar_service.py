import sqlite3
import inspect

import app.academic_calendar_service as academic_calendar_service
from app.academic_calendar_service import (
    calendar_exclusion_applies,
    create_calendar_entry,
    ensure_academic_calendar_schema,
    get_calendar_entry,
    list_calendar_entries,
    reference_calendar_df,
    set_calendar_entry_active,
    update_calendar_entry,
    validate_calendar_data,
)
from app.database import get_connection, init_db


def _clear_calendar_db() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM academic_calendar")


def _seed_calendar_scope_data() -> None:
    init_db()
    with get_connection() as conn:
        for table in [
            "audit_logs",
            "user_accounts",
            "academic_calendar",
            "group_enrolments",
            "students",
            "timetable_entries",
            "student_groups",
            "courses",
            "lecturers",
        ]:
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO lecturers (
                id, staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES (11, '900011', 'Ms', 'Calendar Lecturer', 'M', 'ID', 'PAYE', 'Address', '081', 440, 'Campus', '2026-01-01', '2026-12-31', 1)
            """
        )

        conn.execute(
            """
            INSERT INTO courses (id, course_code, course_name, faculty, department, budget_allocation, active)
            VALUES (22, 'CAL101', 'Calendar Course', 'Faculty', 'Department', 'BUD', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO student_groups (id, group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES (33, 'CAL_GROUP', 22, 11, 'Campus', 'Full-time', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO academic_calendar (
                id, title, start_date, end_date, calendar_type, action, allow_override,
                start_time, end_time, scope_type, lecturer_id, course_id, group_id,
                exclude_from_claims_and_registers, notes, active
            )
            VALUES
                (101, 'Active group exclusion', '2026-03-02', '2026-03-02', 'unexpected_class_cancellation', 'exclude', 0,
                 '10:00', '11:00', 'group', NULL, NULL, 33, 1, 'Test', 1),
                (102, 'Inactive public holiday', '2026-03-03', '2026-03-03', 'public_holiday', 'exclude', 0,
                 NULL, NULL, 'all', NULL, NULL, NULL, 1, 'Test', 0)
            """
        )


def test_calendar_listing_uses_runtime_database_provider():
    source = inspect.getsource(academic_calendar_service.list_calendar_entries)

    assert "get_runtime_connection" in source
    assert "convert_placeholders" in source


def test_academic_calendar_schema_migration_preserves_existing_rows():
    _clear_calendar_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO academic_calendar (title, start_date, end_date, calendar_type, action, allow_override)
            VALUES ('Legacy Closure', '2026-03-02', '2026-03-02', 'institutional_closure', 'exclude', 0)
            """
        )

    ensure_academic_calendar_schema()

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM academic_calendar").fetchone()["count"]
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(academic_calendar)").fetchall()]
    assert count == 1
    assert "start_time" in columns
    assert "scope_type" in columns
    assert "exclude_from_claims_and_registers" in columns
    assert "active" in columns


def test_calendar_validation_rejects_invalid_date_and_time_ranges():
    _clear_calendar_db()
    is_valid, errors = validate_calendar_data(
        {
            "title": "Invalid",
            "calendar_type": "Unexpected Class Cancellation",
            "start_date": "2026-03-03",
            "end_date": "2026-03-02",
            "start_time": "10:00",
            "end_time": "09:00",
            "scope_type": "all",
        }
    )
    assert is_valid is False
    assert "End date must be on or after start date." in errors
    assert "End time must be after start time." in errors


def test_list_calendar_entries_filters_are_not_ambiguous():
    _seed_calendar_scope_data()

    active_entries = list_calendar_entries(active=True)
    inactive_entries = list_calendar_entries(active=False)
    all_entries = list_calendar_entries(active=None)
    type_entries = list_calendar_entries(calendar_type="Unexpected Class Cancellation")

    assert list(active_entries["title"]) == ["Active group exclusion"]
    assert list(inactive_entries["title"]) == ["Inactive public holiday"]
    assert set(all_entries["title"]) == {"Active group exclusion", "Inactive public holiday"}
    assert list(type_entries["title"]) == ["Active group exclusion"]


def test_list_calendar_entries_returns_clear_active_and_joined_scope_columns():
    _seed_calendar_scope_data()

    entries = list_calendar_entries(active=True)
    row = entries.iloc[0].to_dict()

    assert row["id"] == 101
    assert row["calendar_id"] == 101
    assert row["active"] == 1
    assert row["calendar_active"] == 1
    assert row["group_name"] == "CAL_GROUP"
    assert row["group_active"] == 1
    assert row["course_code"] == "CAL101"
    assert row["lecturer_name"] == "Calendar Lecturer"


def test_reference_calendar_helper_does_not_depend_on_filtered_sql():
    df = reference_calendar_df()

    assert not df.empty
    assert {"title", "start_date", "end_date", "category"}.issubset(df.columns)
    assert "Semester 1 Mid-Semester Break" in set(df["title"])


def test_calendar_create_update_deactivate_reactivate(monkeypatch):
    _clear_calendar_db()
    monkeypatch.setattr("app.academic_calendar_service._backup", lambda prefix: None)
    monkeypatch.setattr("app.academic_calendar_service.log_audit_event", lambda *args, **kwargs: None)

    entry_id = create_calendar_entry(
        {
            "title": "Unexpected closure",
            "calendar_type": "Unexpected Class Cancellation",
            "start_date": "2026-03-02",
            "end_date": "2026-03-02",
            "scope_type": "all",
            "exclude_from_claims_and_registers": True,
            "notes": "Test-only row",
        }
    )
    assert get_calendar_entry(entry_id)["title"] == "Unexpected closure"

    update_calendar_entry(
        entry_id,
        {
            "title": "Updated closure",
            "calendar_type": "Unexpected Class Cancellation",
            "start_date": "2026-03-02",
            "end_date": "2026-03-02",
            "scope_type": "all",
            "exclude_from_claims_and_registers": True,
            "active": True,
            "notes": "Updated",
        },
    )
    assert get_calendar_entry(entry_id)["title"] == "Updated closure"

    set_calendar_entry_active(entry_id, False)
    assert get_calendar_entry(entry_id)["active"] == 0
    set_calendar_entry_active(entry_id, True)
    assert get_calendar_entry(entry_id)["active"] == 1


def test_calendar_exclusion_applies_for_full_day_and_time_overlap():
    row = {
        "title": "Test",
        "start_date": "2026-03-02",
        "end_date": "2026-03-02",
        "action": "exclude",
        "active": 1,
        "exclude_from_claims_and_registers": 1,
        "scope_type": "all",
        "start_time": "10:30",
        "end_time": "10:45",
    }
    session = {
        "session_date": "2026-03-02",
        "start_time": "10:00",
        "end_time": "11:00",
        "lecturer_id": 1,
        "course_id": 1,
        "group_id": 1,
    }
    assert calendar_exclusion_applies(row, session) is True

    row["start_time"] = "11:00"
    row["end_time"] = "12:00"
    assert calendar_exclusion_applies(row, session) is False

    row["start_time"] = None
    row["end_time"] = None
    assert calendar_exclusion_applies(row, session) is True


def test_calendar_exclusion_scopes_and_inactive_rows():
    base = {
        "title": "Scoped",
        "start_date": "2026-03-02",
        "end_date": "2026-03-02",
        "action": "exclude",
        "active": 1,
        "exclude_from_claims_and_registers": 1,
        "start_time": None,
        "end_time": None,
    }
    session = {
        "session_date": "2026-03-02",
        "start_time": "10:00",
        "end_time": "11:00",
        "lecturer_id": 10,
        "course_id": 20,
        "group_id": 30,
    }
    assert calendar_exclusion_applies(base | {"scope_type": "lecturer", "lecturer_id": 10}, session) is True
    assert calendar_exclusion_applies(base | {"scope_type": "lecturer", "lecturer_id": 11}, session) is False
    assert calendar_exclusion_applies(base | {"scope_type": "course", "course_id": 20}, session) is True
    assert calendar_exclusion_applies(base | {"scope_type": "course", "course_id": 21}, session) is False
    assert calendar_exclusion_applies(base | {"scope_type": "group", "group_id": 30}, session) is True
    assert calendar_exclusion_applies(base | {"scope_type": "group", "group_id": 31}, session) is False
    assert calendar_exclusion_applies(base | {"scope_type": "all", "active": 0}, session) is False
    assert calendar_exclusion_applies(base | {"scope_type": "all", "exclude_from_claims_and_registers": 0}, session) is False
