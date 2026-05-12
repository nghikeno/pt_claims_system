from app.document_storage import (
    get_document_storage,
    generate_download_url,
    document_storage_status,
    generated_document_base_dir,
    save_generated_file,
    storage_is_durable,
    store_generated_document_set,
    storage_summary,
    validate_storage_config,
)


def test_document_storage_local_mode_preserves_local_paths():
    status = document_storage_status(app_env="development", mode="local")

    assert status.mode == "local"
    assert status.local_path_allowed is True
    assert status.configured is True
    assert status.durable is False
    assert generated_document_base_dir().parts[-2:] == ("data", "generated")


def test_document_storage_blocks_local_in_production():
    status = document_storage_status(app_env="production", mode="local")

    assert status.blocking_issue
    assert "Production cannot use local" in status.blocking_issue


def test_document_storage_object_pending_blocks_production():
    status = document_storage_status(app_env="production", mode="object_storage_pending")

    assert status.configured is False
    assert status.blocking_issue == "Production requires configured durable object storage."


def test_ephemeral_storage_is_not_durable():
    status = document_storage_status(app_env="staging", mode="ephemeral")

    assert status.durable is False
    assert status.configured is True
    assert storage_is_durable({"DOCUMENT_STORAGE_MODE": "ephemeral"}) is False


def test_object_storage_missing_config_is_not_ready():
    result = validate_storage_config(env={"DOCUMENT_STORAGE_MODE": "object_storage"}, mode="object_storage")

    assert result.ready is False
    assert "OBJECT_STORAGE_BUCKET" in result.missing_keys
    assert "OBJECT_STORAGE_SECRET_ACCESS_KEY" in result.missing_keys


def test_object_storage_configured_fake_upload_returns_safe_reference(tmp_path):
    file_path = tmp_path / "claim.docx"
    file_path.write_text("demo", encoding="utf-8")
    env = {
        "DOCUMENT_STORAGE_MODE": "object_storage",
        "OBJECT_STORAGE_PROVIDER": "minio",
        "OBJECT_STORAGE_BUCKET": "demo-bucket",
        "OBJECT_STORAGE_REGION": "us-east-1",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://storage.example.invalid",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "example-access",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "example-secret",
        "OBJECT_STORAGE_PREFIX": "pt-claims",
        "OBJECT_STORAGE_FAKE_UPLOAD": "true",
    }

    storage = get_document_storage(env=env)
    stored = storage.save_generated_file(file_path, "generated_v2/claim.docx")

    assert stored.mode == "object_storage"
    assert stored.durable is True
    assert stored.uploaded is False
    assert stored.storage_key == "pt-claims/generated_v2/claim.docx"
    assert stored.reference == "s3://demo-bucket/pt-claims/generated_v2/claim.docx"
    assert "example-secret" not in str(stored.as_dict())


def test_object_storage_fake_signed_download_url_does_not_expose_secrets():
    env = {
        "DOCUMENT_STORAGE_MODE": "object_storage",
        "OBJECT_STORAGE_PROVIDER": "r2",
        "OBJECT_STORAGE_BUCKET": "demo-bucket",
        "OBJECT_STORAGE_REGION": "auto",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://storage.example.invalid",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "example-access",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "example-secret",
        "OBJECT_STORAGE_FAKE_UPLOAD": "true",
    }

    url = generate_download_url("generated_v2/claim.docx", env=env)

    assert url == "https://download.example.invalid/generated_v2/claim.docx?expires_in=900"
    assert "example-access" not in url
    assert "example-secret" not in url
    assert "demo-bucket" not in url


def test_local_storage_does_not_generate_signed_url(tmp_path):
    assert generate_download_url("generated_v2/claim.docx", env={"DOCUMENT_STORAGE_MODE": "local"}) is None


def test_local_save_generated_file_preserves_path(monkeypatch, tmp_path):
    file_path = tmp_path / "register.docx"
    file_path.write_text("demo", encoding="utf-8")
    monkeypatch.setenv("DOCUMENT_STORAGE_MODE", "local")

    stored = save_generated_file(file_path, "generated_v2/register.docx")

    assert stored.reference == str(file_path)
    assert stored.uploaded is False


def test_document_generation_storage_integration_uses_local_mode_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DOCUMENT_STORAGE_MODE", raising=False)
    output_dir = tmp_path / "generated_v2" / "2026" / "05" / "1000"
    output_dir.mkdir(parents=True)
    claim = output_dir / "claim.docx"
    claim.write_text("demo", encoding="utf-8")

    rows = store_generated_document_set([claim], output_dir)

    assert rows[0]["mode"] == "local"
    assert rows[0]["reference"] == str(claim)


def test_storage_summary_does_not_expose_secret_values(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "secret-bucket-name")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "very-secret-key")

    summary = storage_summary()

    assert "secret-bucket-name" not in str(summary)
    assert "very-secret-key" not in str(summary)
    assert "mode" in summary
