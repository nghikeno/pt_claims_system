from __future__ import annotations

import sqlite3

import pytest

from app.course_group_service import (
    course_exists,
    create_course,
    create_group,
    create_lecturer_group,
    find_duplicate_groups,
    find_duplicate_lecturer_groups,
    get_course_by_code,
    get_group,
    group_exists,
    lecturer_group_exists,
    list_groups_for_lecturer,
    list_lecturer_groups,
    list_groups,
    normalise_editable_group_name,
    update_course,
    update_group,
    update_lecturer_group,
    validate_course_data,
    validate_group_data,
    validate_lecturer_group_data,
)
from app.database import get_connection, init_db
from app.dev_reset import dev_reset
from app.lecturer_service import create_lecturer


def valid_course_data(course_code="ABC123S") -> dict:
    return {
        "course_code": course_code,
        "course_name": "Administrative Basics",
        "faculty": "Computing and Informatics",
        "department": "Informatics",
        "budget_allocation": "0183-0102",
        "active": "Yes",
    }


def valid_group_data(group_name="ABC Group A", course_code="ABC123S") -> dict:
    return {
        "group_name": group_name,
        "course_code": course_code,
        "campus": "Windhoek Main Campus",
        "study_mode": "Part-time",
        "active": "Yes",
    }


def valid_lecturer_data(staff_number="300001", full_name="Victoria Lecturer") -> dict:
    return {
        "staff_number": staff_number,
        "title": "Ms",
        "full_name": full_name,
        "highest_qualification": "Dummy Qualification",
        "id_or_passport_number": "DUMMY-ID-300001",
        "paye_number": "DUMMY-PAYE-300001",
        "physical_address": "P.O. Box 000, Windhoek",
        "contact_number": "0810000002",
        "tariff_per_hour": 410,
        "campus": "Windhoek Main Campus",
        "contract_start_date": "2026-02-01",
        "contract_end_date": "2026-06-05",
        "active": "Yes",
    }


def valid_lecturer_group_data(staff_number="300001", course_code="ABC123S", group_name="VICTORIA_GREEN_FT_SEM1_2026") -> dict:
    return {
        "staff_number": staff_number,
        "course_code": course_code,
        "group_name": group_name,
        "campus": "Windhoek Main Campus",
        "study_mode": "Full-time",
        "active": "Yes",
    }


def assert_invalid(result, expected_error):
    is_valid, errors = result
    assert is_valid is False
    assert any(expected_error in error for error in errors)


def test_student_groups_has_nullable_lecturer_id_column_after_init():
    dev_reset()
    init_db()
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(student_groups)").fetchall()]

    assert "lecturer_id" in columns


def test_valid_course_passes_validation():
    assert validate_course_data(valid_course_data()) == (True, [])


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("course_code", "Course code is required."),
        ("course_name", "Course name is required."),
        ("budget_allocation", "Budget allocation is required."),
    ],
)
def test_course_required_fields_fail_validation(field, expected):
    data = valid_course_data()
    data[field] = ""

    assert_invalid(validate_course_data(data), expected)


def test_course_validation_rejects_bank_detail_text():
    data = valid_course_data()
    data["department"] = "First National Bank"

    assert_invalid(validate_course_data(data), "Bank details must not be stored in this system.")


def test_create_course_inserts_and_course_exists_works():
    dev_reset()
    created = create_course(valid_course_data())
    fetched = get_course_by_code("ABC123S")

    assert created["course_code"] == "ABC123S"
    assert fetched["course_name"] == "Administrative Basics"
    assert course_exists("ABC123S") is True
    assert course_exists("MISSING") is False


def test_create_course_rejects_duplicate_course_code():
    dev_reset()
    create_course(valid_course_data())

    with pytest.raises(ValueError, match="already exists"):
        create_course(valid_course_data())


