from pathlib import Path

import pandas as pd
import pytest

from app.database import get_connection, init_db
from app.import_master_data import import_master_data
from app.master_data_template import SHEET_COLUMNS, generate_master_data_template
from app.seed_data import seed_database


@pytest.fixture(autouse=True)
def seeded_database():
    seed_database()


def test_master_data_template_is_generated(tmp_path):
    output_path = tmp_path / "master_data_template.xlsx"

    generated_path = generate_master_data_template(output_path)

    assert generated_path.exists()


def test_workbook_contains_all_required_sheets(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")
    workbook = pd.read_excel(output_path, sheet_name=None)

    assert set(SHEET_COLUMNS).issubset(set(workbook))
    assert "Instructions" in workbook
    assert "Data_Dictionary" in workbook
    assert "Allowed_Values" in workbook


def test_master_data_template_contains_instructions_data_dictionary_and_allowed_values(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")
    workbook = pd.read_excel(output_path, sheet_name=None)

    assert "Do not use real bank details" in " ".join(workbook["Instructions"].astype(str).values.flatten())
    assert set(["sheet_name", "column_name", "required", "description", "example", "notes"]).issubset(
        workbook["Data_Dictionary"].columns
    )
    assert "day_of_week" in set(workbook["Allowed_Values"]["field"])


def test_workbook_contains_required_columns(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")
    workbook = pd.read_excel(output_path, sheet_name=None)

    for sheet_name, columns in SHEET_COLUMNS.items():
        assert list(workbook[sheet_name].columns) == columns


def test_importing_workbook_succeeds(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    summary = import_master_data(output_path)

    assert summary["lecturers"]["inserted"] == 1
    assert summary["students"]["inserted"] == 2
    with get_connection() as conn:
        student_count = conn.execute("SELECT COUNT(*) AS count FROM students").fetchone()["count"]
        enrolment_count = conn.execute("SELECT COUNT(*) AS count FROM group_enrolments").fetchone()["count"]
    assert student_count == 2
    assert enrolment_count == 2


def test_dry_run_import_does_not_change_database_row_counts(tmp_path):
    from app.import_master_data import import_master_data

    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")
    with get_connection() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ["lecturers", "courses", "students", "group_enrolments", "timetable_entries"]
        }

    summary = import_master_data(output_path, dry_run=True)

    with get_connection() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ["lecturers", "courses", "students", "group_enrolments", "timetable_entries"]
        }
    assert summary["students"]["inserted"] == 2
    assert before == after


def test_importing_workbook_twice_does_not_create_duplicates(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    import_master_data(output_path)
    import_master_data(output_path)

    with get_connection() as conn:
        student_count = conn.execute("SELECT COUNT(*) AS count FROM students").fetchone()["count"]
        enrolment_count = conn.execute("SELECT COUNT(*) AS count FROM group_enrolments").fetchone()["count"]
        timetable_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM timetable_entries te
            JOIN lecturers l ON l.id = te.lecturer_id
            JOIN student_groups sg ON sg.id = te.group_id
            JOIN courses c ON c.id = sg.course_id
            WHERE l.staff_number = 'DUMMY-LECT-0001'
              AND c.course_code = 'CUS411S'
              AND (
                (sg.group_name = 'Group 1' AND te.day_of_week = 'Monday' AND te.start_time = '08:00' AND te.end_time = '10:00')
                OR
                (sg.group_name = 'Group 2' AND te.day_of_week = 'Tuesday' AND te.start_time = '10:00' AND te.end_time = '12:00')
              )
            """
        ).fetchone()["count"]

    assert student_count == 2
    assert enrolment_count == 2
    assert timetable_count == 2


def test_duplicate_student_enrolment_is_not_created(tmp_path):
    output_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")
    workbook = pd.read_excel(output_path, sheet_name=None)
    workbook["Group_Enrolments"] = pd.concat(
        [workbook["Group_Enrolments"], workbook["Group_Enrolments"].iloc[[0]]],
        ignore_index=True,
    )
    duplicate_path = tmp_path / "duplicate_enrolment.xlsx"
    with pd.ExcelWriter(duplicate_path, engine="openpyxl") as writer:
        for sheet_name, df in workbook.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    import_master_data(duplicate_path)

    with get_connection() as conn:
        enrolment_count = conn.execute("SELECT COUNT(*) AS count FROM group_enrolments").fetchone()["count"]

    assert enrolment_count == 2
