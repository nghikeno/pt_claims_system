import sqlite3
from pathlib import Path

from app.config import DATA_DIR, DB_PATH, DOCX_TEMPLATES_DIR, EXPORTS_DIR, GENERATED_DIR, PILOTS_DIR, TEMPLATES_DIR


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DB_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    DOCX_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    PILOTS_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lecturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_number TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                full_name TEXT NOT NULL,
                highest_qualification TEXT NOT NULL,
                id_or_passport_number TEXT NOT NULL,
                paye_number TEXT NOT NULL,
                physical_address TEXT NOT NULL,
                contact_number TEXT NOT NULL,
                tariff_per_hour REAL NOT NULL CHECK (tariff_per_hour >= 0),
                campus TEXT NOT NULL,
                contract_start_date TEXT NOT NULL,
                contract_end_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL UNIQUE,
                course_name TEXT NOT NULL,
                faculty TEXT NOT NULL,
                department TEXT NOT NULL,
                budget_allocation TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS student_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                lecturer_id INTEGER,
                campus TEXT NOT NULL,
                study_mode TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (course_id) REFERENCES courses(id),
                FOREIGN KEY (lecturer_id) REFERENCES lecturers(id)
            );

            CREATE TABLE IF NOT EXISTS timetable_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecturer_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                day_of_week TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                effective_start_date TEXT NOT NULL,
                effective_end_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (lecturer_id) REFERENCES lecturers(id),
                FOREIGN KEY (group_id) REFERENCES student_groups(id)
            );

            CREATE TABLE IF NOT EXISTS academic_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                calendar_type TEXT NOT NULL,
                action TEXT NOT NULL,
                allow_override INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT NOT NULL UNIQUE,
                surname TEXT,
                initials TEXT,
                full_name TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS group_enrolments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE (student_id, group_id),
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (group_id) REFERENCES student_groups(id)
            );

            CREATE TABLE IF NOT EXISTS user_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'lecturer')),
                lecturer_id INTEGER,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT,
                FOREIGN KEY (lecturer_id) REFERENCES lecturers(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_account_id INTEGER,
                username TEXT,
                role TEXT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details_json TEXT,
                ip_address TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_account_id) REFERENCES user_accounts(id)
            );
            """
        )
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(student_groups)").fetchall()]
        if "lecturer_id" not in columns:
            conn.execute("ALTER TABLE student_groups ADD COLUMN lecturer_id INTEGER")
        calendar_columns = [row["name"] for row in conn.execute("PRAGMA table_info(academic_calendar)").fetchall()]
        calendar_migrations = {
            "start_time": "ALTER TABLE academic_calendar ADD COLUMN start_time TEXT",
            "end_time": "ALTER TABLE academic_calendar ADD COLUMN end_time TEXT",
            "scope_type": "ALTER TABLE academic_calendar ADD COLUMN scope_type TEXT NOT NULL DEFAULT 'all'",
            "lecturer_id": "ALTER TABLE academic_calendar ADD COLUMN lecturer_id INTEGER",
            "course_id": "ALTER TABLE academic_calendar ADD COLUMN course_id INTEGER",
            "group_id": "ALTER TABLE academic_calendar ADD COLUMN group_id INTEGER",
            "exclude_from_claims_and_registers": "ALTER TABLE academic_calendar ADD COLUMN exclude_from_claims_and_registers INTEGER NOT NULL DEFAULT 1",
            "notes": "ALTER TABLE academic_calendar ADD COLUMN notes TEXT",
            "active": "ALTER TABLE academic_calendar ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            "created_at": "ALTER TABLE academic_calendar ADD COLUMN created_at TEXT",
            "updated_at": "ALTER TABLE academic_calendar ADD COLUMN updated_at TEXT",
        }
        for column, sql in calendar_migrations.items():
            if column not in calendar_columns:
                conn.execute(sql)
