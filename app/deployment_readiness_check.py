from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.config import (
    DB_PATH,
    REAL_DB_PATH,
    database_provider,
    generated_file_mode,
    get_app_env,
    session_timeout_minutes,
)
from app.document_storage import OBJECT_STORAGE_CONFIG_KEYS, document_storage_status, validate_storage_config


VALID_STATUSES = {"PASS", "WARN", "BLOCK"}


def _env_bool(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _setting_text(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


def _secret_set(env: dict[str, str], name: str) -> bool:
    return bool(str(env.get(name, "") or "").strip())


def _is_true(name: str) -> bool:
    return _setting_text(name).lower() in {"1", "true", "yes", "on"}


def _path_looks_like_staging(path: Path) -> bool:
    return "staging" in [part.lower() for part in path.parts]


def _status_rank(status: str) -> int:
    return {"PASS": 0, "WARN": 1, "BLOCK": 2}[status]


def _check(status: str, message: str) -> dict[str, str]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid readiness status: {status}")
    return {"status": status, "message": message}


def evaluate_readiness(env: dict[str, str] | None = None) -> dict[str, Any]:
    if env is None:
        env = dict(os.environ)
    app_env = get_app_env()
    provider = database_provider()
    db_url_set = bool(env.get("DATABASE_URL", "").strip())
    pt_db_path_set = bool(env.get("PT_CLAIMS_DB_PATH", "").strip())
    file_mode = generated_file_mode()
    storage_mode = env.get("DOCUMENT_STORAGE_MODE") or file_mode
    storage_validation = validate_storage_config(env=env, mode=storage_mode, app_env=app_env)
    storage = document_storage_status(app_env=app_env, mode=storage_mode, env=env)
    db_perf_debug = str(env.get("DB_PERF_DEBUG", "")).strip()
    pool_min = str(env.get("DB_POOL_MIN_SIZE", "1")).strip()
    pool_max = str(env.get("DB_POOL_MAX_SIZE", "4")).strip()
    using_local_sqlite_default = provider == "sqlite" and not pt_db_path_set and DB_PATH.resolve() == REAL_DB_PATH.resolve()
    runtime_path = Path(env.get("PT_CLAIMS_DB_PATH", str(DB_PATH))).expanduser()

    checks: list[dict[str, str]] = []
    checks.append(_check("PASS", f"APP_ENV is {app_env}."))
    checks.append(_check("PASS", f"Database provider mode is {provider}. DATABASE_URL set: {'yes' if db_url_set else 'no'}." ))
    checks.append(_check("PASS", f"PT_CLAIMS_DB_PATH set: {'yes' if pt_db_path_set else 'no'}." ))
    checks.append(_check("PASS", f"GENERATED_FILE_MODE is {file_mode}."))
    checks.append(_check("PASS", f"DOCUMENT_STORAGE_MODE is {storage.mode}."))
    checks.append(_check("PASS", f"SESSION_TIMEOUT_MINUTES is {session_timeout_minutes()}."))

    production_secret_flags = {
        "database_url": db_url_set,
        "object_storage_provider": _secret_set(env, "OBJECT_STORAGE_PROVIDER"),
        "object_storage_bucket": _secret_set(env, "OBJECT_STORAGE_BUCKET"),
        "object_storage_region": _secret_set(env, "OBJECT_STORAGE_REGION"),
        "object_storage_endpoint_url": _secret_set(env, "OBJECT_STORAGE_ENDPOINT_URL"),
        "object_storage_access_key_id": _secret_set(env, "OBJECT_STORAGE_ACCESS_KEY_ID"),
        "object_storage_secret_access_key": _secret_set(env, "OBJECT_STORAGE_SECRET_ACCESS_KEY"),
        "session_timeout_minutes": _secret_set(env, "SESSION_TIMEOUT_MINUTES"),
    }

    if db_url_set and pt_db_path_set:
        checks.append(_check("WARN", "Both DATABASE_URL and PT_CLAIMS_DB_PATH are set. This can be confusing; PostgreSQL mode should not also set PT_CLAIMS_DB_PATH."))

    if app_env == "development":
        if using_local_sqlite_default:
            checks.append(_check("PASS", "Development with the local SQLite default is a normal local configuration."))
        elif provider == "sqlite":
            checks.append(_check("WARN", "Development is using a non-default SQLite path. Confirm this is intentional."))
        else:
            checks.append(_check("WARN", "Development is using PostgreSQL. This is allowed for testing but is not the normal local default."))

    if app_env == "staging":
        if provider == "postgresql" and db_url_set:
            checks.append(_check("PASS", "Staging PostgreSQL is configured. Use anonymised staging data only."))
        elif provider == "sqlite":
            if _path_looks_like_staging(runtime_path):
                checks.append(_check("PASS", "Staging SQLite path appears to be under a staging folder."))
            else:
                checks.append(_check("WARN", "Staging SQLite path does not appear to be under data/staging. Confirm it is anonymised."))
        else:
            checks.append(_check("WARN", "Staging database configuration is unusual. Confirm anonymised data only."))

    if app_env == "production":
        checks.append(_check("BLOCK", "Real-data online production remains blocked until production PostgreSQL migration, durable document storage, safe secrets, provider-level backups, and access-control review are complete."))
        if not db_url_set:
            checks.append(_check("BLOCK", "Production requires DATABASE_URL for managed PostgreSQL."))
        if provider == "sqlite":
            checks.append(_check("BLOCK", "Production with SQLite/local files is blocked."))
        if file_mode == "local" or storage.mode == "local":
            checks.append(_check("BLOCK", "Production with local generated file mode is blocked because durable object storage is required."))
        if storage.mode == "ephemeral":
            checks.append(_check("BLOCK", "Production with ephemeral generated file mode is blocked because durable object storage is required."))
        if storage.mode == "object_storage_pending":
            checks.append(_check("BLOCK", "Production with object_storage_pending is blocked because durable object storage is not configured."))
        if storage.mode == "object_storage" and not storage_validation.ready:
            checks.append(_check("BLOCK", "Production object storage is missing required configuration: " + ", ".join(storage_validation.missing_keys)))
        if storage.blocking_issue:
            checks.append(_check("BLOCK", storage.blocking_issue))
        if _is_true("DB_PERF_DEBUG"):
            checks.append(_check("BLOCK", "Production must not run with DB_PERF_DEBUG enabled."))
        if not production_secret_flags["session_timeout_minutes"]:
            checks.append(_check("WARN", "SESSION_TIMEOUT_MINUTES is not explicitly configured for production."))
        if provider == "postgresql":
            checks.append(_check("WARN", "PostgreSQL production runtime must still be validated end to end with real production infrastructure before real data migration."))

    if storage.mode == "object_storage_pending":
        checks.append(_check("WARN" if app_env != "production" else "BLOCK", "Document object storage is pending; generated files are not durably stored online."))
    if storage.mode == "object_storage" and storage_validation.ready:
        checks.append(_check("PASS", "S3-compatible document storage configuration is present. Values are not displayed."))

    warnings = [item["message"] for item in checks if item["status"] == "WARN"]
    blockers = [item["message"] for item in checks if item["status"] == "BLOCK"]
    final_status = max((item["status"] for item in checks), key=_status_rank) if checks else "PASS"

    return {
        "app_env": app_env,
        "database_provider": provider,
        "database_url_set": db_url_set,
        "pt_claims_db_path_set": pt_db_path_set,
        "using_local_sqlite_default": using_local_sqlite_default,
        "generated_file_mode": file_mode,
        "document_storage_mode": storage.mode,
        "document_storage_durable": storage.durable,
        "document_storage_configured": storage.configured,
        "document_storage_ready": storage_validation.ready,
        "document_storage_message": storage.message,
        "missing_storage_config_keys": storage_validation.missing_keys,
        "object_storage_secret_flags": {key.lower(): _secret_set(env, key) for key in OBJECT_STORAGE_CONFIG_KEYS},
        "production_secret_flags": production_secret_flags,
        "session_timeout_minutes": session_timeout_minutes(),
        "db_perf_debug": db_perf_debug or "false",
        "db_pool_min_size": pool_min,
        "db_pool_max_size": pool_max,
        "environment_shape": app_env,
        "local_controlled_use_status": "PASS" if app_env == "development" and using_local_sqlite_default else "WARN",
        "staging_demo_status": "PASS" if app_env == "staging" and (provider == "postgresql" or _path_looks_like_staging(runtime_path)) else "WARN",
        "real_data_production_status": "BLOCK" if app_env == "production" and blockers else "NOT_EVALUATED" if app_env != "production" else "PASS",
        "checks": checks,
        "warnings": warnings,
        "blocking_issues": blockers,
        "final_status": final_status,
    }


def render_text_report(result: dict[str, Any]) -> str:
    lines = [
        "Deployment Readiness Check",
        "==========================",
        f"APP_ENV: {result['app_env']}",
        f"Database provider: {result['database_provider']}",
        f"DATABASE_URL set: {'yes' if result['database_url_set'] else 'no'}",
        f"PT_CLAIMS_DB_PATH set: {'yes' if result['pt_claims_db_path_set'] else 'no'}",
        f"Using local SQLite default: {'yes' if result['using_local_sqlite_default'] else 'no'}",
        f"GENERATED_FILE_MODE: {result['generated_file_mode']}",
        f"DOCUMENT_STORAGE_MODE: {result['document_storage_mode']}",
        f"Document storage durable: {'yes' if result['document_storage_durable'] else 'no'}",
        f"Document storage configured: {'yes' if result['document_storage_configured'] else 'no'}",
        f"Document storage ready: {'yes' if result['document_storage_ready'] else 'no'}",
        f"Missing storage config keys: {', '.join(result['missing_storage_config_keys']) if result['missing_storage_config_keys'] else 'none'}",
        f"SESSION_TIMEOUT_MINUTES: {result['session_timeout_minutes']}",
        f"DB_PERF_DEBUG: {result['db_perf_debug']}",
        f"DB_POOL_MIN_SIZE: {result['db_pool_min_size']}",
        f"DB_POOL_MAX_SIZE: {result['db_pool_max_size']}",
        "",
        f"Local controlled use status: {result['local_controlled_use_status']}",
        f"Anonymised staging/demo status: {result['staging_demo_status']}",
        f"Real-data online production status: {result['real_data_production_status']}",
        "",
        "Checks:",
    ]
    for item in result["checks"]:
        lines.append(f"[{item['status']}] {item['message']}")
    lines.extend(["", f"Final readiness status: {result['final_status']}"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check deployment readiness without exposing secrets.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--fail-on-block", action="store_true", help="Exit non-zero if blocking issues are found.")
    args = parser.parse_args()

    result = evaluate_readiness()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text_report(result))
    if args.fail_on_block and result["final_status"] == "BLOCK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
