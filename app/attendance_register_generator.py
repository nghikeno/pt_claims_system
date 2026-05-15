from math import ceil
from pathlib import Path

import pandas as pd
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.db_provider import convert_placeholders, get_runtime_connection, rows_to_dicts
from app.docx_utils import (
    add_compact_paragraph,
    add_warning,
    apply_compact_document_style,
    create_document,
    create_fixed_table,
    ensure_parent,
    format_docx_date,
    format_time_range,
    safe_filename_text,
    set_a4_landscape,
    set_cell_text,
    set_narrow_margins,
)
from app.student_row_safety import is_suspicious_student_row


WARNING_TEXT = "DRAFT ONLY - CLASHES DETECTED, REVIEW REQUIRED"
MAX_SESSION_COLUMNS = 6
MIN_REGISTER_ROWS = 30


def get_students_for_group(group_name: str, course_code: str, staff_number: str | None = None) -> list[dict]:
    lecturer_filter = ""
    params: list[str] = [group_name, course_code]
    if staff_number:
        lecturer_filter = "AND l.staff_number = ?"
        params.append(staff_number)
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(f"""
            SELECT s.student_number, s.surname, s.initials, s.full_name
            FROM group_enrolments ge
            JOIN students s ON s.id = ge.student_id
            JOIN student_groups sg ON sg.id = ge.group_id
            JOIN courses c ON c.id = sg.course_id
            LEFT JOIN lecturers l ON l.id = sg.lecturer_id
            WHERE ge.active = 1
              AND s.active = 1
              AND sg.group_name = ?
              AND c.course_code = ?
              {lecturer_filter}
            ORDER BY s.surname, s.initials, s.student_number
            """),
            tuple(params),
        ).fetchall()
    return [row for row in rows_to_dicts(rows) if not is_suspicious_student_row(row)]


def _student_rows(students: list[dict], session_count: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, student in enumerate(students, start=1):
        display_name = " ".join(part for part in [student["surname"], student["initials"]] if part)
        rows.append([str(index), display_name, student["student_number"]] + [""] * session_count)
    target_rows = max(MIN_REGISTER_ROWS, len(rows))
    for index in range(len(rows) + 1, target_rows + 1):
        rows.append([str(index), "", ""] + [""] * session_count)
    return rows


def _register_id(staff_number: str, course_code: str, group_name: str, year: int, month: int, page_number: int) -> str:
    return f"REG-{staff_number}-{course_code}-{safe_filename_text(group_name)}-{year}-{month:02d}-P{page_number}"


def _add_register_header(document, faculty: str, department: str, course_name: str, course_code: str, group_name: str) -> None:
    add_compact_paragraph(
        document,
        "NAMIBIA UNIVERSITY OF SCIENCE AND TECHNOLOGY",
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=10,
    )
    add_compact_paragraph(document, "Faculty of Computing and Informatics", align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    add_compact_paragraph(document, "Department of Informatics", align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    add_compact_paragraph(document, "CLASS ATTENDANCE SHEET", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=11)
    add_compact_paragraph(document, f"FACULTY: {faculty}", bold=True, size=8)
    add_compact_paragraph(document, f"DEPARTMENT: {department}", bold=True, size=8)
    add_compact_paragraph(
        document,
        f"COURSE NAME: {course_name}     COURSE CODE: {course_code}     GROUP: {group_name}",
        bold=True,
        size=8,
    )


def _add_attendance_table(document, students: list[dict], session_chunk: list[dict]) -> None:
    session_count = len(session_chunk)
    table = create_fixed_table(document, 2, 3 + session_count)
    row0 = table.rows[0].cells
    row1 = table.rows[1].cells
    base_headers = ["NR.", "STUDENT SURNAME & INITIAL", "STD NR"]
    for index, header in enumerate(base_headers):
        set_cell_text(row0[index], header, bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_text(row1[index], "", bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
    for offset, session in enumerate(session_chunk):
        column = 3 + offset
        set_cell_text(row0[column], f"DATE: {format_docx_date(session['session_date'])}", bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_text(row1[column], f"TIME: {format_time_range(session['start_time'], session['end_time'])}", bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)

    for row_values in _student_rows(students, session_count):
        cells = table.add_row().cells
        for cell, value in zip(cells, row_values):
            set_cell_text(cell, value, size=7, align=WD_ALIGN_PARAGRAPH.CENTER if len(str(value)) <= 12 else None)


def _add_signature_footer(document, lecturer_name: str, staff_number: str, register_id: str) -> None:
    table = create_fixed_table(document, 2, 4)
    values = [lecturer_name, "__________________________", staff_number, "__________________"]
    labels = ["NAME OF LECTURER", "SIGNATURE", "STAFF NR.", "DATE"]
    for index, value in enumerate(values):
        set_cell_text(table.rows[0].cells[index], value, bold=index in (0, 2), size=8, align=WD_ALIGN_PARAGRAPH.CENTER)
    for index, label in enumerate(labels):
        set_cell_text(table.rows[1].cells[index], label, bold=True, size=7, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_compact_paragraph(document, f"Register ID: {register_id}", size=6, align=WD_ALIGN_PARAGRAPH.RIGHT)


def generate_attendance_register_pack(
    sessions_df: pd.DataFrame,
    output_path: str | Path,
    year: int,
    month: int,
    warning: bool = False,
) -> Path:
    if sessions_df.empty:
        raise ValueError("Cannot generate attendance register pack without sessions")

    output = ensure_parent(output_path)
    document = create_document()
    apply_compact_document_style(document, font_name="Arial", font_size=8)
    section = document.sections[0]
    set_a4_landscape(section)
    set_narrow_margins(section)

    lecturer_name = sessions_df["lecturer_name"].iloc[0]
    staff_number = str(sessions_df["staff_number"].iloc[0])

    group_keys = ["faculty", "department", "course_name", "course_code", "group_name", "campus"]
    first_page = True
    for group_values, group_df in sessions_df.groupby(group_keys, sort=True):
        faculty, department, course_name, course_code, group_name, _group_campus = group_values
        group_df = group_df.sort_values(["session_date", "start_time"])
        students = get_students_for_group(group_name, course_code)
        page_count = ceil(len(group_df) / MAX_SESSION_COLUMNS)
        for chunk_index in range(page_count):
            if not first_page:
                document.add_page_break()
            first_page = False
            session_chunk = group_df.iloc[
                chunk_index * MAX_SESSION_COLUMNS : (chunk_index + 1) * MAX_SESSION_COLUMNS
            ].to_dict("records")
            register_id = _register_id(staff_number, course_code, group_name, year, month, chunk_index + 1)
            _add_register_header(document, faculty, department, course_name, course_code, group_name)
            if warning:
                add_warning(document, WARNING_TEXT)
            if page_count > 1:
                add_compact_paragraph(document, f"Continuation: Page {chunk_index + 1} of {page_count}", bold=True, size=8)
            _add_attendance_table(document, students, session_chunk)
            _add_signature_footer(document, lecturer_name, staff_number, register_id)

    document.save(output)
    return output
