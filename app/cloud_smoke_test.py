from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import database_provider
from app.db_provider import normalize_postgres_url, psycopg_available
from app.document_storage import (
    OBJECT_STORAGE_CONFIG_KEYS,
    document_storage_mode,
    get_document_storage,
    validate_storage_config,
)


VALID_STATUSES = {"PASS", "WARN", "BLOCK"}
DUMMY_SMOKE_TEST_CONTENT = "PT Claims smoke test dummy file only. No real data.\n"


def _check(status: str, message: str, **extra: Any) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid smoke-test status: {status}")
    return {"status": status, "message": message, **extra}


def _rank(status: str) -> int:
    return {"PASS": 0, "WARN": 1, "BLOCK": 2}[status]


def _final_status(checks: list[dict[str, Any]]) -> str:
    return max((item["status"] for item in checks), key=_rank) if checks else "PASS"


def _secret_present(env: dict[str, str], name: str) -> bool:
    return bool(str(env.get(name, "") or "").strip())


def config_summary(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    storage_validation = validate_storage_config(env=env, mode=env.get("DOCUMENT_STORAGE_MODE") or document_storage_mode(env))
    flags = {
        "APP_ENV": _secret_present(env, "APP_ENV"),
        "DATABASE_URL": _secret_present(env, "DATABASE_URL"),
        "DOCUMENT_STORAGE_MODE": _secret_present(env, "DOCUMENT_STORAGE_MODE"),
        "SESSION_TIMEOUT_MINUTES": _secret_present(env, "SESSION_TIMEOUT_MINUTES"),
        **{key: _secret_present(env, key) for key in OBJECT_STORAGE_CONFIG_KEYS},
    }
    checks = [_check("PASS", "Configuration presence checked without printing secret values.", present_keys=flags)]
    if not flags["DATABASE_URL"]:
        checks.append(_check("WARN", "DATABASE_URL is not set. PostgreSQL live smoke test cannot run."))
    if storage_validation.mode == "object_storage" and not storage_validation.ready:
        checks.append(
            _check(
                "BLOCK",
                "Object storage mode is selected but required config is missing.",
                missing_keys=storage_validation.missing_keys,
            )
        )
    elif storage_validation.mode != "object_storage":
        checks.append(_check("WARN", f"DOCUMENT_STORAGE_MODE is {storage_validation.mode}; live object-storage upload smoke test will not run."))
    else:
        checks.append(_check("PASS", "Object storage config shape is complete.", missing_keys=[]))
    return {
        "name": "config",
        "status": _final_status(checks),
        "checks": checks,
        "database_url_set": flags["DATABASE_URL"],
        "document_storage_mode": storage_validation.mode,
        "missing_storage_config_keys": storage_validation.missing_keys,
    }


def postgres_smoke_test(env: dict[str, str] | None = None, required: bool = True) -> dict[str, Any]:
    env = env or dict(os.environ)
    url_set = _secret_present(env, "DATABASE_URL")
    if not url_set:
        status = "BLOCK" if required else "WARN"
        return {
            "name": "postgres",
            "status": status,
            "checks": [_check(status, "DATABASE_URL is not set. PostgreSQL smoke test skipped.")],
            "database_url_set": False,
        }
    if not str(env.get("DATABASE_URL", "")).startswith(("postgresql://", "postgresql+psycopg://")):
        return {
            "name": "postgres",
            "status": "BLOCK",
            "checks": [_check("BLOCK", "DATABASE_URL is set but does not look like a PostgreSQL URL.")],
            "database_url_set": True,
        }
    if not psycopg_available():
        return {
            "name": "postgres",
            "status": "BLOCK",
            "checks": [_check("BLOCK", "psycopg is not installed, so PostgreSQL smoke test cannot run.")],
            "database_url_set": True,
        }
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(normalize_postgres_url(env["DATABASE_URL"]), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version() AS version, current_database() AS database_name, current_user AS user_name")
                row = cur.fetchone() or {}
        return {
            "name": "postgres",
            "status": "PASS",
            "checks": [_check("PASS", "PostgreSQL read-only connection check passed.")],
            "database_url_set": True,
            "provider": database_provider(),
            "server_version": str(row.get("version", "")).split(" on ")[0],
            "current_database_checked": bool(row.get("database_name")),
            "current_user_checked": bool(row.get("user_name")),
        }
    except Exception as exc:
        return {
            "name": "postgres",
            "status": "BLOCK",
            "checks": [_check("BLOCK", f"PostgreSQL read-only connection check failed: {type(exc).__name__}")],
            "database_url_set": True,
        }


def storage_dry_run(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    validation = validate_storage_config(env=env, mode=env.get("DOCUMENT_STORAGE_MODE") or document_storage_mode(env))
    checks: list[dict[str, Any]] = []
    if validation.mode != "object_storage":
        checks.append(_check("WARN", f"Storage mode is {validation.mode}; no object storage upload will run."))
    elif validation.ready:
        checks.append(_check("PASS", "Object storage config shape is valid. No upload was performed."))
    else:
        checks.append(_check("BLOCK", "Object storage config is incomplete.", missing_keys=validation.missing_keys))
    return {
        "name": "storage_dry_run",
        "status": _final_status(checks),
        "checks": checks,
        "document_storage_mode": validation.mode,
        "missing_storage_config_keys": validation.missing_keys,
        "uploaded": False,
    }


def storage_upload_dummy(env: dict[str, str] | None = None, yes: bool = False) -> dict[str, Any]:
    env = env or dict(os.environ)
    validation = validate_storage_config(env=env, mode=env.get("DOCUMENT_STORAGE_MODE") or document_storage_mode(env))
    if not yes:
        return {
            "name": "storage_upload_dummy",
            "status": "BLOCK",
            "checks": [_check("BLOCK", "Dummy upload requires --yes.")],
            "uploaded": False,
        }
    if validation.mode != "object_storage":
        return {
            "name": "storage_upload_dummy",
            "status": "BLOCK",
            "checks": [_check("BLOCK", "Dummy upload requires DOCUMENT_STORAGE_MODE=object_storage.")],
            "uploaded": False,
        }
    if not validation.ready:
        return {
            "name": "storage_upload_dummy",
            "status": "BLOCK",
            "checks": [_check("BLOCK", "Object storage config is incomplete.", missing_keys=validation.missing_keys)],
            "uploaded": False,
        }
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    storage_key = f"smoke-tests/pt-claims-smoke-test-{timestamp}.txt"
    try:
        with tempfile.TemporaryDirectory(prefix="pt_claims_smoke_") as temp_dir:
            local_path = Path(temp_dir) / "pt-claims-smoke-test.txt"
            local_path.write_text(DUMMY_SMOKE_TEST_CONTENT, encoding="utf-8")
            stored = get_document_storage(env=env).save_generated_file(local_path, storage_key)
        return {
            "name": "storage_upload_dummy",
            "status": "PASS",
            "checks": [_check("PASS", "Dummy object-storage upload completed.")],
            "document_storage_mode": validation.mode,
            "object_key": stored.storage_key,
            "uploaded": stored.uploaded,
            "dummy_content_only": True,
        }
    except Exception as exc:
        return {
            "name": "storage_upload_dummy",
            "status": "BLOCK",
            "checks": [_check("BLOCK", f"Dummy object-storage upload failed: {type(exc).__name__}")],
            "uploaded": False,
        }


def all_dry_run(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    results = [config_summary(env), postgres_smoke_test(env, required=False), storage_dry_run(env)]
    return {
        "name": "all_dry_run",
        "status": _final_status(results),
        "results": results,
    }


def _collect_checks(result: dict[str, Any]) -> list[dict[str, Any]]:
    if "checks" in result:
        return list(result["checks"])
    checks: list[dict[str, Any]] = []
    for child in result.get("results", []):
        checks.extend(_collect_checks(child))
    return checks


def render_text_report(result: dict[str, Any]) -> str:
    lines = [
        "Cloud Infrastructure Smoke Test",
        "===============================",
        f"Command: {result['name']}",
        f"Final status: {result['status']}",
        "",
        "Checks:",
    ]
    for check in _collect_checks(result):
        lines.append(f"[{check['status']}] {check['message']}")
        if check.get("missing_keys"):
            lines.append(f"Missing keys: {', '.join(check['missing_keys'])}")
    if result.get("database_url_set") is not None:
        lines.append(f"DATABASE_URL set: {'yes' if result['database_url_set'] else 'no'}")
    if result.get("document_storage_mode"):
        lines.append(f"DOCUMENT_STORAGE_MODE: {result['document_storage_mode']}")
    if result.get("object_key"):
        lines.append(f"Object key: {result['object_key']}")
    if result.get("uploaded") is not None:
        lines.append(f"Uploaded: {'yes' if result['uploaded'] else 'no'}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe cloud infrastructure smoke tests without exposing secrets.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--config-only", action="store_true")
    actions.add_argument("--postgres", action="store_true")
    actions.add_argument("--storage-dry-run", action="store_true")
    actions.add_argument("--storage-upload-dummy", action="store_true")
    actions.add_argument("--all-dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Required before uploading the dummy smoke-test file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON without secret values.")
    args = parser.parse_args()

    if args.config_only:
        result = config_summary()
    elif args.postgres:
        result = postgres_smoke_test(required=True)
    elif args.storage_dry_run:
        result = storage_dry_run()
    elif args.storage_upload_dummy:
        result = storage_upload_dummy(yes=args.yes)
    else:
        result = all_dry_run()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text_report(result))
    if args.postgres and result["status"] == "BLOCK":
        raise SystemExit(1)
    if args.storage_upload_dummy and result["status"] == "BLOCK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
