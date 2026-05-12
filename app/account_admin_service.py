from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.audit_service import log_audit_event
from app.auth_service import hash_password, validate_new_password
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict, rows_to_dicts


def list_user_accounts() -> pd.DataFrame:
    init_runtime_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT ua.id, ua.username, ua.role, ua.lecturer_id, l.full_name AS lecturer_name,
                   ua.must_change_password, ua.active, ua.created_at, ua.updated_at, ua.last_login_at
            FROM user_accounts AS ua
            LEFT JOIN lecturers AS l ON l.id = ua.lecturer_id
            ORDER BY ua.role, ua.username
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def reset_user_password(admin_user: dict, username: str, temporary_password: str, confirm_password: str | None = None) -> dict:
    if not admin_user or admin_user.get("role") != "admin":
        raise PermissionError("Only admins can reset user passwords.")
    confirm = temporary_password if confirm_password is None else confirm_password
    errors = validate_new_password(username, temporary_password, confirm)
    if errors:
        raise ValueError("; ".join(errors))
    password_hash, password_salt = hash_password(temporary_password)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    init_runtime_db()
    with get_runtime_connection() as conn:
        target = row_to_dict(conn.execute(convert_placeholders("SELECT id, role FROM user_accounts WHERE username = ?"), (username,)).fetchone())
        if target is None:
            raise ValueError("User account not found.")
        conn.execute(
            convert_placeholders(
                """
            UPDATE user_accounts
            SET password_hash = ?, password_salt = ?, must_change_password = 1, updated_at = ?
            WHERE username = ?
            """,
            ),
            (password_hash, password_salt, now, username),
        )
    log_audit_event(
        "admin_password_reset",
        user=admin_user,
        entity_type="user_account",
        entity_id=username,
        details={"target_username": username},
        success=True,
    )
    return {"username": username, "must_change_password": 1}