def test_update_course_updates_existing_course():
    dev_reset()
    create_course(valid_course_data())
    updated = update_course(
        "ABC123S",
        valid_course_data("IGNORED") | {
            "course_name": "Updated Course",
            "faculty": "Updated Faculty",
            "department": "Updated Department",
            "budget_allocation": "9999-0000",
            "active": False,
        },
    )

    assert updated["course_code"] == "ABC123S"
    assert updated["course_name"] == "Updated Course"
    assert updated["faculty"] == "Updated Faculty"
    assert updated["department"] == "Updated Department"
    assert updated["budget_allocation"] == "9999-0000"
    assert updated["active"] == 0


def test_valid_group_passes_validation():
    dev_reset()
    create_course(valid_course_data())

    assert validate_group_data(valid_group_data()) == (True, [])


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("group_name", "Group name is required."),
        ("course_code", "Course code is required."),
    ],
)
def test_group_required_fields_fail_validation(field, expected):
    dev_reset()
    create_course(valid_course_data())
    data = valid_group_data()
    data[field] = ""

    assert_invalid(validate_group_data(data), expected)


def test_group_validation_rejects_non_existing_course_code():
    dev_reset()

    assert_invalid(validate_group_data(valid_group_data()), "Course code must reference an existing course.")


def test_group_validation_rejects_invalid_study_mode():
    dev_reset()
    create_course(valid_course_data())
    data = valid_group_data()
    data["study_mode"] = "Weekend"

    assert_invalid(validate_group_data(data), "Study mode must be one of")


def test_group_validation_rejects_bank_detail_text():
    dev_reset()
    create_course(valid_course_data())
    data = valid_group_data()
    data["campus"] = "Bank account holder"

    assert_invalid(validate_group_data(data), "Bank details must not be stored in this system.")


def test_create_group_inserts_and_group_exists_works():
    dev_reset()
    create_course(valid_course_data())
    created = create_group(valid_group_data())
    fetched = get_group("ABC Group A", "ABC123S")

    assert created["group_name"] == "ABC Group A"
    assert fetched["course_code"] == "ABC123S"
    assert group_exists("ABC Group A", "ABC123S") is True
    assert group_exists("Missing Group", "ABC123S") is False


def test_create_group_rejects_duplicate_group_name_for_same_course():
    dev_reset()
    create_course(valid_course_data())
    create_group(valid_group_data())

    with pytest.raises(ValueError, match="already exists for the selected course"):
        create_group(valid_group_data())


def test_create_group_allows_same_group_name_for_different_courses():
    dev_reset()
    create_course(valid_course_data("ABC123S"))
    create_course(valid_course_data("DEF123S"))

    create_group(valid_group_data("Shared Group", "ABC123S"))
    create_group(valid_group_data("Shared Group", "DEF123S"))
    groups = list_groups()

    assert len(groups[groups["group_name"] == "Shared Group"]) == 2


def test_update_group_updates_campus_study_mode_and_active():
    dev_reset()
    create_course(valid_course_data())
    create_group(valid_group_data())

    updated = update_group(
        "ABC Group A",
        "ABC123S",
        valid_group_data("IGNORED", "IGNORED") | {
            "campus": "Distance / Online",
            "study_mode": "Distance / Online",
            "active": False,
        },
    )

    assert updated["group_name"] == "ABC Group A"
    assert updated["course_code"] == "ABC123S"
    assert updated["campus"] == "Distance / Online"
    assert updated["study_mode"] == "Distance / Online"
    assert updated["active"] == 0


