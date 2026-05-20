from datetime import date

from app.database import get_connection, init_db
from app.academic_calendar_service import import_nust_2026_exclusions
from app.generation_period_service import resolve_custom_generation_period
from app.session_generator import generate_monthly_sessions, generate_sessions_for_period


def _reset_minimal_session_data() -> None:
    init_db()
    with get_connection() as conn:
        for table in [
            "audit_logs",
            "group_enrolments",
            "students",
            "timetable_entries",
            "academic_calendar",
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
            VALUES
                (101, '900101', 'Ms', 'Demo Lecturer One', 'M', 'ID101', 'PAYE101', 'Address', '081', 440, 'Campus', '2026-01-01', '2026-12-31', 1),
                (102, '900102', 'Mr', 'Demo Lecturer Two', 'M', 'ID102', 'PAYE102', 'Address', '082', 440, 'Campus', '2026-01-01', '2026-12-31', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO courses (id, course_code, course_name, faculty, department, budget_allocation, active)
            VALUES
                (201, 'AAA101', 'Course One', 'Faculty', 'Department', 'BUD1', 1),
                (202, 'BBB202', 'Course Two', 'Faculty', 'Department', 'BUD2', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO student_groups (id, group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES
                (301, 'ONE_GROUP', 201, 101, 'Campus', 'Full-time', 1),
                (302, 'TWO_GROUP', 201, 102, 'Campus', 'Full-time', 1),
                (303, 'ONE_OTHER_COURSE', 202, 101, 'Campus', 'Full-time', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES
                (101, 301, 'Monday', '10:00', '11:00', '2026-03-01', '2026-03-31', 1),
                (102, 302, 'Monday', '10:00', '11:00', '2026-03-01', '2026-03-31', 1),
                (101, 303, 'Monday', '12:00', '13:00', '2026-03-01', '2026-03-31', 1)
            """
        )


def _insert_calendar(**overrides) -> None:
    data = {
        "title": "Calendar test",
        "start_date": "2026-03-02",
        "end_date": "2026-03-02",
        "calendar_type": "unexpected_class_cancellation",
        "action": "exclude",
        "allow_override": 0,
        "start_time": None,
        "end_time": None,
        "scope_type": "all",
        "lecturer_id": None,
        "course_id": None,
        "group_id": None,
        "exclude_from_claims_and_registers": 1,
        "notes": "",
        "active": 1,
    }
    data.update(overrides)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO academic_calendar (
                title, start_date, end_date, calendar_type, action, allow_override,
                start_time, end_time, scope_type, lecturer_id, course_id, group_id,
                exclude_from_claims_and_registers, notes, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"], data["start_date"], data["end_date"], data["calendar_type"],
                data["action"], data["allow_override"], data["start_time"], data["end_time"],
                data["scope_type"], data["lecturer_id"], data["course_id"], data["group_id"],
                data["exclude_from_claims_and_registers"], data["notes"], data["active"],
            ),
        )


def _session_rows(staff_number: int):
    return generate_monthly_sessions(staff_number, 2026, 3).to_dict("records")


def test_full_day_calendar_exclusion_removes_sessions_in_date_range():
    _reset_minimal_session_data()
    _insert_calendar()

    rows = _session_rows(900101)

    assert all(row["session_date"] != "2026-03-02" for row in rows)


def test_time_bound_exclusion_removes_only_overlapping_sessions():
    _reset_minimal_session_data()
    _insert_calendar(start_time="10:30", end_time="10:45")

    rows = _session_rows(900101)

    excluded_group_dates = {(row["group_name"], row["session_date"]) for row in rows}
    assert ("ONE_GROUP", "2026-03-02") not in excluded_group_dates
    assert ("ONE_OTHER_COURSE", "2026-03-02") in excluded_group_dates


def test_non_overlapping_time_bound_exclusion_does_not_remove_session():
    _reset_minimal_session_data()
    _insert_calendar(start_time="14:00", end_time="15:00")

    rows = _session_rows(900101)

    assert any(row["group_name"] == "ONE_GROUP" and row["session_date"] == "2026-03-02" for row in rows)


def test_lecturer_scoped_exclusion_affects_only_that_lecturer():
    _reset_minimal_session_data()
    _insert_calendar(scope_type="lecturer", lecturer_id=101)

    lecturer_one_rows = _session_rows(900101)
    lecturer_two_rows = _session_rows(900102)

    assert all(row["session_date"] != "2026-03-02" for row in lecturer_one_rows)
    assert any(row["session_date"] == "2026-03-02" for row in lecturer_two_rows)


def test_course_scoped_exclusion_affects_only_that_course():
    _reset_minimal_session_data()
    _insert_calendar(scope_type="course", course_id=201)

    rows = _session_rows(900101)
    groups_on_date = {row["group_name"] for row in rows if row["session_date"] == "2026-03-02"}

    assert "ONE_GROUP" not in groups_on_date
    assert "ONE_OTHER_COURSE" in groups_on_date


def test_group_scoped_exclusion_affects_only_that_group():
    _reset_minimal_session_data()
    _insert_calendar(scope_type="group", group_id=301)

    rows = _session_rows(900101)
    groups_on_date = {row["group_name"] for row in rows if row["session_date"] == "2026-03-02"}

    assert "ONE_GROUP" not in groups_on_date
    assert "ONE_OTHER_COURSE" in groups_on_date


def test_inactive_exclusions_do_not_affect_session_generation():
    _reset_minimal_session_data()
    _insert_calendar(active=0)

    rows = _session_rows(900101)

    assert any(row["session_date"] == "2026-03-02" for row in rows)


def test_session_generation_uses_custom_may_claim_period():
    _reset_minimal_session_data()
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (101, 301, 'Thursday', '10:00', '11:00', '2026-04-01', '2026-05-31', 1)
            """
        )

    rows = generate_monthly_sessions(900101, 2026, 5).to_dict("records")
    dates = {row["session_date"] for row in rows}

    assert "2026-04-30" in dates
    assert all(date <= "2026-05-29" for date in dates)


def test_academic_recess_in_may_custom_period_reduces_sessions_and_records_applied_exclusion():
    _reset_minimal_session_data()
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (101, 301, 'Tuesday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1)
            """
        )
    baseline = generate_monthly_sessions(900101, 2026, 5)
    _insert_calendar(
        title="Institutional Recess",
        calendar_type="academic_recess",
        start_date="2026-05-26",
        end_date="2026-05-27",
        scope_type="all",
        start_time=None,
        end_time=None,
    )

    filtered = generate_monthly_sessions(900101, 2026, 5)
    filtered_dates = set(filtered["session_date"])

    assert "2026-05-26" in set(baseline["session_date"])
    assert "2026-05-26" not in filtered_dates
    assert len(filtered) == len(baseline) - 1
    assert float(filtered["hours"].sum()) == float(baseline["hours"].sum()) - 1.0
    assert filtered.attrs["applied_calendar_exclusions"][0]["title"] == "Institutional Recess"
    assert any(detail["session_date"] == "2026-05-26" for detail in filtered.attrs["excluded_session_details"])


def test_imported_nust_exclusions_remove_good_friday_and_easter_monday_from_april_sessions(monkeypatch):
    _reset_minimal_session_data()
    monkeypatch.setattr("app.academic_calendar_service._backup", lambda prefix: {"performed": True, "mode": "sqlite", "safe_message": "backup", "path": "backup.db"})
    monkeypatch.setattr("app.academic_calendar_service.log_audit_event", lambda *args, **kwargs: None)
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES
                (101, 301, 'Friday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1),
                (101, 301, 'Monday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1)
            """
        )
    baseline_dates = set(generate_monthly_sessions(900101, 2026, 4)["session_date"])

    import_nust_2026_exclusions(confirm_phrase="IMPORT NUST EXCLUSIONS", dry_run=False)
    filtered_dates = set(generate_monthly_sessions(900101, 2026, 4)["session_date"])

    assert "2026-04-03" in baseline_dates
    assert "2026-04-06" in baseline_dates
    assert "2026-04-03" not in filtered_dates
    assert "2026-04-06" not in filtered_dates


def test_imported_nust_exclusions_remove_may_recess_and_holiday_from_sessions(monkeypatch):
    _reset_minimal_session_data()
    monkeypatch.setattr("app.academic_calendar_service._backup", lambda prefix: {"performed": True, "mode": "sqlite", "safe_message": "backup", "path": "backup.db"})
    monkeypatch.setattr("app.academic_calendar_service.log_audit_event", lambda *args, **kwargs: None)
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES
                (101, 301, 'Tuesday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1),
                (101, 301, 'Wednesday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1),
                (101, 301, 'Thursday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1),
                (101, 301, 'Friday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1)
            """
        )

    import_nust_2026_exclusions(confirm_phrase="IMPORT NUST EXCLUSIONS", dry_run=False)
    filtered_dates = set(generate_monthly_sessions(900101, 2026, 5)["session_date"])

    assert "2026-05-26" not in filtered_dates
    assert "2026-05-27" not in filtered_dates
    assert "2026-05-28" not in filtered_dates
    assert "2026-05-29" not in filtered_dates


def test_custom_date_range_uses_selected_dates_and_applies_nust_exclusions(monkeypatch):
    _reset_minimal_session_data()
    monkeypatch.setattr("app.academic_calendar_service._backup", lambda prefix: {"performed": True, "mode": "sqlite", "safe_message": "backup", "path": "backup.db"})
    monkeypatch.setattr("app.academic_calendar_service.log_audit_event", lambda *args, **kwargs: None)
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES
                (101, 301, 'Friday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1),
                (101, 301, 'Monday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1),
                (101, 301, 'Tuesday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1)
            """
        )
    import_nust_2026_exclusions(confirm_phrase="IMPORT NUST EXCLUSIONS", dry_run=False)

    period = resolve_custom_generation_period(date(2026, 4, 3), date(2026, 4, 14))
    sessions = generate_sessions_for_period(900101, period)
    dates = set(sessions["session_date"])

    assert "2026-04-03" not in dates
    assert "2026-04-06" not in dates
    assert "2026-04-07" in dates
    assert all("2026-04-03" <= session_date <= "2026-04-14" for session_date in dates)
    assert sessions.attrs["generation_period_mode"] == "custom"
