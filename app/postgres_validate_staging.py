from __future__ import annotations

import argparse
import os
from typing import Any

from app.postgres_migrate_staging import DEFAULT_TARGET_ENV, target_url_from_env
from app.postgres_schema import TABLE_ORDER


EXPECTED_STAGING_COUNTS = {
    "lecturers": 15,
    "courses": 2,
    "student_groups": 36,
    "timetable_entries": 95,
    "students": 1038,
    "group_enrolments": 1053,
    "user_accounts": 5,
}
KNOWN_REAL_MARKERS = ["Lonia", "Alvina", "Maria", "Mervin", "Haukongo", "Venasius", "Nalukaku"]


def _connect_postgres(url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for PostgreSQL staging validation.") from exc
    return psycopg.connect(url)


def missing_target_url_message(target_env: str = DEFAULT_TARGET_ENV) -> str:
    return f"{target_env} is not configured. Set it to a disposable PostgreSQL URL before validation."


def validate_target_env_present(target_env: str = DEFAULT_TARGET_ENV) -> str:
    if not os.environ.get(target_env, "").strip():
        raise RuntimeError(missing_target_url_message(target_env))
    return target_url_from_env(target_env)


def validate_postgres_staging(target_env: str = DEFAULT_TARGET_ENV) -> dict[str, Any]:
    url = validate_target_env_present(target_env)
    failures: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    with _connect_postgres(url) as conn:
        with conn.cursor() as cur:
            for table in TABLE_ORDER:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                    """,
                    (table,),
                )
                if not cur.fetchone()[0]:
                    failures.append(f"Missing table: {table}")
                    continue
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = int(cur.fetchone()[0])

            for table, expected in EXPECTED_STAGING_COUNTS.items():
                actual = counts.get(table)
                if actual != expected:
                    failures.append(f"{table} count mismatch: expected {expected}, got {actual}")

            for marker in KNOWN_REAL_MARKERS:
                marker_like = f"%{marker}%"
                for table, column in [
                    ("lecturers", "full_name"),
                    ("students", "surname"),
                    ("students", "full_name"),
                    ("student_groups", "group_name"),
                    ("user_accounts", "username"),
                ]:
                    if table not in counts:
                        continue
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} ILIKE %s", (marker_like,))
                    if int(cur.fetchone()[0]):
                        failures.append(f"Known real marker remains in {table}.{column}: {marker}")

            cur.execute("SELECT COUNT(*) FROM user_accounts WHERE username = 'staging_admin' AND role = 'admin'")
            if int(cur.fetchone()[0]) != 1:
                failures.append("staging_admin account missing.")
            cur.execute("SELECT COUNT(*) FROM user_accounts WHERE role = 'lecturer'")
            if int(cur.fetchone()[0]) < 4:
                failures.append("Expected demo lecturer accounts are missing.")
            cur.execute("SELECT COUNT(*) FROM user_accounts WHERE password_hash IN ('Staging@2026', 'StagingAdmin@2026')")
            if int(cur.fetchone()[0]):
                failures.append("Plaintext staging password found in password_hash.")
            cur.execute("SELECT COUNT(*) FROM student_groups sg LEFT JOIN courses c ON c.id = sg.course_id WHERE c.id IS NULL")
            if int(cur.fetchone()[0]):
                failures.append("Broken student_groups.course_id foreign-key relationship found.")
            cur.execute("SELECT COUNT(*) FROM group_enrolments ge LEFT JOIN students s ON s.id = ge.student_id WHERE s.id IS NULL")
            if int(cur.fetchone()[0]):
                failures.append("Broken group_enrolments.student_id relationship found.")
            cur.execute("SELECT COUNT(*) FROM group_enrolments ge LEFT JOIN student_groups sg ON sg.id = ge.group_id WHERE sg.id IS NULL")
            if int(cur.fetchone()[0]):
                failures.append("Broken group_enrolments.group_id relationship found.")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM student_groups sg
                JOIN lecturers l ON l.id = sg.lecturer_id
                JOIN courses c ON c.id = sg.course_id
                WHERE l.staff_number = '900001'
                """
            )
            if int(cur.fetchone()[0]) == 0:
                warnings.append("Sample lecturer group query returned no groups for 900001.")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM timetable_entries te
                JOIN lecturers l ON l.id = te.lecturer_id
                WHERE l.staff_number = '900001'
                """
            )
            if int(cur.fetchone()[0]) == 0:
                warnings.append("Sample lecturer timetable query returned no entries for 900001.")
    return {"target_env": target_env, "valid": not failures, "counts": counts, "failures": failures, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate disposable PostgreSQL staging migration.")
    parser.add_argument("--target-env", default=DEFAULT_TARGET_ENV)
    args = parser.parse_args()
    try:
        result = validate_postgres_staging(args.target_env)
    except RuntimeError as exc:
        print(f"Validation failed: {exc}")
        raise SystemExit(1) from None
    print(f"Target env: {result['target_env']}")
    print(f"Valid: {result['valid']}")
    print(f"Counts: {result['counts']}")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    if result["failures"]:
        print("Failures:")
        for failure in result["failures"]:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