def test_find_duplicate_groups_detects_manually_existing_duplicates(monkeypatch, tmp_path):
    db_path = tmp_path / "duplicates.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                course_name TEXT NOT NULL
            );
            CREATE TABLE student_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                lecturer_id INTEGER,
                campus TEXT,
                study_mode TEXT,
                active INTEGER
            );
            INSERT INTO courses (id, course_code, course_name)
            VALUES (1, 'ABC123S', 'Administrative Basics');
            INSERT INTO student_groups (group_name, course_id, campus, study_mode, active)
            VALUES
                ('ABC Group A', 1, 'Windhoek Main Campus', 'Part-time', 1),
                ('ABC Group A', 1, 'Windhoek Main Campus', 'Part-time', 1),
                ('ABC Group B', 1, 'Windhoek Main Campus', 'Part-time', 1);
            """
        )

    def temp_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.course_group_service.init_db", lambda: None)
    monkeypatch.setattr("app.course_group_service.get_runtime_connection", temp_connection)

    duplicates = find_duplicate_groups()

    assert duplicates.to_dict("records") == [{"course_code": "ABC123S", "group_name": "ABC Group A", "count": 2}]


def test_create_lecturer_group_creates_group_linked_to_lecturer_and_course():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())

    created = create_lecturer_group(valid_lecturer_group_data())
    listed = list_lecturer_groups("300001")

    assert created["staff_number"] == "300001"
    assert created["lecturer_name"] == "Victoria Lecturer"
    assert created["course_code"] == "ABC123S"
    assert created["group_name"] == "VICTORIA_GREEN_FT_SEM1_2026"
    assert listed.iloc[0]["group_name"] == "VICTORIA_GREEN_FT_SEM1_2026"
    assert lecturer_group_exists("300001", "ABC123S", "VICTORIA_GREEN_FT_SEM1_2026") is True


def test_create_lecturer_group_rejects_missing_or_unknown_staff_number():
    dev_reset()
    create_course(valid_course_data())
    missing = valid_lecturer_group_data(staff_number="")
    unknown = valid_lecturer_group_data(staff_number="399999")

    assert_invalid(validate_lecturer_group_data(missing), "Staff number is required.")
    assert_invalid(validate_lecturer_group_data(unknown), "Staff number must reference an existing lecturer.")
    with pytest.raises(ValueError, match="Staff number must reference an existing lecturer"):
        create_lecturer_group(unknown)


def test_create_lecturer_group_rejects_unknown_course_code():
    dev_reset()
    create_lecturer(valid_lecturer_data())
    data = valid_lecturer_group_data(course_code="MISSING")

    assert_invalid(validate_lecturer_group_data(data), "Course code must reference an existing course.")
    with pytest.raises(ValueError, match="Course code must reference an existing course"):
        create_lecturer_group(data)


def test_validate_lecturer_group_rejects_blank_generation_inputs():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    data = valid_lecturer_group_data() | {"group_label": "", "semester": "", "year": "26"}

    is_valid, errors = validate_lecturer_group_data(data)

    assert is_valid is False
    assert "Group label is required." in errors
    assert "Semester is required." in errors
    assert "Year must be a valid four-digit year." in errors


def test_create_lecturer_group_rejects_duplicate_same_lecturer_course_and_group():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    create_lecturer_group(valid_lecturer_group_data())

    with pytest.raises(ValueError, match="already exists for the selected lecturer and course"):
        create_lecturer_group(valid_lecturer_group_data())


def test_create_lecturer_group_allows_same_group_name_for_different_lecturers():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data("300001", "Victoria Lecturer"))
    create_lecturer(valid_lecturer_data("300002", "Matheus Lecturer"))

    create_lecturer_group(valid_lecturer_group_data("300001", "ABC123S", "SHARED_GROUP"))
    create_lecturer_group(valid_lecturer_group_data("300002", "ABC123S", "SHARED_GROUP"))
    groups = list_lecturer_groups()

    assert len(groups[groups["group_name"] == "SHARED_GROUP"]) == 2


def test_update_lecturer_group_updates_campus_study_mode_and_active():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    create_lecturer_group(valid_lecturer_group_data())

    updated = update_lecturer_group(
        "300001",
        "ABC123S",
        "VICTORIA_GREEN_FT_SEM1_2026",
        {"campus": "Distance / Online", "study_mode": "Distance / Online", "active": False},
    )

    assert updated["campus"] == "Distance / Online"
    assert updated["study_mode"] == "Distance / Online"
    assert updated["active"] == 0


def test_update_lecturer_group_can_change_group_name_and_preserve_identity_links():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    create_lecturer_group(valid_lecturer_group_data())

    updated = update_lecturer_group(
        "300001",
        "ABC123S",
        "VICTORIA_GREEN_FT_SEM1_2026",
        valid_lecturer_group_data(group_name=" VICTORIA_BLUE_FT_SEM1_2026 "),
    )

    assert updated["group_name"] == "VICTORIA_BLUE_FT_SEM1_2026"
    assert updated["staff_number"] == "300001"
    assert updated["course_code"] == "ABC123S"
    assert lecturer_group_exists("300001", "ABC123S", "VICTORIA_BLUE_FT_SEM1_2026") is True
    assert lecturer_group_exists("300001", "ABC123S", "VICTORIA_GREEN_FT_SEM1_2026") is False


def test_update_lecturer_group_blocks_duplicate_group_name_for_same_lecturer_course():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    create_lecturer_group(valid_lecturer_group_data(group_name="GROUP_A"))
    create_lecturer_group(valid_lecturer_group_data(group_name="GROUP_B"))

    with pytest.raises(ValueError, match="already exists"):
        update_lecturer_group("300001", "ABC123S", "GROUP_A", valid_lecturer_group_data(group_name="GROUP_B"))


def test_update_lecturer_group_allows_same_group_name_for_different_lecturer():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data("300001", "Victoria Lecturer"))
    create_lecturer(valid_lecturer_data("300002", "Matheus Lecturer"))
    create_lecturer_group(valid_lecturer_group_data("300001", "ABC123S", "GROUP_A"))
    create_lecturer_group(valid_lecturer_group_data("300002", "ABC123S", "GROUP_B"))

    updated = update_lecturer_group("300002", "ABC123S", "GROUP_B", valid_lecturer_group_data("300002", "ABC123S", "GROUP_A"))

    assert updated["group_name"] == "GROUP_A"
    assert list_lecturer_groups(staff_number="300001").iloc[0]["group_name"] == "GROUP_A"
    assert list_lecturer_groups(staff_number="300002").iloc[0]["group_name"] == "GROUP_A"


def test_update_lecturer_group_does_not_affect_generic_groups():
    dev_reset()
    create_course(valid_course_data())
    create_lecturer(valid_lecturer_data())
    create_group(valid_group_data("GENERIC_GROUP", "ABC123S"))
    create_lecturer_group(valid_lecturer_group_data(group_name="SCOPED_GROUP"))

    update_lecturer_group("300001", "ABC123S", "SCOPED_GROUP", valid_lecturer_group_data(group_name="RENAMED_SCOPED_GROUP"))

    assert group_exists("GENERIC_GROUP", "ABC123S") is True
    assert lecturer_group_exists("300001", "ABC123S", "RENAMED_SCOPED_GROUP") is True


def test_normalise_editable_group_name_trims_value():
    assert normalise_editable_group_name("  GROUP_A  ") == "GROUP_A"


def test_list_lecturer_groups_filters_by_staff_number_and_course_code():
    dev_reset()
    create_course(valid_course_data("ABC123S"))
    create_course(valid_course_data("DEF123S"))
    create_lecturer(valid_lecturer_data("300001", "Victoria Lecturer"))
    create_lecturer(valid_lecturer_data("300002", "Matheus Lecturer"))
    create_lecturer_group(valid_lecturer_group_data("300001", "ABC123S", "GROUP_A"))
    create_lecturer_group(valid_lecturer_group_data("300001", "DEF123S", "GROUP_B"))
    create_lecturer_group(valid_lecturer_group_data("300002", "ABC123S", "GROUP_C"))

    by_lecturer = list_lecturer_groups(staff_number="300001")
    by_course = list_lecturer_groups(course_code="ABC123S")

    assert set(by_lecturer["group_name"]) == {"GROUP_A", "GROUP_B"}
    assert set(by_course["group_name"]) == {"GROUP_A", "GROUP_C"}


def test_list_groups_for_lecturer_returns_only_selected_lecturer_groups():
    dev_reset()
    create_course(valid_course_data("ABC123S"))
    create_course(valid_course_data("DEF123S"))
    create_lecturer(valid_lecturer_data("300001", "Alvina Lecturer"))
    create_lecturer(valid_lecturer_data("300002", "Mervin Lecturer"))
    create_group(valid_group_data("GENERIC_GROUP", "ABC123S"))
    create_lecturer_group(valid_lecturer_group_data("300001", "ABC123S", "ALVINA_GREEN_FT_SEM1_2026"))
    create_lecturer_group(valid_lecturer_group_data("300001", "DEF123S", "ALVINA_YELLOW_FT_SEM1_2026"))
    create_lecturer_group(valid_lecturer_group_data("300002", "ABC123S", "MERVIN_GREEN_FT_SEM1_2026"))

    groups = list_groups_for_lecturer("300001")

    assert list(groups["group_name"]) == ["ALVINA_GREEN_FT_SEM1_2026", "ALVINA_YELLOW_FT_SEM1_2026"]
    assert "staff_number" not in groups.columns
    assert "lecturer_name" not in groups.columns


def test_list_groups_for_lecturer_returns_alvina_style_groups_only():
    dev_reset()
    create_lecturer(valid_lecturer_data("1009470", "Alvina Niiro Hilifavali Hailonga"))
    create_lecturer(valid_lecturer_data("1001259", "Mervin Nolin Shaun Mokhatu"))
    create_lecturer_group(valid_lecturer_group_data("1009470", "CUS411S", "Alvin_Lunch_FT_SEM1_2026"))
    create_lecturer_group(valid_lecturer_group_data("1009470", "CUS411S", "Alvin_Yellow_FT_SEM1_2026"))
    create_lecturer_group(valid_lecturer_group_data("1001259", "CUS411S", "MERVIN_GREEN_FT_SEM1_2026"))

    alvina_groups = list_groups_for_lecturer("1009470")
    mervin_groups = list_groups_for_lecturer("1001259")

    assert list(alvina_groups["group_name"]) == ["Alvin_Lunch_FT_SEM1_2026", "Alvin_Yellow_FT_SEM1_2026"]
    assert list(mervin_groups["group_name"]) == ["MERVIN_GREEN_FT_SEM1_2026"]


def test_find_duplicate_lecturer_groups_detects_manually_existing_duplicates(monkeypatch, tmp_path):
    db_path = tmp_path / "lecturer_duplicates.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE lecturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_number TEXT NOT NULL,
                full_name TEXT NOT NULL
            );
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                course_name TEXT NOT NULL
            );
            CREATE TABLE student_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                lecturer_id INTEGER,
                campus TEXT,
                study_mode TEXT,
                active INTEGER
            );
            INSERT INTO lecturers (id, staff_number, full_name)
            VALUES (1, '300001', 'Victoria Lecturer');
            INSERT INTO courses (id, course_code, course_name)
            VALUES (1, 'ABC123S', 'Administrative Basics');
            INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES
                ('GROUP_A', 1, 1, 'Windhoek Main Campus', 'Full-time', 1),
                ('GROUP_A', 1, 1, 'Windhoek Main Campus', 'Full-time', 1);
            """
        )

    def temp_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.course_group_service.init_db", lambda: None)
    monkeypatch.setattr("app.course_group_service.get_runtime_connection", temp_connection)

    duplicates = find_duplicate_lecturer_groups()

    assert duplicates.to_dict("records") == [
        {"staff_number": "300001", "course_code": "ABC123S", "group_name": "GROUP_A", "count": 2}
    ]
