import json
import sqlite3

import pytest

from app.local_first_sync import (
    CONFIRMATION_PHRASE,
    EXCLUDED_TABLES,
    build_sync_plan,
    main,
    open_sqlite,
    parse_tables,
    render_text_report,
    run_apply,
    table_counts,
)


SECRET_URL = "postgresql://user:secret-password@example.invalid/db"


def make_db(path, variant="base"):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE lecturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_number TEXT UNIQUE,
                title TEXT,
                full_name TEXT,
                highest_qualification TEXT,
                id_or_passport_number TEXT,
                paye_number TEXT,
                physical_address TEXT,
                contact_number TEXT,
                tariff_per_hour REAL,
                campus TEXT,
                contract_start_date TEXT,
                contract_end_date TEXT,
                active INTEGER
            );
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT UNIQUE,
                course_name TEXT,
                faculty TEXT,
                department TEXT,
                budget_allocation TEXT,
                active INTEGER
            );
            CREATE TABLE student_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                course_id INTEGER,
                lecturer_id INTEGER,
                campus TEXT,
                study_mode TEXT,
                active INTEGER
            );
            CREATE TABLE timetable_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecturer_id INTEGER,
                group_id INTEGER,
                day_of_week TEXT,
                start_time TEXT,
                end_time TEXT,
                effective_start_date TEXT,
                effective_end_date TEXT,
                active INTEGER
            );
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT UNIQUE,
                surname TEXT,
                initials TEXT,
                full_name TEXT,
                active INTEGER
            );
            CREATE TABLE group_enrolments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                group_id INTEGER,
                active INTEGER
            );
            CREATE TABLE academic_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                start_date TEXT,
                end_date TEXT,
                calendar_type TEXT,
                action TEXT,
                allow_override INTEGER DEFAULT 0,
                start_time TEXT,
                end_time TEXT,
                scope_type TEXT DEFAULT 'all',
                lecturer_id INTEGER,
                course_id INTEGER,
                group_id INTEGER,
                exclude_from_claims_and_registers INTEGER DEFAULT 1,
                notes TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE user_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password_hash TEXT, password_salt TEXT);
            CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT);
            """
        )
        if variant != "empty":
            lecturer_name = "Local Lecturer"
            student_name = "Student One"
            if variant == "conflicting_names":
                lecturer_name = "Production Lecturer"
                student_name = "Different Student"
            conn.execute(
                """
                INSERT INTO lecturers (
                    staff_number, title, full_name, highest_qualification, id_or_passport_number,
                    paye_number, physical_address, contact_number, tariff_per_hour, campus,
                    contract_start_date, contract_end_date, active
                )
                VALUES ('990001', 'Ms', ?, 'MSc', 'SECRET-ID', 'SECRET-PAYE', 'SECRET-ADDRESS',
                        'SECRET-PHONE', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
                """,
                (lecturer_name,),
            )
            conn.execute(
                """
                INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active)
                VALUES ('CUS411S', 'Computing', 'FCI', 'Informatics', 'BUDGET', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
                VALUES ('LOCAL_GROUP', 1, 1, 'Windhoek Main Campus', 'Full-time', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO timetable_entries (lecturer_id, group_id, day_of_week, start_time, end_time, effective_start_date, effective_end_date, active)
                VALUES (1, 1, 'Monday', '08:00', '09:00', '2026-02-01', '2026-06-30', 1)
                """
            )
            conn.execute(
                "INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('STU001', 'Surname', 'A', ?, 1)",
                (student_name,),
            )
            conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (1, 1, 1)")
            conn.execute(
                """
                INSERT INTO academic_calendar (title, start_date, end_date, calendar_type, action, scope_type, active)
                VALUES ('Holiday', '2026-05-01', '2026-05-01', 'Public Holiday', 'exclude', 'all', 1)
                """
            )
            conn.execute("INSERT INTO user_accounts (username, password_hash, password_salt) VALUES ('admin', 'SECRET-HASH', 'SECRET-SALT')")
            conn.execute("INSERT INTO audit_logs (action) VALUES ('login_success')")


def plan_for(tmp_path, local_variant="base", prod_variant="empty", tables=None):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local, local_variant)
    make_db(prod, prod_variant)
    with open_sqlite(local) as local_conn, open_sqlite(prod) as prod_conn:
        return build_sync_plan(local_conn, prod_conn, tables or parse_tables(None))


def table_summary(report, table):
    return next(item for item in report["plans"] if item["table"] == table)


def test_dry_run_builds_insert_plan_for_supported_tables(tmp_path):
    report = plan_for(tmp_path)

    assert table_summary(report, "lecturers")["inserts"] == 1
    assert table_summary(report, "courses")["inserts"] == 1
    assert table_summary(report, "student_groups")["inserts"] == 1
    assert table_summary(report, "timetable_entries")["inserts"] == 1
    assert table_summary(report, "students")["inserts"] == 1
    assert table_summary(report, "group_enrolments")["inserts"] == 1
    assert table_summary(report, "academic_calendar")["inserts"] == 1
    assert "user_accounts" in report["excluded_tables"]
    assert "audit_logs" in report["excluded_tables"]


def test_dry_run_detects_duplicate_natural_keys(tmp_path):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod, "empty")
    with sqlite3.connect(local) as conn:
        conn.execute(
            """
            INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active)
            VALUES ('LOCAL_GROUP', 1, 1, 'Windhoek Main Campus', 'Full-time', 1)
            """
        )
    with open_sqlite(local) as local_conn, open_sqlite(prod) as prod_conn:
        report = build_sync_plan(local_conn, prod_conn, ["student_groups"])

    assert table_summary(report, "student_groups")["conflicts"] == 1
    assert "student_groups has 1 conflict" in " ".join(report["blockers"])


def test_conflicting_lecturer_same_staff_number_is_blocked(tmp_path):
    report = plan_for(tmp_path, local_variant="base", prod_variant="conflicting_names", tables=["lecturers"])

    assert table_summary(report, "lecturers")["conflicts"] == 1
    assert "conflicting production values" in table_summary(report, "lecturers")["records"]["conflicts"][0]["reason"]


def test_conflicting_student_same_student_number_is_blocked(tmp_path):
    report = plan_for(tmp_path, local_variant="base", prod_variant="conflicting_names", tables=["students"])

    assert table_summary(report, "students")["conflicts"] == 1


def test_timetable_overlap_is_blocked(tmp_path):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod)
    with sqlite3.connect(local) as conn:
        conn.execute("DELETE FROM timetable_entries")
        conn.execute(
            """
            INSERT INTO timetable_entries (lecturer_id, group_id, day_of_week, start_time, end_time, effective_start_date, effective_end_date, active)
            VALUES (1, 1, 'Monday', '08:30', '09:30', '2026-02-01', '2026-06-30', 1)
            """
        )
    with open_sqlite(local) as local_conn, open_sqlite(prod) as prod_conn:
        report = build_sync_plan(local_conn, prod_conn, ["timetable_entries"])

    assert table_summary(report, "timetable_entries")["conflicts"] == 1
    assert "overlaps" in table_summary(report, "timetable_entries")["records"]["conflicts"][0]["reason"]


def test_generic_groups_are_blocked(tmp_path):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod, "empty")
    with sqlite3.connect(local) as conn:
        conn.execute("UPDATE student_groups SET lecturer_id = NULL")
    with open_sqlite(local) as local_conn, open_sqlite(prod) as prod_conn:
        report = build_sync_plan(local_conn, prod_conn, ["student_groups"])

    assert table_summary(report, "student_groups")["conflicts"] == 1
    assert "Generic groups" in table_summary(report, "student_groups")["records"]["conflicts"][0]["reason"]


def test_write_mode_refuses_without_postgresql_provider(monkeypatch):
    monkeypatch.setattr("app.local_first_sync.database_provider", lambda: "sqlite")
    monkeypatch.setattr("app.local_first_sync.database_url", lambda: "")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        run_apply(arg_obj(yes=True, backup_acknowledged=True, confirm_sync=CONFIRMATION_PHRASE))


def test_write_mode_refuses_without_yes():
    with pytest.raises(PermissionError, match="--yes"):
        run_apply(arg_obj(yes=False, backup_acknowledged=True, confirm_sync=CONFIRMATION_PHRASE))


def test_write_mode_refuses_without_backup_acknowledgement():
    with pytest.raises(PermissionError, match="backup-acknowledged"):
        run_apply(arg_obj(yes=True, backup_acknowledged=False, confirm_sync=CONFIRMATION_PHRASE))


def test_write_mode_refuses_without_exact_confirmation():
    with pytest.raises(PermissionError, match="confirm-sync"):
        run_apply(arg_obj(yes=True, backup_acknowledged=True, confirm_sync="WRONG"))


def test_report_does_not_include_user_accounts_audit_logs_or_secrets(tmp_path):
    report = plan_for(tmp_path)
    text = render_text_report(report)
    payload = json.dumps(report)

    for excluded in EXCLUDED_TABLES:
        assert excluded in payload
    assert "SECRET-HASH" not in text
    assert "SECRET-SALT" not in text
    assert "SECRET-ID" not in text
    assert "SECRET-PAYE" not in text


def test_placeholder_conversion_is_used_for_postgresql(monkeypatch):
    monkeypatch.setattr("app.db_provider.database_provider", lambda: "postgresql")
    monkeypatch.setattr("app.config.database_provider", lambda: "postgresql")
    from app.db_provider import convert_placeholders

    assert convert_placeholders("SELECT * FROM lecturers WHERE staff_number = ?") == "SELECT * FROM lecturers WHERE staff_number = %s"


def test_summary_counts_do_not_require_excluded_tables(tmp_path):
    local = tmp_path / "local.db"
    make_db(local)
    with open_sqlite(local) as conn:
        counts = table_counts(conn)

    assert counts["lecturers"] == 1
    assert "user_accounts" not in counts


def test_table_filter_parses_supported_tables_only():
    assert parse_tables("lecturers,student_groups") == ["lecturers", "student_groups"]
    with pytest.raises(ValueError):
        parse_tables("user_accounts")


def test_cli_json_report_does_not_leak_database_url(monkeypatch, capsys, tmp_path):
    local = tmp_path / "local.db"
    make_db(local)
    monkeypatch.setattr("app.local_first_sync.DB_PATH", local)
    monkeypatch.setattr("app.local_first_sync.database_provider", lambda: "sqlite")
    monkeypatch.setattr("app.local_first_sync.database_url", lambda: SECRET_URL)

    exit_code = main(["--dry-run", "--json", "--tables", "lecturers"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert SECRET_URL not in captured.out
    assert "secret-password" not in captured.out


def arg_obj(**overrides):
    defaults = {
        "yes": False,
        "backup_acknowledged": False,
        "confirm_sync": "",
        "tables": "",
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()
