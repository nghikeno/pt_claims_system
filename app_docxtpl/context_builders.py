from __future__ import annotations

from math import ceil
from pathlib import Path

import pandas as pd

from app.attendance_register_generator import get_students_for_group
from app.docx_utils import format_time_range


MAX_REGISTER_SESSIONS = 5


def format_claim_date(value) -> str:
    return pd.to_datetime(value).strftime("%d/%m/%Y")


def format_register_date(value) -> str:
    return pd.to_datetime(value).strftime("%d-%m-%y")


def format_compact_number(value) -> str:
    parsed = float(value)
    return str(int(parsed)) if parsed.is_integer() else f"{parsed:.2f}"


def _course_post(sessions_df: pd.DataFrame) -> str:
    codes = set(sessions_df["course_code"].astype(str))
    if {"ICT521S", "CUS411S"}.issubset(codes):
        return "ICT521S & CUS411S"
    return " & ".join(sorted(codes))


def _faculty_department(sessions_df: pd.DataFrame) -> str:
    departments = sorted(set(sessions_df["department"].astype(str)))
    if any("Informatics" in item for item in departments):
        return "Informatics"
    return " / ".join(departments)


def _budget_allocation(sessions_df: pd.DataFrame) -> str:
    return ", ".join(sorted(set(sessions_df["budget_allocation"].astype(str))))


def _title_marks(title: str) -> dict[str, str]:
    normalized = str(title or "").strip().casefold()
    aliases = {
        "prof": "title_prof_mark",
        "dr": "title_dr_mark",
        "mr": "title_mr_mark",
        "ms": "title_ms_mark",
    }
    marks = {
        "title_prof_mark": "",
        "title_dr_mark": "",
        "title_mr_mark": "",
        "title_ms_mark": "",
    }
    mark_key = aliases.get(normalized)
    if mark_key:
        marks[mark_key] = "X"
    return marks


def build_claim_context(sessions_df: pd.DataFrame, year: int, month: int) -> dict:
    if sessions_df.empty:
        raise ValueError("Cannot build claim context without sessions")

    first = sessions_df.iloc[0]
    claim_rows = []
    sorted_df = sessions_df.sort_values(["group_name", "session_date", "start_time"])
    for group_name, group_df in sorted_df.groupby("group_name", sort=True):
        for number, row in enumerate(group_df.to_dict("records"), start=1):
            claim_rows.append(
                {
                    "no": str(number),
                    "date": format_claim_date(row["session_date"]),
                    "activity": "X",
                    "group_display": group_name if number == 1 else "",
                    "meeting": "",
                    "time_range": format_time_range(row["start_time"], row["end_time"]),
                    "hours": format_compact_number(row["hours"]),
                    "rate": format_compact_number(row["tariff_per_hour"]),
                    "cents": "00",
                    "office_use": "",
                    "group_name": group_name,
                }
            )

    context = {
        "lecturer_title": str(first["title"]),
        "lecturer_name": str(first["lecturer_name"]),
        "highest_qualification": str(first["highest_qualification"]),
        "budget_allocation": _budget_allocation(sessions_df),
        "staff_number": str(first["staff_number"]),
        "tariff_per_hour": format_compact_number(first["tariff_per_hour"]),
        "id_or_passport_number": str(first["id_or_passport_number"]),
        "paye_number": str(first["paye_number"]),
        "physical_address": str(first["physical_address"]),
        "contact_number": str(first["contact_number"]),
        "level_part_time_mark": "X",
        "level_full_time_mark": "",
        "level_extra_curricular_mark": "",
        "total_hours": format_compact_number(float(sessions_df["hours"].sum())),
        "course_post": _course_post(sessions_df),
        "faculty_department": _faculty_department(sessions_df),
        "claim_rows": claim_rows,
        "year": year,
        "month": month,
    }
    context.update(_title_marks(str(first["title"])))
    return context


def _student_rows(group_name: str, course_code: str, staff_number: str | None = None) -> list[dict]:
    students = get_students_for_group(group_name, course_code, staff_number=staff_number)
    if not students:
        students = [
            {"surname": "", "initials": "", "student_number": "", "full_name": ""}
            for _ in range(10)
        ]
    rows = []
    for index, student in enumerate(students, start=1):
        row = {
            "nr": str(index),
            "surname": str(student.get("surname") or ""),
            "initials": str(student.get("initials") or ""),
            "student_number": str(student.get("student_number") or ""),
        }
        for sig_index in range(1, MAX_REGISTER_SESSIONS + 1):
            row[f"sig{sig_index}"] = ""
        rows.append(row)
    return rows


def _blank_session_values(context: dict) -> None:
    for index in range(1, MAX_REGISTER_SESSIONS + 1):
        context[f"session_{index}_date"] = ""
        context[f"session_{index}_time"] = ""


def build_register_page_contexts(sessions_df: pd.DataFrame, year: int, month: int) -> list[dict]:
    if sessions_df.empty:
        raise ValueError("Cannot build register contexts without sessions")

    lecturer_name = str(sessions_df["lecturer_name"].iloc[0])
    staff_number = str(sessions_df["staff_number"].iloc[0])
    contexts: list[dict] = []
    group_keys = ["faculty", "department", "course_name", "course_code", "group_name", "campus"]
    for group_values, group_df in sessions_df.groupby(group_keys, sort=True):
        faculty, department, course_name, course_code, group_name, _campus = group_values
        sorted_group = group_df.sort_values(["session_date", "start_time"])
        total_pages = ceil(len(sorted_group) / MAX_REGISTER_SESSIONS)
        students = _student_rows(str(group_name), str(course_code), staff_number=staff_number)
        for page_index in range(total_pages):
            chunk = sorted_group.iloc[
                page_index * MAX_REGISTER_SESSIONS : (page_index + 1) * MAX_REGISTER_SESSIONS
            ].to_dict("records")
            context = {
                "faculty": str(faculty),
                "department": "Informatics" if "Informatics" in str(department) else str(department),
                "course_name": str(course_name),
                "course_code": str(course_code),
                "group_name": str(group_name),
                "lecturer_name": lecturer_name,
                "staff_number": staff_number,
                "students": students,
                "page_number": page_index + 1,
                "total_pages": total_pages,
                "year": year,
                "month": month,
            }
            _blank_session_values(context)
            for index, session in enumerate(chunk, start=1):
                context[f"session_{index}_date"] = format_register_date(session["session_date"])
                context[f"session_{index}_time"] = format_time_range(session["start_time"], session["end_time"])
            contexts.append(context)
    return contexts


def generated_v2_directory(year: int, month: int, staff_number: str) -> Path:
    return Path("data") / "generated_v2" / str(year) / f"{month:02d}" / str(staff_number)
