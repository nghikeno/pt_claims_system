from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import GENERATED_DIR, generated_file_mode, get_app_env, get_setting


VALID_DOCUMENT_STORAGE_MODES = {"local", "ephemeral", "object_storage_pending", "object_storage"}
OBJECT_STORAGE_CONFIG_KEYS = [
    "OBJECT_STORAGE_PROVIDER",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_ENDPOINT_URL",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
]
OBJECT_STORAGE_OPTIONAL_KEYS = ["OBJECT_STORAGE_PREFIX"]


@dataclass(frozen=True)
class DocumentStorageStatus:
    mode: str
    durable: bool
    local_path_allowed: bool
    configured: bool
    message: str
    blocking_issue: str | None = None


@dataclass(frozen=True)
class StorageValidationResult:
    mode: str
    ready: bool
    durable: bool
    missing_keys: list[str] = field(default_factory=list)
    secret_flags: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blocking_issue: str | None = None


@dataclass(frozen=True)
class StoredDocument:
    local_path: str
    storage_key: str
    mode: str
    durable: bool
    reference: str
    uploaded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "local_path": self.local_path,
            "storage_key": self.storage_key,
            "mode": self.mode,
            "durable": self.durable,
            "reference": self.reference,
            "uploaded": self.uploaded,
        }


def _setting_from(env: dict[str, str] | None, name: str, default: Any = "") -> Any:
    if env is not None:
        return env.get(name, default)
    return get_setting(name, default)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _bool_setting(env: dict[str, str] | None, name: str, default: bool = False) -> bool:
    value = _setting_from(env, name, "true" if default else "false")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def document_storage_mode(env: dict[str, str] | None = None) -> str:
    mode = _clean(_setting_from(env, "DOCUMENT_STORAGE_MODE", generated_file_mode())).lower()
    return mode if mode in VALID_DOCUMENT_STORAGE_MODES else "local"


def object_storage_config_present(env: dict[str, str] | None = None) -> bool:
    return validate_storage_config(env=env, mode="object_storage").ready


def validate_storage_config(
    env: dict[str, str] | None = None,
    mode: str | None = None,
    app_env: str | None = None,
) -> StorageValidationResult:
    app_env = app_env or _clean(_setting_from(env, "APP_ENV", get_app_env())).lower() or "development"
    mode = (mode or document_storage_mode(env)).strip().lower()
    if mode not in VALID_DOCUMENT_STORAGE_MODES:
        mode = "local"

    secret_flags = {key.lower(): bool(_clean(_setting_from(env, key, ""))) for key in OBJECT_STORAGE_CONFIG_KEYS}

    if mode == "local":
        blocking = "Production cannot use local generated document storage." if app_env == "production" else None
        return StorageValidationResult(
            mode=mode,
            ready=blocking is None,
            durable=False,
            secret_flags=secret_flags,
            blocking_issue=blocking,
        )
    if mode == "ephemeral":
        blocking = "Production cannot rely on ephemeral generated document storage." if app_env == "production" else None
        return StorageValidationResult(
            mode=mode,
            ready=blocking is None,
            durable=False,
            secret_flags=secret_flags,
            warnings=["Generated files are not durable in ephemeral mode."],
            blocking_issue=blocking,
        )
    if mode == "object_storage_pending":
        return StorageValidationResult(
            mode=mode,
            ready=False,
            durable=False,
            secret_flags=secret_flags,
            blocking_issue="Production requires configured durable object storage.",
        )

    missing = [key for key in OBJECT_STORAGE_CONFIG_KEYS if not _clean(_setting_from(env, key, ""))]
    return StorageValidationResult(
        mode=mode,
        ready=not missing,
        durable=not missing,
        missing_keys=missing,
        secret_flags=secret_flags,
        blocking_issue=None if not missing else "Object storage mode is missing required configuration.",
    )


