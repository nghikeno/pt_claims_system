import gc
import json
import sqlite3

import pytest

from app.production_to_local_refresh import (
    COPY_CONFIRMATION,
    REPLACE_CONFIRMATION,
    build_refreshed_copy,
    build_report,
    main,
    replace_supported_tables,
    render_text_report,
    run_refresh,
    validate_output_path,
    validate_local_path,
)
from tests.test_local_first_sync import SECRET_URL, make_db


class FakeRuntimeConnection:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        self.conn.close()
        return False


def configure_fake_postgres(monkeypatch, prod_path):
    monkeypatch.setattr("app.production_to_local_refresh.database_provider", lambda: "postgresql")
    monkeypatch.setattr("app.production_to_local_refresh.database_url", lambda: SECRET_URL)
    monkeypatch.setattr("app.production_to_local_refresh.get_runtime_connection", lambda: FakeRuntimeConnection(prod_path))


def test_summary_reports_counts_without_secrets(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod)
    gc.collect()
    configure_fake_postgres(monkeypatch, prod)

    report = build_report(local)
    text = json.dumps(report)

    assert report["local_counts"]["lecturers"] == 1
    assert report["production_counts"]["lecturers"] == 1
    assert SECRET_URL not in text
    assert "secret-password" not in text


def test_dry_run_does_not_write_local_or_production(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod)
    configure_fake_postgres(monkeypatch, prod)

    before_local = local.read_bytes()
    before_prod = prod.read_bytes()
    build_report(local)

    assert local.read_bytes() == before_local
    assert prod.read_bytes() == before_prod


