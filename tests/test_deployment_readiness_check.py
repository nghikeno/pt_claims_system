import json
import subprocess
import sys

import pytest

from app.deployment_readiness_check import evaluate_readiness, render_text_report


SECRET_URL = "postgresql://user:secret-password@example/db"


def _clear_env(monkeypatch):
    for name in [
        "APP_ENV",
        "DATABASE_URL",
        "PT_CLAIMS_DB_PATH",
        "GENERATED_FILE_MODE",
        "SESSION_TIMEOUT_MINUTES",
        "DB_PERF_DEBUG",
        "DB_POOL_MIN_SIZE",
        "DB_POOL_MAX_SIZE",
        "DOCUMENT_STORAGE_MODE",
        "OBJECT_STORAGE_PROVIDER",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_REGION",
        "OBJECT_STORAGE_ENDPOINT_URL",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_PREFIX",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_development_default_sqlite_pass(monkeypatch):
    import app.deployment_readiness_check as checker

    _clear_env(monkeypatch)
    monkeypatch.setattr(checker, "DB_PATH", checker.REAL_DB_PATH)

    result = checker.evaluate_readiness()

    assert result["app_env"] == "development"
    assert result["database_provider"] == "sqlite"
    assert result["using_local_sqlite_default"] is True
    assert result["final_status"] == "PASS"
    assert result["local_controlled_use_status"] == "PASS"


def test_staging_sqlite_non_staging_path_warns(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("PT_CLAIMS_DB_PATH", str(tmp_path / "pt_claims_test.db"))

    result = evaluate_readiness()

    assert result["final_status"] == "WARN"
    assert any("does not appear to be under data/staging" in warning for warning in result["warnings"])


def test_staging_postgresql_does_not_print_secret(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)

    result = evaluate_readiness()
    output = render_text_report(result)

    assert result["database_provider"] == "postgresql"
    assert result["database_url_set"] is True
    assert result["document_storage_mode"] in {"local", "ephemeral"}
    assert SECRET_URL not in output
    assert "secret-password" not in output


def test_production_without_database_url_blocked(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    result = evaluate_readiness()

    assert result["final_status"] == "BLOCK"
    assert any("Production requires DATABASE_URL" in issue for issue in result["blocking_issues"])


def test_production_with_sqlite_blocked(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = evaluate_readiness()

    assert any("Production with SQLite" in issue for issue in result["blocking_issues"])


def test_production_with_db_perf_debug_blocked(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("DB_PERF_DEBUG", "true")

    result = evaluate_readiness()

    assert result["final_status"] == "BLOCK"
    assert any("DB_PERF_DEBUG" in issue for issue in result["blocking_issues"])


def test_production_with_local_generated_files_blocked(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("GENERATED_FILE_MODE", "local")

    result = evaluate_readiness()

    assert any("local generated file mode" in issue for issue in result["blocking_issues"])


def test_production_readiness_reports_storage_and_secret_flags(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("GENERATED_FILE_MODE", "ephemeral")
    monkeypatch.setenv("DOCUMENT_STORAGE_MODE", "object_storage_pending")
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "30")

    result = evaluate_readiness()

    assert result["final_status"] == "BLOCK"
    assert result["real_data_production_status"] == "BLOCK"
    assert result["production_secret_flags"]["database_url"] is True
    assert result["production_secret_flags"]["object_storage_bucket"] is False
    assert result["document_storage_mode"] == "object_storage_pending"
    assert any("durable object storage" in issue for issue in result["blocking_issues"])


def test_production_object_storage_missing_config_is_blocked(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("DOCUMENT_STORAGE_MODE", "object_storage")
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "30")

    result = evaluate_readiness()

    assert result["final_status"] == "BLOCK"
    assert result["document_storage_ready"] is False
    assert "OBJECT_STORAGE_SECRET_ACCESS_KEY" in result["missing_storage_config_keys"]


def test_production_object_storage_configured_allows_storage_check_without_leaking(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)
    monkeypatch.setenv("DOCUMENT_STORAGE_MODE", "object_storage")
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "30")
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "r2")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "private-bucket")
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT_URL", "https://storage.example.invalid")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "access-key-value")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "secret-key-value")

    result = evaluate_readiness()
    output = render_text_report(result)
    payload = json.dumps(result)

    assert result["document_storage_ready"] is True
    assert result["document_storage_configured"] is True
    assert result["missing_storage_config_keys"] == []
    assert "access-key-value" not in output
    assert "secret-key-value" not in payload
    assert "private-bucket" not in payload


def test_json_output_does_not_include_database_url(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)

    result = evaluate_readiness()
    payload = json.dumps(result)

    assert "database_url_set" in payload
    assert SECRET_URL not in payload
    assert "secret-password" not in payload


def test_fail_on_block_exits_nonzero(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    completed = subprocess.run(
        [sys.executable, "-m", "app.deployment_readiness_check", "--fail-on-block"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "DATABASE_URL" not in completed.stdout or "://" not in completed.stdout


def test_json_cli_does_not_include_raw_database_url(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", SECRET_URL)

    completed = subprocess.run(
        [sys.executable, "-m", "app.deployment_readiness_check", "--json"],
        text=True,
        capture_output=True,
        check=True,
    )

    assert '"database_url_set": true' in completed.stdout
    assert SECRET_URL not in completed.stdout
    assert "secret-password" not in completed.stdout