def document_storage_status(
    app_env: str | None = None,
    mode: str | None = None,
    env: dict[str, str] | None = None,
) -> DocumentStorageStatus:
    app_env = app_env or _clean(_setting_from(env, "APP_ENV", get_app_env())).lower() or "development"
    validation = validate_storage_config(env=env, mode=mode, app_env=app_env)
    mode = validation.mode
    if mode == "local":
        return DocumentStorageStatus(
            mode=mode,
            durable=False,
            local_path_allowed=True,
            configured=True,
            message="Generated documents are stored on the local filesystem.",
            blocking_issue=validation.blocking_issue,
        )
    if mode == "ephemeral":
        return DocumentStorageStatus(
            mode=mode,
            durable=False,
            local_path_allowed=False,
            configured=True,
            message="Generated documents are available for immediate download only and are not durable.",
            blocking_issue=validation.blocking_issue,
        )
    if mode == "object_storage_pending":
        return DocumentStorageStatus(
            mode=mode,
            durable=False,
            local_path_allowed=False,
            configured=False,
            message="Object storage is planned but not configured.",
            blocking_issue=validation.blocking_issue,
        )
    return DocumentStorageStatus(
        mode=mode,
        durable=validation.ready,
        local_path_allowed=False,
        configured=validation.ready,
        message="S3-compatible object storage is configured." if validation.ready else "S3-compatible object storage is missing required configuration.",
        blocking_issue=validation.blocking_issue,
    )


def generated_document_base_dir() -> Path:
    return GENERATED_DIR


def _normalise_storage_key(storage_key: str) -> str:
    return storage_key.replace("\\", "/").lstrip("/")


def _prefixed_key(storage_key: str, env: dict[str, str] | None = None) -> str:
    key = _normalise_storage_key(storage_key)
    prefix = _normalise_storage_key(_clean(_setting_from(env, "OBJECT_STORAGE_PREFIX", "")))
    return f"{prefix}/{key}" if prefix else key


class DocumentStorage:
    mode = "local"
    durable = False

    def save_generated_file(self, local_path: str | Path, storage_key: str) -> StoredDocument:
        raise NotImplementedError

    def get_download_reference(self, storage_key: str) -> str:
        raise NotImplementedError

    def supports_signed_downloads(self) -> bool:
        return False

    def generate_download_url(self, storage_key: str, expires_in_seconds: int = 900) -> str | None:
        return None


class LocalDocumentStorage(DocumentStorage):
    mode = "local"
    durable = False

    def save_generated_file(self, local_path: str | Path, storage_key: str) -> StoredDocument:
        path = str(Path(local_path))
        key = _normalise_storage_key(storage_key)
        return StoredDocument(path, key, self.mode, self.durable, path, uploaded=False)

    def get_download_reference(self, storage_key: str) -> str:
        return _normalise_storage_key(storage_key)


class EphemeralDocumentStorage(LocalDocumentStorage):
    mode = "ephemeral"


class ObjectStoragePending(DocumentStorage):
    mode = "object_storage_pending"

    def save_generated_file(self, local_path: str | Path, storage_key: str) -> StoredDocument:
        raise RuntimeError("Object storage is pending and cannot store generated documents.")

    def get_download_reference(self, storage_key: str) -> str:
        return _normalise_storage_key(storage_key)


