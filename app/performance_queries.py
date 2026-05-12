from __future__ import annotations

from app.db_provider import convert_placeholders, db_perf_span, get_runtime_connection, init_runtime_db, row_to_dict


def admin_dashboard_counts() -> dict[str, int]:
    init_runtime_db()
    with db_perf_span("admin_dashboard_counts"):
        with get_runtime_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM lecturers) AS lecturers,
                    (SELECT COUNT(*) FROM courses) AS courses,
                    (SELECT COUNT(*) FROM student_groups) AS groups,
                    (SELECT COUNT(*) FROM students) AS students,
                    (SELECT COUNT(*) FROM timetable_entries) AS timetable_entries,
                    (SELECT COUNT(*) FROM academic_calendar) AS academic_calendar_entries
                """
            ).fetchone()
    data = row_to_dict(row) or {}
    return {key.replace("_", " "): int(value or 0) for key, value in data.items()}


def lecturer_dashboard_counts(staff_number: str) -> dict[str, int]:
    init_runtime_db()
    with db_perf_span("lecturer_dashboard_counts"):
        with get_runtime_connection() as conn:
            row = conn.execute(
                convert_placeholders(
                    """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM student_groups AS g
                        JOIN lecturers AS l ON l.id = g.lecturer_id
                        WHERE l.staff_number = %s AND g.lecturer_id IS NOT NULL
                    ) AS groups,
                    (
                        SELECT COUNT(*)
                        FROM timetable_entries AS t
                        JOIN lecturers AS l ON l.id = t.lecturer_id
                        WHERE l.staff_number = %s
                    ) AS timetable_entries,
                    (
                        SELECT COUNT(*)
                        FROM group_enrolments AS ge
                        JOIN student_groups AS g ON g.id = ge.group_id
                        JOIN lecturers AS l ON l.id = g.lecturer_id
                        WHERE l.staff_number = %s AND ge.active = 1
                    ) AS active_enrolments
                """.replace("%s", "?")
                ),
                (str(staff_number), str(staff_number), str(staff_number)),
            ).fetchone()
    data = row_to_dict(row) or {}
    return {key.replace("_", " "): int(value or 0) for key, value in data.items()}
