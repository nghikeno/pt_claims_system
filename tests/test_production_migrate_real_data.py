import json
import os
import sqlite3
import subprocess
import sys

import pytest

from app.production_migrate_real_data import (
    CONFIRMATION_PHRASE,
    build_dry_run_report,
    compare_counts,
    identity_reset_plan,
    identity_reset_sql,
    migrate_real_data,
    migration_order,
    render_text_report,
    target_is_empty,
)


SECRET_URL = "postgresql://user:secret-password@example/db"


def _make_source_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE lecturers (id INTEGER PRIMARY KEY AUTOINCREMENT, staff_number TEXT, full_name TEXT);
            CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, course_code TEXT);
            CREATE TABLE student_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, group_name TEXT, lecturer_id INTEGER, course_id INTEGER);
            CREATE TABLE timetable_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, lecturer_id INTEGER, group_id INTEGER);
            CREATE TABLE academic_calendar (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT);
            CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, student_number TEXT);
            CREATE TABLE group_enrolments (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, group_id INTEGER);
            CREATE TABLE user_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password_hash TEXT, password_salt TEXT);
            CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT);
            INSERT INTO lecturers (staff_number, full_name) VALUES ('1000', 'Demo Lecturer');
            INSERT INTO courses (course_code) VALUES ('CUS101');
            INSERT INTO student_groups (group_name, lecturer_id, course_id) VALUES ('DEMO_GROUP', 1, 1);
            INSERT INTO timetable_entries (lecturer_id, group_id) VALUES (1, 1);
            INSERT INTO academic_calendar (title) VALUES ('Demo Holiday');
            INSERT INTO students (student_number) VALUES ('STU001');
            INSERT INTO group_enrolments (student_id, group_id) VALUES (1, 1);
            INSERT INTO user_accounts (username, password_hash, password_salt) VALUES ('demo', 'super-secret-hash', 'super-secret-salt');
            INSERT INTO audit_logs (action) VALUES ('login_success');
            """
        )


def object_storage_env():
    return {
        "DATABASE_URL": SECRET_URL,
        "DOCUMENT_STORAGE_MODE": "object_storage",
        "OBJECT_STORAGE_PROVIDER": "r2",
        "OBJECT_STORAGE_BUCKET": "private-bucket",
        "OBJECT_STORAGE_REGION": "auto",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://storage.example.invalid",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key-value",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key-value",
    }


def assert_no_secrets(text):
    assert SECRET_URL not in text
    assert "secret-password" not in text
    assert "super-secret-hash" not in text
    assert "super-secret-salt" not in text
    assert "access-key-value" not in text
    assert "secret-key-value" not in text
    assert "private-bucket" not in text


def test_dry_run_does_not_write_and_does_not_print_secrets(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    report = build_dry_run_report(db_path, env=object_storage_env())
    text = render_text_report(report)

    assert report["writes_postgres"] is False
    assert report["source_counts"]["lecturers"] == 1
    assert report["target_configured"] is True
    assert_no_secrets(text)


def test_real_write_refuses_without_yes(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    with pytest.raises(PermissionError, match="--yes"):
        migrate_real_data(db_path, confirmation=CONFIRMATION_PHRASE, backup_acknowledged=True, env=object_storage_env())


def test_real_write_refuses_without_exact_confirmation(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    with pytest.raises(PermissionError, match="confirm-real-production-migration"):
        migrate_real_data(db_path, yes=True, confirmation="WRONG", backup_acknowledged=True, env=object_storage_env())


def test_real_write_refuses_without_database_url(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)
    env = object_storage_env()
    env.pop("DATABASE_URL")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        migrate_real_data(db_path, yes=True, confirmation=CONFIRMATION_PHRASE, backup_acknowledged=True, env=env)


def test_real_write_refuses_without_backup_acknowledgement(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    with pytest.raises(PermissionError, match="backup-acknowledged"):
        migrate_real_data(db_path, yes=True, confirmation=CONFIRMATION_PHRASE, env=object_storage_env())


def test_migration_order_is_parent_before_child():
    order = migration_order()

    assert order.index("lecturers") < order.index("student_groups")
    assert order.index("courses") < order.index("student_groups")
    assert order.index("student_groups") < order.index("timetable_entries")
    assert order.index("students") < order.index("group_enrolments")


def test_identity_sequence_reset_sql_is_generated():
    plan = identity_reset_plan()
    sql = identity_reset_sql("lecturers")

    assert any(item["table"] == "lecturers" for item in plan)
    assert "pg_get_serial_sequence('lecturers', 'id')" in sql
    assert "setval" in sql


def test_count_comparison_detects_mismatch():
    result = compare_counts({"lecturers": 15}, {"lecturers": 14}, ["lecturers"])

    assert result["matches"] is False
    assert result["mismatches"]["lecturers"] == {"source": 15, "target": 14}


def test_target_non_empty_check_blocks():
    assert target_is_empty({"lecturers": 0, "courses": 0}) is True
    assert target_is_empty({"lecturers": 1, "courses": 0}) is False


def test_json_output_does_not_leak_secrets(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    report = build_dry_run_report(db_path, env=object_storage_env())
    payload = json.dumps(report)

    assert_no_secrets(payload)


def test_cli_dry_run_does_not_print_database_url(tmp_path):
    db_path = tmp_path / "source.db"
    _make_source_db(db_path)

    completed = subprocess.run(
        [sys.executable, "-m", "app.production_migrate_real_data", "--dry-run", "--source", str(db_path), "--json"],
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "DATABASE_URL": SECRET_URL},
    )

    assert SECRET_URL not in completed.stdout
    assert "secret-password" not in completed.stdout
