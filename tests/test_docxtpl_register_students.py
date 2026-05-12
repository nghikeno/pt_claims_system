import pandas as pd

from app.course_group_service import create_course, create_lecturer_group
from app.database import get_connection
from app.dev_reset import dev_reset
from app.lecturer_service import create_lecturer
from app_docxtpl.context_builders import build_register_page_contexts


def setup_register_student_data():
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
    with get_connection() as conn:
        group_id = conn.execute(
            "SELECT id FROM student_groups WHERE group_name = 'LONIA_GROUP2_FT_SEM1_2026'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)",
            ("226173453", "Haukongo", "JL", "Haukongo JL"),
        )
        active_student_id = conn.execute("SELECT id FROM students WHERE student_number = '226173453'").fetchone()["id"]
        conn.execute(
            "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, 1)",
            ("2261755170", "Venasius", "FPN", "Venasius FPN"),
        )
        inactive_student_id = conn.execute("SELECT id FROM students WHERE student_number = '2261755170'").fetchone()["id"]
        conn.execute(
            "INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 1)",
            (active_student_id, group_id),
        )
        conn.execute(
            "INSERT INTO group_enrolments (student_id, group_id, active) VALUES (?, ?, 0)",
            (inactive_student_id, group_id),
        )


def sessions_df():
    return pd.DataFrame(
        [
            {
                "lecturer_name": "Lonia Lecturer",
                "staff_number": "300001",
                "faculty": "Computing and Informatics",
                "department": "Informatics",
                "course_name": "Test Student Skills",
                "course_code": "TST999S",
                "group_name": "LONIA_GROUP2_FT_SEM1_2026",
                "campus": "Windhoek Main Campus",
                "session_date": "2026-02-02",
                "start_time": "08:00",
                "end_time": "09:00",
            }
        ]
    )


def test_register_context_includes_only_active_students_for_group():
    setup_register_student_data()

    contexts = build_register_page_contexts(sessions_df(), 2026, 2)
    students = contexts[0]["students"]

    assert any(student["student_number"] == "226173453" for student in students)
    assert all(student["student_number"] != "2261755170" for student in students)