def test_refresh_output_file_is_created_from_local_copy_and_replaces_supported_tables(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    output = tmp_path / "refreshed.db"
    make_db(local)
    make_db(prod)
    with sqlite3.connect(prod) as conn:
        conn.execute("UPDATE lecturers SET full_name = 'Production Current'")
        conn.execute("INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('STU002', 'Two', 'B', 'Student Two', 1)")
    configure_fake_postgres(monkeypatch, prod)

    result = run_refresh(args(yes=True, output=str(output), local_path=str(local), confirm_refresh=COPY_CONFIRMATION))

    assert output.exists()
    assert result["refresh_result"]["counts"]["students"] == 2
    with sqlite3.connect(output) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT full_name FROM lecturers WHERE staff_number = '990001'").fetchone()["full_name"] == "Production Current"
        assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2


def test_user_accounts_and_password_hashes_are_preserved_locally(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    output = tmp_path / "refreshed.db"
    make_db(local)
    make_db(prod)
    with sqlite3.connect(prod) as conn:
        conn.execute("UPDATE user_accounts SET password_hash = 'PROD-HASH', password_salt = 'PROD-SALT'")
    configure_fake_postgres(monkeypatch, prod)

    run_refresh(args(yes=True, output=str(output), local_path=str(local), confirm_refresh=COPY_CONFIRMATION))

    with sqlite3.connect(output) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT password_hash, password_salt FROM user_accounts WHERE username = 'admin'").fetchone()
        assert row["password_hash"] == "SECRET-HASH"
        assert row["password_salt"] == "SECRET-SALT"


def test_audit_logs_are_preserved_locally(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    output = tmp_path / "refreshed.db"
    make_db(local)
    make_db(prod)
    with sqlite3.connect(prod) as conn:
        conn.execute("UPDATE audit_logs SET action = 'production_action'")
    configure_fake_postgres(monkeypatch, prod)

    run_refresh(args(yes=True, output=str(output), local_path=str(local), confirm_refresh=COPY_CONFIRMATION))

    with sqlite3.connect(output) as conn:
        assert conn.execute("SELECT action FROM audit_logs").fetchone()[0] == "login_success"


def test_missing_database_url_blocks(monkeypatch, tmp_path):
    local = tmp_path / "local.db"
    make_db(local)
    monkeypatch.setattr("app.production_to_local_refresh.database_provider", lambda: "sqlite")
    monkeypatch.setattr("app.production_to_local_refresh.database_url", lambda: "")

    report = build_report(local)

    assert any("DATABASE_URL" in blocker for blocker in report["blockers"])


def test_non_postgresql_provider_blocks_refresh(monkeypatch, tmp_path):
    local = tmp_path / "local.db"
    make_db(local)
    monkeypatch.setattr("app.production_to_local_refresh.database_provider", lambda: "sqlite")
    monkeypatch.setattr("app.production_to_local_refresh.database_url", lambda: "sqlite:///local")

    report = build_report(local)

    assert any("PostgreSQL" in blocker for blocker in report["blockers"])


def test_training_db_path_is_blocked_unless_explicit(tmp_path):
    training_dir = tmp_path / "data" / "training"
    training_dir.mkdir(parents=True)
    local = training_dir / "pt_claims_training.db"
    make_db(local)

    assert validate_local_path(local)
    assert validate_local_path(local, allow_training_local=True) == []


def test_replace_local_requires_backup_local(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod)
    configure_fake_postgres(monkeypatch, prod)

    with pytest.raises(PermissionError, match="backup-local"):
        run_refresh(args(yes=True, replace_local=True, local_path=str(local), confirm_refresh=REPLACE_CONFIRMATION))


def test_replace_local_creates_timestamped_backup(tmp_path, monkeypatch):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    make_db(local)
    make_db(prod)
    gc.collect()
    with sqlite3.connect(prod) as conn:
        conn.execute("UPDATE lecturers SET full_name = 'Production Current'")
    configure_fake_postgres(monkeypatch, prod)

    result = run_refresh(
        args(
            yes=True,
            replace_local=True,
            backup_local=True,
            local_path=str(local),
            confirm_refresh=REPLACE_CONFIRMATION,
        )
    )

    assert result["backup_path"]
    assert "BEFORE_PRODUCTION_REFRESH" in result["backup_path"]
    assert result["blockers"] == []
    assert result["local_db_replaced"] is True
    text = render_text_report(result)
    assert "Local backup created:" in text
    assert "Local DB replaced successfully." in text
    assert "Output path cannot be the active local DB unless --replace-local is used." not in text
    with sqlite3.connect(local) as conn:
        assert conn.execute("SELECT full_name FROM lecturers").fetchone()[0] == "Production Current"


def test_output_equal_active_local_without_replace_local_blocks(tmp_path):
    local = tmp_path / "local.db"
    make_db(local)

    blockers = validate_output_path(local, local, replace_local=False)

    assert "Output path cannot be the active local DB unless --replace-local is used." in blockers


def test_output_equal_active_local_with_replace_local_does_not_block(tmp_path):
    local = tmp_path / "local.db"
    make_db(local)

    blockers = validate_output_path(local, local, replace_local=True)

    assert "Output path cannot be the active local DB unless --replace-local is used." not in blockers


def test_sqlite_fk_order_refreshes_child_tables(tmp_path):
    local = tmp_path / "local.db"
    prod = tmp_path / "prod.db"
    output = tmp_path / "refreshed.db"
    make_db(local)
    make_db(prod)
    with sqlite3.connect(prod) as prod_conn:
        prod_conn.row_factory = sqlite3.Row
        production_rows = {}
        for table in ["lecturers", "courses", "student_groups", "timetable_entries", "students", "group_enrolments", "academic_calendar"]:
            production_rows[table] = [dict(row) for row in prod_conn.execute(f"SELECT * FROM {table}")]

    result = build_refreshed_copy(local, output, production_rows)

    assert result["counts"]["group_enrolments"] == 1
    with sqlite3.connect(output) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_main_closes_postgres_pool(monkeypatch, tmp_path, capsys):
    local = tmp_path / "local.db"
    make_db(local)
    closed = {"value": False}
    monkeypatch.setattr("app.production_to_local_refresh.DB_PATH", local)
    monkeypatch.setattr("app.production_to_local_refresh.database_provider", lambda: "sqlite")
    monkeypatch.setattr("app.production_to_local_refresh.database_url", lambda: "")
    monkeypatch.setattr("app.production_to_local_refresh.close_postgres_pool", lambda: closed.__setitem__("value", True))

    main(["--dry-run"])

    assert closed["value"] is True
    assert "DATABASE_URL" in capsys.readouterr().out


def args(**overrides):
    defaults = {
        "yes": False,
        "output": "",
        "replace_local": False,
        "backup_local": False,
        "confirm_refresh": "",
        "local_path": "",
        "allow_training_local": False,
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()
