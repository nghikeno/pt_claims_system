from pathlib import Path

import pytest
import pandas as pd

from app.config import DB_PATH
from app.course_group_service import create_course, create_lecturer_group
from app.database import get_connection
from app.dev_reset import dev_reset
from app.lecturer_service import create_lecturer
from app.timetable_service import (
    create_timetable_entry,
    deactivate_timetable_entry,
    delete_timetable_entry,
    detect_timetable_overlaps,
    hard_delete_confirmation_valid,
    list_groups_for_timetable,
    list_timetable_entries,
    list_timetable_entries_for_lecturer,
    reactivate_timetable_entry,
    timetable_group_ownership_message,
    update_timetable_entry,
    validate_timetable_entry,
)


def valid_course_data(course_code="ABC123S") -> dict:
    return {
        "course_code": course_code,
        "course_name": "Administrative Basics",
        "faculty": "Computing and Informatics",
        "department": "Informatics",
        "budget_allocation": "0183-0102",
        "active": "Yes",
    }


def valid_lecturer_data(staff_number="300001", full_name="Alvina Lecturer") -> dict:
    return {
        "staff_number": staff_number,
        "title": "Ms",
        "full_name": full_name,
        "highest_qualification": "Dummy Qualification",
        "id_or_passport_number": f"DUMMY-ID-{staff_number}",
        "paye_number": f"DUMMY-PAYE-{staff_number}",
        "physical_address": "P.O. Box 000, Windhoek",
        "contact_number": "0810000002",
        "tariff_per_hour": 410,
        "campus": "Windhoek Main Campus",
        "contract_start_date": "2026-02-01",
        "contract_end_date": "2026-06-05",
        "active": "Yes",
    }


def lecturer_group_data(staff_number="300001", course_code="ABC123S", group_name="ALVINA_GREEN_FT_SEM1_2026") -> dict:
    return {
        "staff_number": staff_number,
        "course_code": course_code,
        "group_name": group_name,
        "campus": "Windhoek Main Campus",
        "study_mode": "Full-time",
        "active": "Yes",
    }


def setup_timetable_dependencies():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data("300001", "Alvina Lecturer"))
    create_lecturer(valid_lecturer_data("300002", "Mervin Lecturer"))
    create_lecturer_group(lecturer_group_data("300001", "ABC123S", "ALVINA_GREEN_FT_SEM1_2026"))
    create_lecturer_group(lecturer_group_data("300001", "ABC123S", "ALVINA_BLUE_FT_SEM1_2026"))
    create_lecturer_group(lecturer_group_data("300002", "ABC123S", "MERVIN_GREEN_PT_SEM1_2026"))


def group_id_for(staff_number: str, group_name: str) -> int:
    groups = list_groups_for_timetable(staff_number)
    return int(groups[groups["group_name"] == group_name].iloc[0]["group_id"])


def valid_entry_data(staff_number="300001", group_name="ALVINA_GREEN_FT_SEM1_2026") -> dict:
    return {
        "staff_number": staff_number,
        "group_id": group_id_for(staff_number, group_name),
        "day_of_week": "Monday",
        "start_time": "08:00",
        "end_time": "09:00",
        "effective_start_date": "2026-02-01",
        "effective_end_date": "2026-06-30",
        "active": "Yes",
    }


def test_create_timetable_entry():
    setup_timetable_dependencies()

    entry = create_timetable_entry(valid_entry_data())

    assert entry["staff_number"] == "300001"
    assert entry["group_name"] == "ALVINA_GREEN_FT_SEM1_2026"
    assert entry["day_of_week"] == "Monday"
    assert entry["start_time"] == "08:00"


def test_group_must_belong_to_selected_lecturer():
    setup_timetable_dependencies()
    data = valid_entry_data("300001")
    data["group_id"] = group_id_for("300002", "MERVIN_GREEN_PT_SEM1_2026")

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is False
    assert "Group must belong to the selected lecturer." in errors


def test_lecturer_scoped_group_listed_for_lecturer_passes_ownership_validation():
    setup_timetable_dependencies()
    data = valid_entry_data("300001", "ALVINA_GREEN_FT_SEM1_2026")

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is True
    assert "Group must belong to the selected lecturer." not in errors