class S3CompatibleDocumentStorage(DocumentStorage):
    mode = "object_storage"
    durable = True

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env
        validation = validate_storage_config(env=env, mode="object_storage")
        if not validation.ready:
            raise RuntimeError(f"Object storage configuration is incomplete: {', '.join(validation.missing_keys)}")
        self.provider = _clean(_setting_from(env, "OBJECT_STORAGE_PROVIDER", "s3"))
        self.bucket = _clean(_setting_from(env, "OBJECT_STORAGE_BUCKET", ""))
        self.region = _clean(_setting_from(env, "OBJECT_STORAGE_REGION", ""))
        self.endpoint_url = _clean(_setting_from(env, "OBJECT_STORAGE_ENDPOINT_URL", ""))
        self.access_key_id = _clean(_setting_from(env, "OBJECT_STORAGE_ACCESS_KEY_ID", ""))
        self.secret_access_key = _clean(_setting_from(env, "OBJECT_STORAGE_SECRET_ACCESS_KEY", ""))
        self.fake_upload = _bool_setting(env, "OBJECT_STORAGE_FAKE_UPLOAD", False) or _bool_setting(env, "OBJECT_STORAGE_DRY_RUN", False)

    def _reference_for(self, storage_key: str) -> str:
        return f"s3://{self.bucket}/{_prefixed_key(storage_key, self.env)}"

    def _client(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for object storage operations.") from exc
        return boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
        )

    def save_generated_file(self, local_path: str | Path, storage_key: str) -> StoredDocument:
        local_path = Path(local_path)
        key = _prefixed_key(storage_key, self.env)
        if not local_path.exists():
            raise FileNotFoundError(f"Generated file does not exist: {local_path}")
        if self.fake_upload:
            return StoredDocument(str(local_path), key, self.mode, self.durable, self._reference_for(storage_key), uploaded=False)

        client = self._client()
        extra_args: dict[str, str] = {}
        content_type, _ = mimetypes.guess_type(local_path.name)
        if content_type:
            extra_args["ContentType"] = content_type
        if extra_args:
            client.upload_file(str(local_path), self.bucket, key, ExtraArgs=extra_args)
        else:
            client.upload_file(str(local_path), self.bucket, key)
        return StoredDocument(str(local_path), key, self.mode, self.durable, self._reference_for(storage_key), uploaded=True)

    def get_download_reference(self, storage_key: str) -> str:
        return f"s3://{self.bucket}/{_normalise_storage_key(storage_key)}"

    def supports_signed_downloads(self) -> bool:
        return True

    def generate_download_url(self, storage_key: str, expires_in_seconds: int = 900) -> str | None:
        key = _normalise_storage_key(storage_key)
        if self.fake_upload:
            return f"https://download.example.invalid/{key}?expires_in={int(expires_in_seconds)}"
        client = self._client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expires_in_seconds),
        )


def get_document_storage(mode: str | None = None, env: dict[str, str] | None = None) -> DocumentStorage:
    mode = (mode or document_storage_mode(env)).strip().lower()
    if mode == "local":
        return LocalDocumentStorage()
    if mode == "ephemeral":
        return EphemeralDocumentStorage()
    if mode == "object_storage_pending":
        return ObjectStoragePending()
    if mode == "object_storage":
        return S3CompatibleDocumentStorage(env=env)
    return LocalDocumentStorage()


def save_generated_file(local_path: str | Path, storage_key: str) -> StoredDocument:
    return get_document_storage().save_generated_file(local_path, storage_key)


def get_download_reference(storage_key: str) -> str:
    return get_document_storage().get_download_reference(storage_key)


def supports_signed_downloads(env: dict[str, str] | None = None) -> bool:
    return get_document_storage(env=env).supports_signed_downloads()


def generate_download_url(storage_key: str, expires_in_seconds: int = 900, env: dict[str, str] | None = None) -> str | None:
    return get_document_storage(env=env).generate_download_url(storage_key, expires_in_seconds)


def storage_is_durable(env: dict[str, str] | None = None) -> bool:
    return validate_storage_config(env=env).durable


def storage_key_for_generated_file(local_path: str | Path, output_dir: str | Path | None = None) -> str:
    path = Path(local_path)
    if output_dir is not None:
        try:
            return _normalise_storage_key(str(path.relative_to(Path(output_dir))))
        except ValueError:
            pass
    try:
        return _normalise_storage_key(str(path.relative_to(generated_document_base_dir().parent)))
    except ValueError:
        return _normalise_storage_key(path.name)


def store_generated_document_set(
    paths: list[str | Path],
    output_dir: str | Path,
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    storage = get_document_storage()
    results: list[dict[str, Any]] = []
    for path in paths:
        key = storage_key_for_generated_file(path, output_dir)
        if prefix:
            key = f"{_normalise_storage_key(prefix)}/{key}"
        results.append(storage.save_generated_file(path, key).as_dict())
    return results


def storage_summary(env: dict[str, str] | None = None) -> dict[str, Any]:
    status = document_storage_status(env=env)
    validation = validate_storage_config(env=env, mode=status.mode)
    return {
        "mode": status.mode,
        "durable": status.durable,
        "configured": status.configured,
        "local_path_allowed": status.local_path_allowed,
        "message": status.message,
        "blocking_issue": status.blocking_issue,
        "missing_keys": validation.missing_keys,
        "secret_flags": validation.secret_flags,
    }
