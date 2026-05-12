from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from app.auth_service import hash_password
from app.config import DATA_DIR, REAL_DB_PATH


DEFAULT_OUTPUT = DATA_DIR / "staging" / "pt_claims_staging_anonymised.db"
CORE_TABLES = [
    "lecturers",
    "courses",
    "student_groups",
    "timetable_entries",
    "students",
    "group_enrolments",
]
KNOWN_REAL_MARKERS = [
    "Lonia",
    "Alvina",
    "Maria",
    "Mervin",
    "Haukongo",
    "Venasius",
    "Nalukaku",
]
DEMO_LECTURER_NAMES = [
    "Demo Lecturer One",
    "Demo Lecturer Two",
    "Demo Lecturer Three",
    "Demo Lecturer Four",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
    return row is not None


def table_counts(path: Path, tables: list[str] | None = None) -> dict[str, int]:
    tables = tables or CORE_TABLES
    with connect(path) as conn:
        counts: dict[str, int] = {}
        for table in tables:
            if table_exists(conn, table):
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return counts


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _demo_lecturer_name(index: int) -> str:
    if index <= len(DEMO_LECTURER_NAMES):
        return DEMO_LECTURER_NAMES[index - 1]
    return f"Demo Lecturer {index:03d}"


def _demo_initial(index: int) -> str:
    return chr(ord("A") + ((index - 1) % 26))


def anonymise_existing_database(path: Path) -> dict[str, Any]:
    with connect(path) as conn:
        lecturer_rows = conn.execute("SELECT id FROM lecturers ORDER BY id").fetchall()
        lecturer_mappings: list[tuple[int, str, str]] = []
        for index, row in enumerate(lecturer_rows, start=1):
            staff_number = f"90{index:04d}"
            name = _demo_lecturer_name(index)
            lecturer_mappings.append((int(row["id"]), staff_number, name))
            conn.execute(
                """
                UPDATE lecturers
                SET staff_number = ?,
                    title = CASE WHEN title IN ('Prof', 'Dr', 'Mr', 'Ms') THEN title ELSE 'Ms' END,
                    full_name = ?,
                    highest_qualification = ?,
                    id_or_passport_number = ?,
                    paye_number = ?,
                    physical_address = ?,
                    contact_number = ?
                WHERE id = ?
                """,
                (
                    staff_number,
                    name,
                    f"Demo Qualification {index:03d}",
                    f"DEMO-ID-{index:06d}",
                    f"DEMO-PAYE-{index:06d}",
                    f"Demo Address {index:03d}",
                    f"081{index:07d}"[:10],
                    int(row["id"]),
                ),
            )

        if table_exists(conn, "students"):
            for index, row in enumerate(conn.execute("SELECT id FROM students ORDER BY id").fetchall(), start=1):
                surname = f"DemoSurname{index:03d}"
                initials = _demo_initial(index)
                conn.execute(
                    """
                    UPDATE students
                    SET student_number = ?, surname = ?, initials = ?, full_name = ?
                    WHERE id = ?
                    """,
                    (f"STU{index:06d}", surname, initials, f"{surname} {initials}", int(row["id"])),
                )

        if table_exists(conn, "student_groups"):
            for index, row in enumerate(conn.execute("SELECT id FROM student_groups ORDER BY id").fetchall(), start=1):
                conn.execute(
                    "UPDATE student_groups SET group_name = ? WHERE id = ?",
                    (f"DEMO_GROUP_{index:03d}", int(row["id"])),
                )

        if table_exists(conn, "audit_logs"):
            conn.execute("DELETE FROM audit_logs")

        if table_exists(conn, "user_accounts"):
            conn.execute("DELETE FROM user_accounts")
            now = "2026-05-12 00:00:00"
            admin_hash, admin_salt = hash_password("StagingAdmin@2026")
            conn.execute(
                """
                INSERT INTO user_accounts (
                    username, password_hash, password_salt, role, lecturer_id,
                    must_change_password, active, created_at, updated_at
                )
                VALUES (?, ?, ?, 'admin', NULL, 1, 1, ?, ?)
                """,
                ("staging_admin", admin_hash, admin_salt, now, now),
            )
            for lecturer_id, staff_number, _name in lecturer_mappings[:4]:
                password_hash, password_salt = hash_password("Staging@2026")
                conn.execute(
                    """
                    INSERT INTO user_accounts (
                        username, password_hash, password_salt, role, lecturer_id,
                        must_change_password, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'lecturer', ?, 1, 1, ?, ?)
                    """,
                    (staff_number, password_hash, password_salt, lecturer_id, now, now),
                )

        skipped_tables = [
            table
            for table in ["audit_logs"]
            if not table_exists(conn, table)
        ]
        return {"lecturers_anonymised": len(lecturer_rows), "skipped_tables": skipped_tables}


def create_anonymised_staging_db(
    source: Path = REAL_DB_PATH,
    output: Path = DEFAULT_OUTPUT,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    source = Path(source)
    output = Path(output)
    if not source.exists():
        raise FileNotFoundError(f"Source database not found: {source}")
    before_hash = sha256_file(source)
    before_counts = table_counts(source)
    if dry_run:
        return {
            "source": str(source),
            "output": str(output),
            "dry_run": True,
            "source_hash_before": before_hash,
            "source_hash_after": sha256_file(source),
            "counts_before": before_counts,
            "counts_after": None,
            "source_modified": False,
            "sensitive_fields_anonymised": False,
            "skipped_tables": [],
        }
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}. Pass --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    anonymise_result = anonymise_existing_database(output)
    after_counts = table_counts(output)
    source_hash_after = sha256_file(source)
    return {
        "source": str(source),
        "output": str(output),
        "dry_run": False,
        "source_hash_before": before_hash,
        "source_hash_after": source_hash_after,
        "counts_before": before_counts,
        "counts_after": after_counts,
        "source_modified": before_hash != source_hash_after,
        "sensitive_fields_anonymised": True,
        "skipped_tables": anonymise_result["skipped_tables"],
    }


def validate_anonymised_db(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Staging database not found: {path}")
    counts = table_counts(path)
    failures: list[str] = []
    with connect(path) as conn:
        text_checks = []
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall()
        ]
        for table in tables:
            columns = _column_names(conn, table)
            searchable_columns = [
                column
                for column in columns
                if column not in {"password_hash", "password_salt"} and "password" not in column.lower()
            ]
            for column in searchable_columns:
                for row in conn.execute(f"SELECT {column} AS value FROM {table} WHERE {column} IS NOT NULL").fetchall():
                    text_checks.append(str(row["value"]))
        combined = "\n".join(text_checks)
        for marker in KNOWN_REAL_MARKERS:
            if marker.lower() in combined.lower():
                failures.append(f"Known real marker remains: {marker}")
        if "Staging@2026" in combined or "StagingAdmin@2026" in combined:
            failures.append("Plaintext staging password found.")
        if table_exists(conn, "audit_logs"):
            audit_count = int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0])
            if audit_count:
                failures.append("Audit logs were not cleared.")
        if table_exists(conn, "user_accounts"):
            real_numeric_usernames = [
                row["username"]
                for row in conn.execute("SELECT username FROM user_accounts WHERE username GLOB '100*'").fetchall()
            ]
            if real_numeric_usernames:
                failures.append("Real-looking staff-number usernames remain.")
    return {"path": str(path), "valid": not failures, "failures": failures, "counts": counts}


def print_result(result: dict[str, Any]) -> None:
    print(f"Source DB: {result['source']}")
    print(f"Output DB: {result['output']}")
    print(f"Dry run: {result['dry_run']}")
    print(f"Counts before: {result['counts_before']}")
    print(f"Counts after: {result['counts_after']}")
    print(f"Source modified: {result['source_modified']}")
    print(f"Sensitive fields anonymised: {result['sensitive_fields_anonymised']}")
    print(f"Skipped tables: {result['skipped_tables']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or validate an anonymised staging SQLite database.")
    parser.add_argument("--source", default=str(REAL_DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--validate", help="Validate an existing anonymised staging database.")
    args = parser.parse_args()

    if args.validate:
        result = validate_anonymised_db(Path(args.validate))
        print(f"Validation path: {result['path']}")
        print(f"Valid: {result['valid']}")
        print(f"Counts: {result['counts']}")
        if result["failures"]:
            print("Failures:")
            for failure in result["failures"]:
                print(f"- {failure}")
            raise SystemExit(1)
        print("No known real names or plaintext staging passwords found.")
        return

    result = create_anonymised_staging_db(
        source=Path(args.source),
        output=Path(args.output),
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )
    print_result(result)


if __name__ == "__main__":
    main()
