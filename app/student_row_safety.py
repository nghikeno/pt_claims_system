from __future__ import annotations

import re
from typing import Any


HEADER_MARKERS = (
    "student surname",
    "student surname & initial",
    "student surname & init",
    "student name",
    "std nr",
    "student number",
    "initial",
    "time:",
    "signature",
    "name of lecturer",
    "lecturer",
    "date",
)


def clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def normalised_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9:]+", " ", clean_cell(value).casefold()).strip()


def is_time_range_text(value: Any) -> bool:
    text = clean_cell(value)
    return bool(re.search(r"\b\d{1,2}[:h]\d{2}\s*[-–—]\s*\d{1,2}[:h]\d{2}\b", text, re.IGNORECASE))


def is_time_derived_student_number(student_number: Any, row_text: Any = "") -> bool:
    number = re.sub(r"\D", "", clean_cell(student_number))
    if len(number) != 8:
        return False
    start_hour = int(number[0:2])
    start_minute = int(number[2:4])
    end_hour = int(number[4:6])
    end_minute = int(number[6:8])
    valid_time_range = (
        0 <= start_hour <= 23
        and 0 <= start_minute <= 59
        and 0 <= end_hour <= 23
        and 0 <= end_minute <= 59
        and (end_hour, end_minute) > (start_hour, start_minute)
    )
    if not valid_time_range:
        return False
    return is_time_range_text(row_text) or number in {"18402000", "07300830", "10301130"}


def suspicious_student_row_reason(
    student_number: Any = "",
    surname: Any = "",
    initials: Any = "",
    full_name: Any = "",
    row_text: Any = "",
) -> str | None:
    values = [clean_cell(row_text), clean_cell(surname), clean_cell(initials), clean_cell(full_name)]
    joined = normalised_text(" ".join(values))
    if not any(clean_cell(value) for value in values) and not clean_cell(student_number):
        return "Empty row"
    if any(marker in joined for marker in HEADER_MARKERS):
        if "time:" in joined or is_time_range_text(row_text):
            return "Time row"
        return "Header row"
    if is_time_derived_student_number(student_number, row_text):
        return "Invalid student number"
    return None


def is_suspicious_student_row(student: dict[str, Any], row_text: Any = "") -> bool:
    return suspicious_student_row_reason(
        student.get("student_number"),
        student.get("surname"),
        student.get("initials"),
        student.get("full_name"),
        row_text,
    ) is not None

