from __future__ import annotations

import json

import pandas as pd

from app.create_maria_pilot_workbook import create_maria_pilot_workbook
from app.dev_reset import dev_reset
from app.import_master_data import import_master_data
from app.session_generator import generate_monthly_sessions
from app.claim_completeness_service import audit_claim_completeness_from_data
from app_docxtpl.context_builders import build_claim_context, build_register_page_contexts


def _load_maria_sessions():
    dev_reset()
    import_master_data(create_maria_pilot_workbook())
    return generate_monthly_sessions(1008977, 2026, 4)


def test_maria_claim_context_totals_rows_and_course_post():
    sessions_df = _load_maria_sessions()
    context = build_claim_context(sessions_df, 2026, 4)

    assert context["total_hours"] == "94"
    assert context["course_post"] == "ICT521S & CUS411S"
    assert len(context["claim_rows"]) == 69
    assert any(row["group_display"] == "ICT Distance" for row in context["claim_rows"])
    assert context["title_ms_mark"] == "X"
    assert context["title_mr_mark"] == ""
    assert "bank" not in json.dumps(context).lower()


def test_claim_context_title_marks_normalize_supported_titles():
    sessions_df = _load_maria_sessions()
    cases = {
        "Ms": "title_ms_mark",
        "mr": "title_mr_mark",
        "DR": "title_dr_mark",
        " prof ": "title_prof_mark",
    }

    for title, expected_mark in cases.items():
        title_df = sessions_df.copy()
        title_df["title"] = title
        context = build_claim_context(title_df, 2026, 4)

        for mark_name in ("title_prof_mark", "title_dr_mark", "title_mr_mark", "title_ms_mark"):
            assert context[mark_name] == ("X" if mark_name == expected_mark else "")


def test_claim_context_unknown_title_leaves_all_title_marks_blank():
    sessions_df = _load_maria_sessions()
    sessions_df["title"] = "Mx"
    context = build_claim_context(sessions_df, 2026, 4)

    assert context["title_prof_mark"] == ""
    assert context["title_dr_mark"] == ""
    assert context["title_mr_mark"] == ""
    assert context["title_ms_mark"] == ""


def test_maria_claim_context_numbering_restarts_per_group():
    sessions_df = _load_maria_sessions()
    rows = build_claim_context(sessions_df, 2026, 4)["claim_rows"]
    first_rows = [row for row in rows if row["group_display"]]

    assert len(first_rows) == sessions_df[["course_code", "group_name"]].drop_duplicates().shape[0]
    assert all(row["no"] == "1" for row in first_rows)


def test_claim_context_keeps_same_group_name_distinct_across_courses():
    sessions_df = pd.DataFrame(
        [
            {
                "course_code": "CUS411S",
                "course_name": "Course A",
                "department": "Informatics",
                "faculty": "Computing",
                "budget_allocation": "B1",
                "group_name": "SHARED_GROUP",
                "session_date": "2026-05-05",
                "start_time": "08:00",
                "end_time": "09:00",
                "hours": 1.0,
                "amount": 440.0,
                "tariff_per_hour": 440.0,
                "title": "Ms",
                "lecturer_name": "Demo Lecturer",
                "highest_qualification": "MSc",
                "staff_number": "900001",
                "id_or_passport_number": "DUMMY",
                "paye_number": "DUMMY",
                "physical_address": "DUMMY",
                "contact_number": "DUMMY",
            },
            {
                "course_code": "ICT521S",
                "course_name": "Course B",
                "department": "Informatics",
                "faculty": "Computing",
                "budget_allocation": "B2",
                "group_name": "SHARED_GROUP",
                "session_date": "2026-05-06",
                "start_time": "08:00",
                "end_time": "09:00",
                "hours": 1.0,
                "amount": 440.0,
                "tariff_per_hour": 440.0,
                "title": "Ms",
                "lecturer_name": "Demo Lecturer",
                "highest_qualification": "MSc",
                "staff_number": "900001",
                "id_or_passport_number": "DUMMY",
                "paye_number": "DUMMY",
                "physical_address": "DUMMY",
                "contact_number": "DUMMY",
            },
        ]
    )

    context = build_claim_context(sessions_df, 2026, 5)
    first_rows = [row for row in context["claim_rows"] if row["group_display"]]
    audit = audit_claim_completeness_from_data(sessions_df, context)

    assert len(first_rows) == 2
    assert {row["course_code"] for row in first_rows} == {"CUS411S", "ICT521S"}
    assert audit["status"] == "PASS"
    assert audit["missing_pairs"] == []


def test_claim_completeness_detects_missing_course_group_pair():
    sessions_df = pd.DataFrame(
        [
            {"course_code": "CUS411S", "group_name": "GROUP_A", "session_date": "2026-05-05", "hours": 1.0, "amount": 440.0},
            {"course_code": "ICT521S", "group_name": "GROUP_A", "session_date": "2026-05-06", "hours": 1.0, "amount": 440.0},
        ]
    )
    claim_context = {"claim_rows": [{"course_code": "CUS411S", "group_name": "GROUP_A"}]}

    audit = audit_claim_completeness_from_data(sessions_df, claim_context)

    assert audit["status"] == "WARN"
    assert audit["missing_pairs"] == [{"course_code": "ICT521S", "group_name": "GROUP_A"}]


def test_maria_register_contexts_split_groups_and_include_dummy_students():
    sessions_df = _load_maria_sessions()
    contexts = build_register_page_contexts(sessions_df, 2026, 4)
    groups = {context["group_name"] for context in contexts}

    assert {
        "CUS HORTICULTURE",
        "CUS GROUP A",
        "CUS GROUP B",
        "ICT GROUP A",
        "ICT GROUP B",
        "ICT BOA-EENANHA",
        "ICT GREY",
        "ICT Distance",
    }.issubset(groups)
    assert len([context for context in contexts if context["group_name"] == "CUS GROUP A"]) > 1
    assert all(
        sum(1 for index in range(1, 6) if context[f"session_{index}_date"]) <= 5
        for context in contexts
    )
    assert any(student["surname"].startswith("PilotSurname") for context in contexts for student in context["students"])
    register_context_text = json.dumps(contexts)
    for sensitive_name in ("id_or_passport_number", "paye_number", "physical_address", "contact_number"):
        assert sensitive_name not in register_context_text


def test_clean_demo_contexts_are_supported():
    dev_reset()
    sessions_df = generate_monthly_sessions(200001, 2026, 2)

    claim_context = build_claim_context(sessions_df, 2026, 2)
    register_contexts = build_register_page_contexts(sessions_df, 2026, 2)

    assert claim_context["lecturer_name"] == "Demo Clean Lecturer"
    assert claim_context["staff_number"] == "200001"
    assert {context["group_name"] for context in register_contexts} == {"Demo Group A", "Demo Group B", "Demo Group C"}
