import json
import os
import subprocess
import sys

from app.cloud_smoke_test import (
    DUMMY_SMOKE_TEST_CONTENT,
    all_dry_run,
    config_summary,
    postgres_smoke_test,
    storage_dry_run,
    storage_upload_dummy,
)


SECRET_URL = "postgresql://user:secret-password@example/db"
ACCESS_KEY = "access-key-value"
SECRET_KEY = "secret-key-value"
BUCKET = "private-bucket"


def object_storage_env():
    return {
        "APP_ENV": "staging",
        "DATABASE_URL": SECRET_URL,
        "DOCUMENT_STORAGE_MODE": "object_storage",
        "OBJECT_STORAGE_PROVIDER": "r2",
        "OBJECT_STORAGE_BUCKET": BUCKET,
        "OBJECT_STORAGE_REGION": "auto",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://storage.example.invalid",
        "OBJECT_STORAGE_ACCESS_KEY_ID": ACCESS_KEY,
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": SECRET_KEY,
        "OBJECT_STORAGE_PREFIX": "pt-claims",
        "OBJECT_STORAGE_FAKE_UPLOAD": "true",
    }


def assert_no_secrets(payload):
    text = json.dumps(payload) if not isinstance(payload, str) else payload
    assert SECRET_URL not in text
    assert "secret-password" not in text
    assert ACCESS_KEY not in text
    assert SECRET_KEY not in text
    assert BUCKET not in text


def test_config_only_does_not_leak_secrets():
    result = config_summary(object_storage_env())

    assert result["database_url_set"] is True
    assert result["document_storage_mode"] == "object_storage"
    assert result["missing_storage_config_keys"] == []
    assert_no_secrets(result)


def test_missing_database_url_warns_not_crashes():
    result = config_summary({"APP_ENV": "staging", "DOCUMENT_STORAGE_MODE": "ephemeral"})

    assert result["status"] == "WARN"
    assert any("DATABASE_URL is not set" in check["message"] for check in result["checks"])


def test_postgres_command_refuses_without_database_url():
    result = postgres_smoke_test({}, required=True)

    assert result["status"] == "BLOCK"
    assert result["database_url_set"] is False


def test_storage_dry_run_does_not_upload():
    result = storage_dry_run(object_storage_env())

    assert result["status"] == "PASS"
    assert result["uploaded"] is False
    assert_no_secrets(result)


def test_storage_upload_requires_yes():
    result = storage_upload_dummy(object_storage_env(), yes=False)

    assert result["status"] == "BLOCK"
    assert result["uploaded"] is False


def test_dummy_upload_uses_dummy_content_only_and_fake_storage():
    result = storage_upload_dummy(object_storage_env(), yes=True)

    assert result["status"] == "PASS"
    assert result["dummy_content_only"] is True
    assert result["object_key"].startswith("pt-claims/smoke-tests/pt-claims-smoke-test-")
    assert result["object_key"].endswith(".txt")
    assert result["uploaded"] is False
    assert DUMMY_SMOKE_TEST_CONTENT == "PT Claims smoke test dummy file only. No real data.\n"
    assert_no_secrets(result)


def test_all_dry_run_structured_output_does_not_leak_secrets():
    result = all_dry_run(object_storage_env())

    assert result["name"] == "all_dry_run"
    assert_no_secrets(result)


def test_storage_upload_cli_requires_yes(monkeypatch):
    env = object_storage_env()
    completed = subprocess.run(
        [sys.executable, "-m", "app.cloud_smoke_test", "--storage-upload-dummy"],
        env={**os.environ, **env},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "requires --yes" in completed.stdout
    assert_no_secrets(completed.stdout + completed.stderr)
