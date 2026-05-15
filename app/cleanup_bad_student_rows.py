from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.db_provider import close_postgres_pool, convert_placeholders, get_runtime_connection, rows_to_dicts
from app.student_row_safety import suspicious_student_row_reason


CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_WILL_REMOVE_ONLY_HEADER_ROW_STUDENTS"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "student_id": row.get("student_id"),
        "student_number": row.get("student_number"),
        "surname": row.get("surname"),
        "initials": row.get("initials"),
        "full_name": row.get("full_name"),
        "lecturer_staff_number": row.get("staff_number"),
        "lecturer_name": row.get("lecturer_name"),
        "course_code": row.get("course_code"),
        "group_name": row.get("group_name"),
        "enrolment_id": row.get("enrolment_id"),
        "reason": row.get("reason"),
    }


def find_suspicious_student_rows() -> list[dict[str, Any]]:
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id AS student_id,
                s.student_number,
                s.surname,
                s.initials,
                s.full_name,
                s.active AS student_active,
                ge.id AS enrolment_id,
                ge.active AS enrolment_active,
                sg.group_name,
                c.course_code,
                l.staff_number,
                l.full_name AS lecturer_name
            FROM students AS s
            LEFT JOIN group_enrolments AS ge ON ge.student_id = s.id
            LEFT JOIN student_groups AS sg ON sg.id = ge.group_id
            LEFT JOIN courses AS c ON c.id = sg.course_id
            LEFT JOIN lecturers AS l ON l.id = sg.lecturer_id
            WHERE s.active = 1
            ORDER BY s.student_number, s.id, ge.id
            """
        ).fetchall()
    findings: list[dict[str, Any]] = []
    for row in rows_to_dicts(rows):
        reason = suspicious_student_row_reason(
            row.get("student_number"),
            row.get("surname"),
            row.get("initials"),
            row.get("full_name"),
            " ".join(str(row.get(key) or "") for key in ("surname", "initials", "full_name", "student_number")),
        )
        if reason:
            item = dict(row)
            item["reason"] = reason
            findings.append(_safe_row(item))
    return findings


def cleanup_suspicious_student_rows(write: bool = False) -> dict[str, Any]:
    findings = find_suspicious_student_rows()
    result = {
        "status": "DRY_RUN" if not write else "APPLIED",
        "matched_count": len(findings),
        "rows": findings,
        "students_deactivated": 0,
        "enrolments_deactivated": 0,
    }
    if not write or not findings:
        return result
    student_ids = sorted({int(row["student_id"]) for row in findings if row.get("student_id") is not None})
    enrolment_ids = sorted({int(row["enrolment_id"]) for row in findings if row.get("enrolment_id") is not None})
    with get_runtime_connection() as conn:
        for enrolment_id in enrolment_ids:
            conn.execute(convert_placeholders("UPDATE group_enrolments SET active = 0 WHERE id = ?"), (enrolment_id,))
            result["enrolments_deactivated"] += 1
        for student_id in student_ids:
            conn.execute(convert_placeholders("UPDATE students SET active = 0 WHERE id = ?"), (student_id,))
            result["students_deactivated"] += 1
        if hasattr(conn, "commit"):
            conn.commit()
    return result


def _print_report(report: dict[str, Any], as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print("Suspicious Student Row Cleanup")
    print("==============================")
    print(f"Status: {report['status']}")
    print(f"Matched rows: {report['matched_count']}")
    print(f"Students deactivated: {report['students_deactivated']}")
    print(f"Enrolments deactivated: {report['enrolments_deactivated']}")
    for row in report["rows"]:
        print(
            "- "
            f"student_id={row.get('student_id')} "
            f"student_number={row.get('student_number')} "
            f"surname={row.get('surname')} "
            f"initials={row.get('initials')} "
            f"group={row.get('course_code')} / {row.get('group_name')} "
            f"reason={row.get('reason')}"
        )
    print("Secrets printed: no")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run or deactivate exact header/time-row student contaminants.")
    parser.add_argument("--yes", action="store_true", help="Apply the guarded cleanup.")
    parser.add_argument("--confirm-cleanup", default="", help="Exact confirmation phrase required for write mode.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)
    write = bool(args.yes)
    if write and args.confirm_cleanup != CONFIRMATION_PHRASE:
        print("Cleanup refused: exact confirmation phrase is required.")
        return 2
    try:
        report = cleanup_suspicious_student_rows(write=write)
        _print_report(report, as_json=args.json)
        return 0
    finally:
        close_postgres_pool()


if __name__ == "__main__":
    raise SystemExit(main())

