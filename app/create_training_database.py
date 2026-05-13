from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.auth_service import hash_password
from app.config import DATA_DIR, REAL_DB_PATH
from app.database import init_db


DEFAULT_TRAINING_DB_PATH = DATA_DIR / "training" / "pt_claims_training.db"
CORE_TABLES = [
    "lecturers",
    "courses",
    "student_groups",
    "timetable_entries",
    "academic_calendar",
    "students",
    "group_enrolments",
    "user_accounts",
]


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _looks_like_real_db(path: str | Path) -> bool:
    resolved = Path(path).expanduser().resolve()
    return resolved == REAL_DB_PATH.resolve() or resolved.name == "pt_claims.db"


def ensure_safe_training_target(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    if _looks_like_real_db(target):
        raise RuntimeError("Refusing to create training data in the production SQLite database path.")
    if "training" not in {part.lower() for part in target.parts}:
        raise RuntimeError("Training database path must live under a training directory.")
    return target


def _insert_user(conn: sqlite3.Connection, username: str, password: str, role: str, lecturer_id: int | None = None) -> None:
    password_hash, password_salt = hash_password(password)
    now = _now()
    conn.execute(
        """
        INSERT INTO user_accounts (
            username, password_hash, password_salt, role, lecturer_id,
            must_change_password, active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
        """,
        (username, password_hash, password_salt, role, lecturer_id, now, now),
    )


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in CORE_TABLES}


def create_training_database(
    output_path: str | Path = DEFAULT_TRAINING_DB_PATH,
    *,
    lecturer_password: str,
    admin_password: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not lecturer_password:
        raise ValueError("Training lecturer password is required.")
    target = ensure_safe_training_target(output_path)
    if dry_run:
        return {"status": "DRY_RUN", "output_path": str(target), "would_write": False}
    if target.exists() and not overwrite:
        raise RuntimeError("Training database already exists. Use --overwrite to recreate it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    init_db(target)
    with _connect(target) as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                id, staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES (1, '900001', 'Ms', 'Training Lecturer', 'Training Qualification',
                    'TRAINING-ID-900001', 'TRAINING-PAYE-900001', 'Training Address',
                    '0800000000', 440, 'Training Campus', '2026-04-01', '2026-11-30', 1)
            """
        )
        courses = [
            (1, "CUS411S", "Computer User Skills", "Computing and Informatics", "Informatics", "TRAINING-BUDGET", 1),
            (2, "ICT521S", "Information Competence", "Computing and Informatics", "Informatics", "TRAINING-BUDGET", 1),
        ]
        conn.executemany(
            "INSERT INTO courses (id, course_code, course_name, faculty, department, budget_allocation, active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            courses,
        )
        groups = [
            (1, "TRAINING_GROUP_A_FT_2026", 1, 1, "Training Campus", "Full-time", 1),
            (2, "TRAINING_GROUP_B_FT_2026", 1, 1, "Training Campus", "Full-time", 1),
            (3, "TRAINING_GROUP_A_FT_2026", 2, 1, "Training Campus", "Full-time", 1),
        ]
        conn.executemany(
            "INSERT INTO student_groups (id, group_name, course_id, lecturer_id, campus, study_mode, active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            groups,
        )
        timetable = [
            (1, 1, 1, "Monday", "08:00", "09:30", "2026-04-30", "2026-05-29", 1),
            (2, 1, 2, "Wednesday", "10:00", "11:30", "2026-04-30", "2026-05-29", 1),
            (3, 1, 3, "Friday", "12:00", "13:30", "2026-04-30", "2026-05-29", 1),
        ]
        conn.executemany(
            """
            INSERT INTO timetable_entries (
                id, lecturer_id, group_id, day_of_week, start_time, end_time,
                effective_start_date, effective_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            timetable,
        )
        students = []
        enrolments = []
        student_id = 1
        for group_id in (1, 2, 3):
            for index in range(1, 9):
                number = f"TRN{student_id:06d}"
                students.append((student_id, number, f"TrainingSurname{student_id:03d}", "TS", f"Training Student {student_id:03d}", 1))
                enrolments.append((student_id, student_id, group_id, 1))
                student_id += 1
        conn.executemany(
            "INSERT INTO students (id, student_number, surname, initials, full_name, active) VALUES (?, ?, ?, ?, ?, ?)",
            students,
        )
        conn.executemany(
            "INSERT INTO group_enrolments (id, student_id, group_id, active) VALUES (?, ?, ?, ?)",
            enrolments,
        )
        now = _now()
        calendar_rows = [
            ("Workers' Day", "2026-05-01", "2026-05-01", "Public Holiday", "exclude", 0, None, None, "all", None, None, None, 1, "Training calendar reference", 1, now, now),
            ("Ascension Day", "2026-05-14", "2026-05-14", "Public Holiday", "exclude", 0, None, None, "all", None, None, None, 1, "Training calendar reference", 1, now, now),
        ]
        conn.executemany(
            """
            INSERT INTO academic_calendar (
                title, start_date, end_date, calendar_type, action, allow_override,
                start_time, end_time, scope_type, lecturer_id, course_id, group_id,
                exclude_from_claims_and_registers, notes, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            calendar_rows,
        )
        _insert_user(conn, "900001", lecturer_password, "lecturer", lecturer_id=1)
        if admin_password:
            _insert_user(conn, "training_admin", admin_password, "admin")
        counts = _counts(conn)
    return {"status": "CREATED", "output_path": str(target), "would_write": True, "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a dummy-only PT Claims training SQLite database.")
    parser.add_argument("--output", type=Path, default=DEFAULT_TRAINING_DB_PATH)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-admin", action="store_true")
    args = parser.parse_args()
    lecturer_password = os.environ.get("TRAINING_LECTURER_PASSWORD", "")
    admin_password = os.environ.get("TRAINING_ADMIN_PASSWORD", "") if args.include_admin else None
    if not args.dry_run and not lecturer_password:
        raise SystemExit("TRAINING_LECTURER_PASSWORD must be set. Value is never printed.")
    if args.include_admin and not args.dry_run and not admin_password:
        raise SystemExit("TRAINING_ADMIN_PASSWORD must be set when --include-admin is used. Value is never printed.")
    result = create_training_database(
        args.output,
        lecturer_password=lecturer_password or "dry-run-placeholder",
        admin_password=admin_password,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print(f"Training DB status: {result['status']}")
    print(f"Output path: {result['output_path']}")
    if result.get("counts"):
        for table, count in result["counts"].items():
            print(f"{table}: {count}")
    print("Secrets printed: no")


if __name__ == "__main__":
    main()