def test_group_ownership_validation_allows_string_group_id():
    setup_timetable_dependencies()
    data = valid_entry_data("300001", "ALVINA_GREEN_FT_SEM1_2026")
    data["group_id"] = str(data["group_id"])

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is True
    assert errors == []


def test_group_ownership_message_identifies_real_owner_for_mismatch():
    setup_timetable_dependencies()
    other_group_id = group_id_for("300002", "MERVIN_GREEN_PT_SEM1_2026")

    message = timetable_group_ownership_message("300001", other_group_id)

    assert "Selected group belongs to 300002 - Mervin Lecturer" in message
    assert "not the selected lecturer 300001" in message


def test_generic_group_is_blocked_for_timetable_entry():
    setup_timetable_dependencies()
    with get_connection() as conn:
        course_id = conn.execute("SELECT id FROM courses WHERE course_code = 'ABC123S'").fetchone()["id"]
        cursor = conn.execute(
            """
            INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES ('GENERIC_GROUP', ?, NULL, 'Windhoek Main Campus', 'Full-time', 1)
            """,
            (course_id,),
        )
        generic_group_id = cursor.lastrowid

    is_valid, errors = validate_timetable_entry(valid_entry_data("300001") | {"group_id": generic_group_id})

    assert is_valid is False
    assert "Group must belong to the selected lecturer." in errors
    assert "not assigned to a lecturer" in timetable_group_ownership_message("300001", generic_group_id)


def test_postgresql_style_group_rows_are_normalised_for_validation(monkeypatch):
    monkeypatch.setattr(
        "app.timetable_service._group_for_lecturer",
        lambda staff_number, group_id: {
            "group_id": "9",
            "lecturer_id": "4",
            "staff_number": str(staff_number),
            "course_code": "CUS411S",
            "group_name": "ELIFAS_GREEN_FT_SEM1_2026",
        },
    )
    monkeypatch.setattr("app.timetable_service._duplicate_exists", lambda cleaned, exclude_id=None: False)
    monkeypatch.setattr("app.timetable_service.detect_timetable_overlaps", lambda data, exclude_id=None: pd.DataFrame())

    is_valid, errors = validate_timetable_entry(
        {
            "staff_number": "1009568",
            "group_id": "9",
            "day_of_week": "Monday",
            "start_time": "08:00",
            "end_time": "09:00",
            "effective_start_date": "2026-02-01",
            "effective_end_date": "2026-06-30",
            "active": True,
        }
    )

    assert is_valid is True
    assert errors == []


def test_start_time_must_be_before_end_time():
    setup_timetable_dependencies()
    data = valid_entry_data() | {"start_time": "09:00", "end_time": "08:00"}

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is False
    assert "Start time must be before end time." in errors


@pytest.mark.parametrize("value", ["17:15", "18:35", "18:40", "21:25"])
def test_institutional_five_minute_times_are_accepted(value):
    setup_timetable_dependencies()
    data = valid_entry_data() | {"start_time": value, "end_time": "23:00"}

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is True
    assert errors == []


@pytest.mark.parametrize("value", ["25:00", "18:99"])
def test_invalid_times_are_rejected(value):
    setup_timetable_dependencies()
    data = valid_entry_data() | {"start_time": value}

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is False
    assert "Start time must be a valid HH:MM time." in errors


def test_effective_start_date_must_be_before_or_equal_end_date():
    setup_timetable_dependencies()
    data = valid_entry_data() | {"effective_start_date": "2026-07-01", "effective_end_date": "2026-06-30"}

    is_valid, errors = validate_timetable_entry(data)

    assert is_valid is False
    assert "Effective start date must be before or equal to effective end date." in errors


def test_duplicate_timetable_entry_is_blocked():
    setup_timetable_dependencies()
    data = valid_entry_data()
    create_timetable_entry(data)

    with pytest.raises(ValueError, match="Duplicate timetable entry"):
        create_timetable_entry(data)


def test_same_lecturer_overlap_is_blocked():
    setup_timetable_dependencies()
    create_timetable_entry(valid_entry_data())
    overlapping = valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "08:30",
        "end_time": "09:30",
    }

    is_valid, errors = validate_timetable_entry(overlapping)

    assert is_valid is False
    assert "Overlapping timetable entry exists for this lecturer or group." in errors
    assert not detect_timetable_overlaps(overlapping).empty


