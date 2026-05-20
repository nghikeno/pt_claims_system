from datetime import date
from pathlib import Path

import pandas as pd

from app.database import get_connection, init_db
from app.generation_period_service import resolve_custom_generation_period
from app.preclaim_verification_service import build_preclaim_verification, build_preclaim_verification_for_period, export_preclaim_verification_report


def _reset_preclaim_db(
    *,
    lecturer_active: int = 1,
    with_group: bool = True,
    with_timetable: bool = True,
    with_enrolments: bool = True,
    contract_start: str = "2026-01-01",
    contract_end: str = "2026-12-31",
    clash: bool = False,
) -> None:
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
            VALUES (1, '900001', 'Ms', 'Preclaim Lecturer', 'M', 'SECRET-ID', 'SECRET-PAYE', 'Address', '081', 440, 'Campus', ?, ?, ?)
            """,
            (contract_start, contract_end, lecturer_active),
        )
        conn.execute(
            """
            INSERT INTO courses (id, course_code, course_name, faculty, department, budget_allocation, active)
            VALUES (1, 'PRE101', 'Preclaim Course', 'Faculty', 'Department', 'BUD', 1)
            """
        )
        if with_group:
            conn.execute(
                """
                INSERT INTO student_groups (id, group_name, course_id, lecturer_id, campus, study_mode, active)
                VALUES (1, 'PRE_GROUP', 1, 1, 'Campus', 'Full-time', 1)
                """
            )
        if with_timetable and with_group:
            conn.execute(
                """
                INSERT INTO timetable_entries (
                    lecturer_id, group_id, day_of_week, start_time, end_time,
                    effective_start_date, effective_end_date, active
                )
                VALUES (1, 1, 'Monday', '10:00', '11:00', '2026-11-01', '2026-11-30', 1)
                """
            )
            if clash:
                conn.execute(
                    """
                    INSERT INTO timetable_entries (
                        lecturer_id, group_id, day_of_week, start_time, end_time,
                        effective_start_date, effective_end_date, active
                    )
                    VALUES (1, 1, 'Monday', '10:30', '11:30', '2026-11-01', '2026-11-30', 1)
                    """
                )
        if with_enrolments and with_group:
            conn.execute(
                "INSERT INTO students (id, student_number, surname, initials, full_name, active) VALUES (1, 'STU1', 'Demo', 'A', 'Demo A', 1)"
            )
            conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (1, 1, 1)")


def test_preclaim_verification_passes_for_complete_month():
    _reset_preclaim_db()

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "PASS"
    assert result["blockers"] == []
    assert result["summary"]["total_claimable_sessions"] > 0
    assert result["summary"]["total_claimable_hours"] > 0


def test_inactive_lecturer_blocks_verification():
    _reset_preclaim_db(lecturer_active=0)

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "BLOCK"
    assert "Lecturer is inactive." in result["blockers"]


def test_no_active_groups_blocks_verification():
    _reset_preclaim_db(with_group=False, with_timetable=False, with_enrolments=False)

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "BLOCK"
    assert "No active lecturer-scoped groups exist for this lecturer." in result["blockers"]


def test_no_timetable_entries_blocks_verification():
    _reset_preclaim_db(with_timetable=False)

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "BLOCK"
    assert "No active timetable entries exist for this lecturer." in result["blockers"]


def test_zero_enrolments_warns():
    _reset_preclaim_db(with_enrolments=False)

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "WARN"
    assert "One or more active groups have zero active enrolments." in result["warnings"]


def test_month_outside_contract_blocks():
    _reset_preclaim_db(contract_start="2026-01-01", contract_end="2026-01-31")

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "BLOCK"
    assert "Selected month is completely outside the lecturer contract period." in result["blockers"]


def test_partial_contract_overlap_warns():
    _reset_preclaim_db(contract_start="2026-11-15", contract_end="2026-12-31")

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "WARN"
    assert "Selected month only partially overlaps the lecturer contract period." in result["warnings"]


def test_clashes_block_verification():
    _reset_preclaim_db(clash=True)

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] == "BLOCK"
    assert "Timetable clashes exist in generated sessions." in result["blockers"]


def test_zero_generated_sessions_warns():
    _reset_preclaim_db(contract_start="2026-11-01", contract_end="2026-11-01")

    result = build_preclaim_verification("900001", 2026, 11)

    assert result["status"] in {"WARN", "BLOCK"}
    assert "Generated session count is zero." in result["warnings"]


def test_export_preclaim_report_excludes_sensitive_fields(tmp_path):
    _reset_preclaim_db()
    result = build_preclaim_verification("900001", 2026, 11)
    result["tables"]["sensitive_check"] = pd.DataFrame(
        [{"staff_number": "900001", "id_or_passport_number": "SECRET-ID", "paye_number": "SECRET-PAYE"}]
    )

    output = export_preclaim_verification_report(result, output_dir=tmp_path)
    text = Path(output).read_text(encoding="utf-8-sig")

    assert "SECRET-ID" not in text
    assert "SECRET-PAYE" not in text
    assert "password_hash" not in text


def test_preclaim_reports_applied_calendar_exclusions_and_suspicious_enrolments():
    _reset_preclaim_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (1, 1, 'Tuesday', '10:00', '11:00', '2026-05-01', '2026-05-31', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO academic_calendar (
                title, start_date, end_date, calendar_type, action, allow_override,
                scope_type, exclude_from_claims_and_registers, active
            )
            VALUES ('Institutional Recess', '2026-05-26', '2026-05-27', 'academic_recess', 'exclude', 0, 'all', 1, 1)
            """
        )
        conn.execute(
            "INSERT INTO students (id, student_number, surname, initials, full_name, active) VALUES (2, '18402000', 'STUDENT SURNAME & INIT...', 'TIME:', 'STUDENT SURNAME & INIT... TIME:', 1)"
        )
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (2, 1, 1)")

    result = build_preclaim_verification("900001", 2026, 5)

    assert "One or more enrolments look like imported header rows." in result["warnings"]
    assert result["summary"]["applied_calendar_exclusion_count"] == 1
    assert "2026-05-26" in set(result["tables"]["excluded_session_details"]["session_date"])
    assert result["tables"]["applied_calendar_exclusions"].iloc[0]["title"] == "Institutional Recess"
    assert result["tables"]["suspicious_enrolments"].iloc[0]["student_number"] == "18402000"


def test_preclaim_custom_range_uses_same_session_period():
    _reset_preclaim_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (
                lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (1, 1, 'Monday', '10:00', '11:00', '2026-04-01', '2026-04-30', 1)
            """
        )
    period = resolve_custom_generation_period(date(2026, 4, 6), date(2026, 4, 13))

    result = build_preclaim_verification_for_period("900001", 2026, 4, period)
    session_dates = set(result["tables"]["generated_sessions"]["session_date"])

    assert result["summary"]["generation_period_mode"] == "custom"
    assert result["summary"]["claim_period"] == "2026-04-06 to 2026-04-13"
    assert session_dates == {"2026-04-06", "2026-04-13"}
