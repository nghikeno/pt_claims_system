from pathlib import Path

import pytest

from app.config import DB_PATH
from app.course_group_service import create_course, create_lecturer_group
from app.database import get_connection
from app.dev_reset import dev_reset
from app.lecturer_service import create_lecturer
from app.student_service import (
    deactivate_enrolment,
    export_student_enrolments_to_csv,
    get_group_for_student_upload,
    import_students_for_group,
    list_student_enrolments,
    reactivate_enrolment,
    validate_student_import,
)
from app.student_word_import import ParsedAttendanceSheet


def setup_student_dependencies():
    dev_reset()
    create_lecturer(
        {
            "staff_number": "300001",
            "title": "Ms",
            "full_name": "Lonia Lecturer",
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
            "group_name": "LONIA_GROUP2_FT_SEM1_2026",
            "campus": "Windhoek Main Campus",
            "study_mode": "Full-time",
            "active": "Yes",
        }
    )
    return get_group_for_student_upload("300001", "TST999S", group_id_for("LONIA_GROUP2_FT_SEM1_2026"))


def group_id_for(group_name: str) -> int:
    with get_connection() as conn:
        return int(conn.execute("SELECT id FROM student_groups WHERE group_name = ?", (group_name,)).fetchone()["id"])


def parsed_sheet(course_code="TST999S", duplicate=False) -> ParsedAttendanceSheet:
    students = [
        {"student_number": "226173453", "surname": "Haukongo", "initials": "JL", "full_name": "Haukongo JL"},
        {"student_number": "2261755170", "surname": "Venasius", "initials": "FPN", "full_name": "Venasius FPN"},
    ]
    if duplicate:
        students.append({"student_number": "226173453", "surname": "Other", "initials": "O", "full_name": "Other O"})
    return ParsedAttendanceSheet(
        source_name="attendance.docx",
        header={"course_code": course_code, "group_label": "2"},
        students=students,
    )


def test_validation_rejects_missing_target_group():
    setup_student_dependencies()

    is_valid, errors, _warnings, _skipped = validate_student_import(parsed_sheet(), "300001", "TST999S", None)

    assert is_valid is False
    assert "Target group must be selected." in errors


def test_validation_warns_but_allows_word_course_mismatch_after_group_mapping_confirmation():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")

    is_valid, errors, warnings, _skipped = validate_student_import(
        parsed_sheet(course_code="ICT521S"),
        "300001",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
    )

    assert is_valid is True
    assert errors == []
    assert any("does not match selected database course" in warning for warning in warnings)


def test_validation_rejects_group_not_belonging_to_selected_lecturer():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")

    is_valid, errors, _warnings, _skipped = validate_student_import(
        parsed_sheet(),
        "999999",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
    )

    assert is_valid is False
    assert any("Target group must exist" in error for error in errors)


def test_validation_flags_duplicate_student_number():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")

    is_valid, errors, _warnings, _skipped = validate_student_import(
        parsed_sheet(duplicate=True),
        "300001",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
    )

    assert is_valid is False
    assert "Duplicate student number in uploaded file: 226173453" in errors


def test_validation_rejects_bank_related_text():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    parsed = parsed_sheet()
    parsed.header["note"] = "bank account number"

    is_valid, errors, _warnings, _skipped = validate_student_import(
        parsed,
        "300001",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
    )

    assert is_valid is False
    assert "Bank details must not be imported." in errors


def test_validation_skips_header_time_contaminant_rows():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    parsed = parsed_sheet()
    parsed.students.append(
        {
            "student_number": "18402000",
            "surname": "STUDENT SURNAME & INIT...",
            "initials": "TIME:",
            "full_name": "STUDENT SURNAME & INIT... TIME:",
        }
    )

    is_valid, errors, _warnings, skipped = validate_student_import(
        parsed,
        "300001",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
    )

    assert is_valid is True
    assert errors == []
    assert any(row["reason"] in {"Header row", "Time row", "Invalid student number"} for row in skipped)


def test_import_inserts_students_and_group_enrolments_and_backup():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_student_import_*.db")) if backup_dir.exists() else set()

    summary = import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)

    assert summary["students_inserted"] == 2
    assert summary["enrolments_inserted"] == 2
    assert len(list_student_enrolments(staff_number="300001")) == 2
    after = set(backup_dir.glob("pt_claims_before_student_import_*.db"))
    assert after - before


def test_import_does_not_duplicate_existing_enrolments():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)

    summary = import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)

    assert summary["enrolments_already_existing"] == 2
    assert len(list_student_enrolments(staff_number="300001")) == 2


def test_import_reactivates_inactive_enrolment():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)
    enrolment_id = int(list_student_enrolments(staff_number="300001").iloc[0]["enrolment_id"])
    deactivate_enrolment(enrolment_id)

    summary = import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)

    assert summary["enrolments_reactivated"] == 1


def test_import_requires_confirmation_for_existing_student_name_update():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)
    changed = parsed_sheet()
    changed.students[0]["surname"] = "Changed"

    is_valid, errors, _warnings, _skipped = validate_student_import(
        changed,
        "300001",
        "TST999S",
        group_id,
        confirm_group_mapping=True,
        allow_student_updates=False,
    )

    assert is_valid is False
    assert any("Confirm updates before import" in error for error in errors)


def test_deactivate_and_reactivate_enrolment_create_backups():
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)
    enrolment_id = int(list_student_enrolments(staff_number="300001").iloc[0]["enrolment_id"])
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_student_enrolment_update_*.db"))

    inactive = deactivate_enrolment(enrolment_id)
    active = reactivate_enrolment(enrolment_id)

    assert inactive["active"] == 0
    assert active["active"] == 1
    after = set(backup_dir.glob("pt_claims_before_student_enrolment_update_*.db"))
    assert len(after - before) >= 2


def test_enrolment_export_works(tmp_path):
    setup_student_dependencies()
    group_id = group_id_for("LONIA_GROUP2_FT_SEM1_2026")
    import_students_for_group(parsed_sheet(), "300001", "TST999S", group_id, confirm_group_mapping=True)
    output = tmp_path / "enrolments.csv"

    path = export_student_enrolments_to_csv(output)

    assert path == output
    assert "226173453" in output.read_text(encoding="utf-8")