def test_same_group_overlap_is_blocked():
    setup_timetable_dependencies()
    create_timetable_entry(valid_entry_data())
    overlapping = valid_entry_data() | {"start_time": "08:15", "end_time": "08:45"}

    is_valid, errors = validate_timetable_entry(overlapping)

    assert is_valid is False
    assert "Overlapping timetable entry exists for this lecturer or group." in errors


def test_non_overlapping_entries_are_allowed():
    setup_timetable_dependencies()
    create_timetable_entry(valid_entry_data())
    non_overlapping = valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    }

    is_valid, errors = validate_timetable_entry(non_overlapping)

    assert is_valid is True
    assert errors == []
    created = create_timetable_entry(non_overlapping)
    assert created["group_name"] == "ALVINA_BLUE_FT_SEM1_2026"


def test_adjacent_time_ranges_are_allowed():
    setup_timetable_dependencies()
    first = valid_entry_data() | {"start_time": "18:40", "end_time": "20:00"}
    second = valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "20:00",
        "end_time": "21:25",
    }
    create_timetable_entry(first)

    is_valid, errors = validate_timetable_entry(second)

    assert is_valid is True
    assert errors == []
    assert create_timetable_entry(second)["end_time"] == "21:25"


def test_listing_timetable_entries_joins_lecturer_course_and_group():
    setup_timetable_dependencies()
    create_timetable_entry(valid_entry_data())

    entries = list_timetable_entries(staff_number="300001")
    lecturer_entries = list_timetable_entries_for_lecturer("300001")

    assert entries.iloc[0]["lecturer_name"] == "Alvina Lecturer"
    assert entries.iloc[0]["course_code"] == "ABC123S"
    assert entries.iloc[0]["group_name"] == "ALVINA_GREEN_FT_SEM1_2026"
    assert len(lecturer_entries) == 1


def test_backup_before_timetable_save_is_created():
    setup_timetable_dependencies()
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_timetable_save_*.db")) if backup_dir.exists() else set()

    create_timetable_entry(valid_entry_data())

    after = set(backup_dir.glob("pt_claims_before_timetable_save_*.db"))
    assert after - before
    assert all(Path(path).exists() for path in after - before)


def test_update_timetable_entry_can_change_start_and_end_time():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())

    updated = update_timetable_entry(entry["id"], valid_entry_data() | {"start_time": "17:15", "end_time": "18:35"})

    assert updated["start_time"] == "17:15"
    assert updated["end_time"] == "18:35"


def test_update_timetable_entry_can_change_day_of_week_and_dates():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())

    updated = update_timetable_entry(
        entry["id"],
        valid_entry_data() | {
            "day_of_week": "Tuesday",
            "effective_start_date": "2026-03-01",
            "effective_end_date": "2026-07-31",
        },
    )

    assert updated["day_of_week"] == "Tuesday"
    assert updated["effective_start_date"] == "2026-03-01"
    assert updated["effective_end_date"] == "2026-07-31"


def test_update_timetable_entry_can_deactivate_and_reactivate():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())

    inactive = update_timetable_entry(entry["id"], valid_entry_data() | {"active": False})
    active = update_timetable_entry(entry["id"], valid_entry_data() | {"active": True})

    assert inactive["active"] == 0
    assert active["active"] == 1


def test_update_timetable_entry_blocks_overlap_with_another_entry():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    second = create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    })

    with pytest.raises(ValueError, match="Overlapping timetable entry"):
        update_timetable_entry(second["id"], valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
            "start_time": "08:30",
            "end_time": "09:30",
        })

    assert list_timetable_entries(group_id=first["group_id"]).iloc[0]["start_time"] == "08:00"


def test_update_timetable_entry_does_not_block_itself():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())

    updated = update_timetable_entry(entry["id"], valid_entry_data() | {"effective_end_date": "2026-07-31"})

    assert updated["effective_end_date"] == "2026-07-31"


