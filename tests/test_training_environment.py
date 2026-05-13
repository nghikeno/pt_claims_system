from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import config
from app.auth_service import verify_password
from app.create_training_database import create_training_database, ensure_safe_training_target
from app.migrate_training_database import CONFIRMATION_PHRASE, dry_run, ensure_training_source


def test_app_env_training_is_recognised(monkeypatch):
    monkeypatch.setenv("APP_ENV", "training")

    assert config.get_app_env() == "training"
    assert config.is_training() is True


def test_training_banner_exists_and_is_not_for_production():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    theme = Path("app_ui/theme.py").read_text(encoding="utf-8")

    assert "render_training_banner" in source
    assert "is_training()" in source
    assert "TRAINING ENVIRONMENT, dummy data only." in theme


def test_training_db_creation_refuses_real_production_db_path():
    with pytest.raises(RuntimeError, match="production SQLite"):
        ensure_safe_training_target("data/pt_claims.db")


def test_training_db_creation_produces_dummy_counts(tmp_path):
    output = tmp_path / "training" / "pt_claims_training.db"

    result = create_training_database(
        output,
        lecturer_password="TrainingLecturer@2026",
        admin_password="TrainingAdmin@2026",
        overwrite=True,
    )

    assert result["status"] == "CREATED"
    assert result["counts"]["lecturers"] == 1
    assert result["counts"]["courses"] == 2
    assert result["counts"]["student_groups"] == 3
    assert result["counts"]["students"] == 24
    assert result["counts"]["group_enrolments"] == 24
    assert result["counts"]["user_accounts"] == 2


def test_training_dummy_lecturer_account_is_hashed_and_linked(tmp_path):
    output = tmp_path / "training" / "pt_claims_training.db"
    create_training_database(output, lecturer_password="TrainingLecturer@2026", overwrite=True)

    with sqlite3.connect(output) as conn:
        conn.row_factory = sqlite3.Row
        account = conn.execute(
            """
            SELECT ua.username, ua.password_hash, ua.password_salt, ua.role, ua.lecturer_id, l.staff_number
            FROM user_accounts AS ua
            JOIN lecturers AS l ON l.id = ua.lecturer_id
            WHERE ua.username = '900001'
            """
        ).fetchone()
        other_lecturers = conn.execute("SELECT COUNT(*) FROM lecturers WHERE staff_number <> '900001'").fetchone()[0]
        visible_groups = conn.execute("SELECT COUNT(*) FROM student_groups WHERE lecturer_id = ?", (account["lecturer_id"],)).fetchone()[0]

    assert account["role"] == "lecturer"
    assert account["staff_number"] == "900001"
    assert account["password_hash"] != "TrainingLecturer@2026"
    assert verify_password("TrainingLecturer@2026", account["password_hash"], account["password_salt"]) is True
    assert other_lecturers == 0
    assert visible_groups == 3


def test_training_migration_refuses_real_source():
    with pytest.raises(RuntimeError, match="production SQLite"):
        ensure_training_source("data/pt_claims.db")


def test_training_migration_dry_run_uses_training_database_url_name(tmp_path):
    output = tmp_path / "training" / "pt_claims_training.db"
    create_training_database(output, lecturer_password="TrainingLecturer@2026", overwrite=True)

    result = dry_run(output, env={"TRAINING_DATABASE_URL": "postgresql://user:secret@example/db"})

    assert result["status"] == "PASS"
    assert result["target_env"] == "TRAINING_DATABASE_URL"
    assert result["writes_postgres"] is False
    assert "secret" not in str(result)
    assert CONFIRMATION_PHRASE == "I_UNDERSTAND_THIS_IS_TRAINING_DATA_ONLY"
