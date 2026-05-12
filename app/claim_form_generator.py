from pathlib import Path

import pandas as pd
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from app.attendance_register_generator import WARNING_TEXT
from app.docx_utils import (
    add_compact_paragraph,
    add_warning,
    apply_compact_document_style,
    create_document,
    create_fixed_table,
    ensure_parent,
    format_compact_hours,
    format_currency,
    format_docx_date,
    format_month_year,
    format_time_range,
    format_whole_money,
    repeat_table_header,
    set_a4_portrait,
    set_cell_text,
    set_narrow_margins,
)


def _title_mark(title: str, expected: str) -> str:
    return "X" if str(title).strip().lower().rstrip(".") == expected.lower() else ""


def _course_post(sessions_df: pd.DataFrame) -> str:
    course_codes = sorted(set(sessions_df["course_code"].astype(str)))
    return " & ".join(course_codes)


def _faculty_department(sessions_df: pd.DataFrame) -> str:
    faculties = sorted(set(sessions_df["faculty"].astype(str)))
    departments = sorted(set(sessions_df["department"].astype(str)))
    faculty = "FCI" if any("Computing" in item for item in faculties) else " / ".join(faculties)
    return f"{faculty} / {' / '.join(departments)}"


def _add_institution_header(document) -> None:
    add_compact_paragraph(
        document,
        "NAMIBIA UNIVERSITY OF SCIENCE AND TECHNOLOGY",
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=10,
    )
    add_compact_paragraph(document, "Faculty of Computing and Informatics", align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    add_compact_paragraph(document, "Department of Informatics", align=WD_ALIGN_PARAGRAPH.CENTER, size=9)


def _add_title_checkboxes(document, title: str) -> None:
    table = create_fixed_table(document, 1, 4)
    for index, label in enumerate(("Prof", "Dr", "Mr", "Ms")):
        mark = _title_mark(title, label)
        set_cell_text(table.rows[0].cells[index], f"{label} [{mark}]", bold=True, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)


def _add_particulars(document, sessions_df: pd.DataFrame) -> None:
    first = sessions_df.iloc[0]
    budget_allocations = ", ".join(sorted(set(sessions_df["budget_allocation"].astype(str))))
    table = create_fixed_table(document, 5, 4)
    left = [
        ("Name & Surname", first["lecturer_name"]),
        ("Highest qualification", first["highest_qualification"]),
        ("Personnel Number", first["staff_number"]),
        ("Identity / Passport Number", first["id_or_passport_number"]),
        ("Address", first["physical_address"]),
    ]
    right = [
        ("Budget Allocation", budget_allocations),
        ("Tariff per hour", format_currency(first["tariff_per_hour"])),
        ("PAYE No.", first["paye_number"]),
        ("Tel. no.", first["contact_number"]),
        ("Claim month", ""),
    ]
    for row_index in range(5):
        cells = table.rows[row_index].cells
        set_cell_text(cells[0], left[row_index][0], bold=True, size=8)
        set_cell_text(cells[1], left[row_index][1], size=8)
        set_cell_text(cells[2], right[row_index][0], bold=True, size=8)
        set_cell_text(cells[3], right[row_index][1], size=8)


def _add_level_of_training(document) -> None:
    table = create_fixed_table(document, 1, 3)
    for index, label in enumerate(("Part-time", "Full-time", "Extra-curricular")):
        mark = "X" if label == "Part-time" else ""
        set_cell_text(table.rows[0].cells[index], f"{label} [{mark}]", bold=True, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)


def _add_claim_table(document, sessions_df: pd.DataFrame) -> None:
    headers = [
        "No.",
        "Date",
        "Lecture/Tutorial/Admin.",
        "Consultation",
        "Dep./Board Meeting",
        "Time From - To",
        "Hours",
        "N$",
        "C",
        "FOR OFFICE USE",
    ]
    table = create_fixed_table(document, 1, len(headers))
    for index, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[index], header, bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
    repeat_table_header(table.rows[0])

    sorted_df = sessions_df.sort_values(["group_name", "session_date", "start_time"])
    for group_name, group_df in sorted_df.groupby("group_name", sort=True):
        for index, row in enumerate(group_df.to_dict("records"), start=1):
            cells = table.add_row().cells
            values = [
                str(index),
                format_docx_date(row["session_date"]),
                "Lecture",
                group_name if index == 1 else "",
                "",
                format_time_range(row["start_time"], row["end_time"]),
                format_compact_hours(row["hours"]),
                format_whole_money(row["tariff_per_hour"]),
                "00",
                "",
            ]
            for cell, value in zip(cells, values):
                set_cell_text(cell, value, size=7, align=WD_ALIGN_PARAGRAPH.CENTER if value != group_name else None)


def _add_signature_block(document) -> None:
    add_compact_paragraph(document, "")
    signature_rows = [
        ("Claimant's Signature: _______________________________", "Date: _______________________"),
        ("Signature of Head of Department: _____________________", "Date: _______________________"),
        ("Signature of Dean/Registrar: _________________________", "Date: _______________________"),
        ("Processed by Payroll Department: _____________________", "Date: _______________________"),
    ]
    for left, right in signature_rows:
        paragraph = add_compact_paragraph(document, f"{left}    {right}", size=8)
        paragraph.paragraph_format.space_after = Pt(2)
    add_compact_paragraph(document, "VERY IMPORTANT: Claims older than 3 months will not be honoured.", bold=True, size=8)
    add_compact_paragraph(
        document,
        "Kindly specify whether you lectured, tutored, had a meeting or did consultation.",
        bold=True,
        size=8,
    )


def generate_claim_form(
    sessions_df: pd.DataFrame,
    output_path: str | Path,
    year: int,
    month: int,
    warning: bool = False,
) -> Path:
    if sessions_df.empty:
        raise ValueError("Cannot generate claim form without sessions")

    output = ensure_parent(output_path)
    document = create_document()
    apply_compact_document_style(document, font_name="Arial", font_size=8)
    section = document.sections[0]
    set_a4_portrait(section)
    set_narrow_margins(section)

    first = sessions_df.iloc[0]
    total_hours = round(float(sessions_df["hours"].sum()), 2)
    total_amount = round(float(sessions_df["amount"].sum()), 2)

    _add_institution_header(document)
    if warning:
        add_warning(document, WARNING_TEXT)
    add_compact_paragraph(
        document,
        "CLAIM FOR REMUNERATION BY PART-TIME LECTURERS / ACADEMIC STAFF MEMBERS",
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=10,
    )
    _add_title_checkboxes(document, first["title"])
    add_compact_paragraph(document, "PARTICULARS OF CLAIMANT", bold=True, size=9)
    _add_particulars(document, sessions_df)
    _add_level_of_training(document)
    add_compact_paragraph(
        document,
        f"PARTICULARS OF CLAIM    HR - TOTAL HOURS CLAIMED: {format_compact_hours(total_hours)}",
        bold=True,
        size=9,
    )
    add_compact_paragraph(document, f"Course/Post: {_course_post(sessions_df)}", bold=True, size=8)
    add_compact_paragraph(
        document,
        f"Course names: {', '.join(sorted(set(sessions_df['course_name'].astype(str))))}",
        size=8,
    )
    add_compact_paragraph(document, f"Faculty/Department: {_faculty_department(sessions_df)}", bold=True, size=8)
    add_compact_paragraph(document, f"Claim month and year: {format_month_year(year, month)}", size=8)
    _add_claim_table(document, sessions_df)
    add_compact_paragraph(
        document,
        f"TOTAL HOURS: {format_compact_hours(total_hours)}    TOTAL AMOUNT: {format_currency(total_amount)}",
        bold=True,
        size=8,
        align=WD_ALIGN_PARAGRAPH.RIGHT,
    )
    _add_signature_block(document)

    try:
        document.save(output)
    except PermissionError:
        if output.exists():
            return output
        raise
    return output
