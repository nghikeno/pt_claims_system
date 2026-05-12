import sqlite3
import subprocess
import sys

from app.production_migration_plan import build_migration_plan, render_text_report


def _make_source_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE lecturers (id INTEGER PRIMARY KEY, staff_number TEXT, full_name TEXT);
            CREATE TABLE courses (id INTEGER PRIMARY KEY, course_code TEXT);
            CREATE TABLE student_groups (id INTEGER PRIMARY KEY, group_name TEXT);
            CREATE TABLE timetable_entries (id INTEGER PRIMARY KEY, lecturer_id INTEGER, group_id INTEGER);
            CREATE TABLE academic_calendar (id INTEGER PRIMARY KEY, title TEXT);
            CREATE TABLE students (id INTEGER PRIMARY KEY, student_number TEXT);
            CREATE TABLE group_enrolments (id INTEGER PRIMARY KEY, student_id INTEGER, group_id INTEGER);
            CREATE TABLE user_accounts (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, password_salt TEXT);
            CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, action TEXT);
            INSERT INTO lecturers VALUES (1, '1000', 'Demo Lecturer');
            INSERT INTO courses VALUES (1, 'CUS101');
            INSERT INTO student_groups VALUES (1, 'DEMO_GROUP');
            INSERT INTO timetable_entries VALUES (1, 1, 1);
            INSERT INTO students VALUES (1, 'STU001');
            INSERT INTO group_enrolments VALUES (1, 1, 1);
            INSERT INTO user_accounts VALUES (1, 'demo', 'hash', 'salt');
            """
        )


def test_production_migration_dry_run_reports_counts_and_blockers(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    plan = build_migration_plan(db_path)
    report = render_text_report(plan)

    assert plan["status"] == "BLOCK"
    assert plan["row_counts"]["lecturers"] == 1
    assert "lecturers" in plan["tables_covered"]
    assert any("dry-run" in blocker.lower() or "real data migration" in blocker.lower() for blocker in plan["blockers"])
    assert "DATABASE_URL" not in report


def test_production_migration_cli_requires_dry_run():
    completed = subprocess.run(
        [sys.executable, "-m", "app.production_migration_plan"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "dry-run" in completed.stderr.lower() or "dry-run" in completed.stdout.lower()


def test_production_migration_cli_dry_run_does_not_print_database_url(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    completed = subprocess.run(
        [sys.executable, "-m", "app.production_migration_plan", "--dry-run", "--source", str(db_path)],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Production Migration Dry-Run Plan" in completed.stdout
    assert "://" not in completed.stdout