def test_update_timetable_entry_blocks_duplicate_entries():
    setup_timetable_dependencies()
    create_timetable_entry(valid_entry_data())
    second_data = valid_entry_data() | {"day_of_week": "Tuesday"}
    second = create_timetable_entry(second_data)

    with pytest.raises(ValueError, match="Duplicate timetable entry"):
        update_timetable_entry(second["id"], valid_entry_data())


def test_backup_before_timetable_update_is_created():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_timetable_update_*.db")) if backup_dir.exists() else set()

    update_timetable_entry(entry["id"], valid_entry_data() | {"start_time": "17:15", "end_time": "18:35"})

    after = set(backup_dir.glob("pt_claims_before_timetable_update_*.db"))
    assert after - before


def test_deactivate_timetable_entry_sets_active_zero_for_selected_row_only():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    second = create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    })

    deactivated = deactivate_timetable_entry(first["id"])

    assert deactivated["active"] == 0
    assert list_timetable_entries(group_id=second["group_id"]).iloc[0]["active"] == 1


def test_reactivate_timetable_entry_sets_active_one_for_selected_row_only():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    second = create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    })
    deactivate_timetable_entry(first["id"])

    reactivated = reactivate_timetable_entry(first["id"])

    assert reactivated["active"] == 1
    assert list_timetable_entries(group_id=second["group_id"]).iloc[0]["active"] == 1


def test_reactivate_timetable_entry_blocks_overlap_with_active_entry():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    deactivate_timetable_entry(first["id"])
    create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "08:30",
        "end_time": "09:30",
    })

    with pytest.raises(ValueError, match="Overlapping timetable entry"):
        reactivate_timetable_entry(first["id"])


def test_inactive_entries_do_not_block_new_active_entries():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    deactivate_timetable_entry(first["id"])
    overlapping = valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "08:30",
        "end_time": "09:30",
    }

    is_valid, errors = validate_timetable_entry(overlapping)

    assert is_valid is True
    assert errors == []


def test_delete_timetable_entry_deletes_only_selected_timetable_row():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    second = create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    })

    delete_timetable_entry(first["id"])
    entries = list_timetable_entries(staff_number="300001")

    assert set(entries["id"]) == {second["id"]}
    assert len(list_groups_for_timetable("300001")) == 2


def test_delete_timetable_entry_does_not_delete_lecturers_courses_or_groups():
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())

    delete_timetable_entry(entry["id"])

    assert len(list_groups_for_timetable("300001")) == 2
    assert list_timetable_entries(staff_number="300001").empty


@pytest.mark.parametrize(
    ("action", "prefix"),
    [
        ("deactivate", "pt_claims_before_timetable_deactivate_*.db"),
        ("reactivate", "pt_claims_before_timetable_reactivate_*.db"),
        ("delete", "pt_claims_before_timetable_delete_*.db"),
    ],
)
def test_management_actions_create_action_specific_backups(action, prefix):
    setup_timetable_dependencies()
    entry = create_timetable_entry(valid_entry_data())
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob(prefix)) if backup_dir.exists() else set()

    if action == "deactivate":
        deactivate_timetable_entry(entry["id"])
    elif action == "reactivate":
        deactivate_timetable_entry(entry["id"])
        before = set(backup_dir.glob(prefix)) if backup_dir.exists() else set()
        reactivate_timetable_entry(entry["id"])
    else:
        delete_timetable_entry(entry["id"])

    after = set(backup_dir.glob(prefix))
    assert after - before


def test_list_timetable_entries_includes_active_and_inactive_records():
    setup_timetable_dependencies()
    first = create_timetable_entry(valid_entry_data())
    create_timetable_entry(valid_entry_data(group_name="ALVINA_BLUE_FT_SEM1_2026") | {
        "start_time": "09:00",
        "end_time": "10:00",
    })
    deactivate_timetable_entry(first["id"])

    entries = list_timetable_entries()

    assert set(entries["active"]) == {0, 1}


def test_hard_delete_confirmation_requires_checkbox_and_exact_phrase():
    assert hard_delete_confirmation_valid(True, "DELETE TIMETABLE ENTRY") is True
    assert hard_delete_confirmation_valid(False, "DELETE TIMETABLE ENTRY") is False
    assert hard_delete_confirmation_valid(True, "delete timetable entry") is False
