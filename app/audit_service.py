from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, rows_to_dicts


SENSITIVE_DETAIL_KEYS = {"password", "password_hash", "password_salt", "bank", "account_number", "account holder"}


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _clean_details(details: dict[str, Any] | None) -> str | None:
    if not details:
        return None
    safe: dict[str, Any] = {}
    for key, value in details.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in SENSITIVE_DETAIL_KEYS):
            safe[key] = "[redacted]"
        else:
            safe[key] = value
    text = json.dumps(safe, sort_keys=True, default=str)
    for forbidden in ("Nust@2026", "password_hash", "password_salt"):
        text = text.replace(forbidden, "[redacted]")
    return text


def log_audit_event(
    action: str,
    user: dict | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    success: bool = True,
    ip_address: str | None = None,
) -> None:
    try:
        init_runtime_db()
        with get_runtime_connection() as conn:
            conn.execute(
                convert_placeholders(
                    """
                INSERT INTO audit_logs (
                    user_account_id, username, role, action, entity_type, entity_id,
                    details_json, ip_address, success, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                ),
                (
                    user.get("id") if user else None,
                    user.get("username") if user else None,
                    user.get("role") if user else None,
                    action,
                    entity_type,
                    str(entity_id) if entity_id is not None else None,
                    _clean_details(details),
                    ip_address,
                    1 if success else 0,
                    _now(),
                ),
            )
    except Exception:
        return


def list_audit_events(limit: int = 100, username: str | None = None, action: str | None = None, success: bool | None = None) -> pd.DataFrame:
    init_runtime_db()
    where: list[str] = []
    params: list[Any] = []
    if username:
        where.append(convert_placeholders("username = ?"))
        params.append(username)
    if action:
        where.append(convert_placeholders("action = ?"))
        params.append(action)
    if success is not None:
        where.append(convert_placeholders("success = ?"))
        params.append(1 if success else 0)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(int(limit))
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders(
                f"""
            SELECT id, username, role, action, entity_type, entity_id, details_json, success, created_at
            FROM audit_logs
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """
            ),
            tuple(params),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))
