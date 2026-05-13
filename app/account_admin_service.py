from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.audit_service import log_audit_event
from app.auth_service import hash_password, validate_new_password, verify_password
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict, rows_to_dicts


def _reset_result(success: bool, stage: str, safe_message: str, **extra) -> dict:
    return {"success": success, "stage": stage, "safe_message": safe_message, **extra}


def _log_reset_diagnostic(stage: str, exc: Exception) -> None:
    print(f"PASSWORD_RESET_DIAGNOSTIC stage={stage} exception={type(exc).__name__}")


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
        return _reset_result(False, "authorisation", "Only admins can reset lecturer passwords.")
    target_username = str(username).strip()
    confirm = temporary_password if confirm_password is None else confirm_password
    errors = validate_new_password(target_username, temporary_password, confirm)
    if errors:
        return _reset_result(False, "validation", "; ".join(errors))
    password_hash, password_salt = hash_password(temporary_password)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    try:
        init_runtime_db()
    except Exception as exc:
        _log_reset_diagnostic("database_initialisation", exc)
        return _reset_result(False, "database_initialisation", "Password reset failed during database initialisation.")
    try:
        with get_runtime_connection() as conn:
            target = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, username, role, lecturer_id
                        FROM user_accounts
                        WHERE username = ?
                        """
                    ),
                    (target_username,),
                ).fetchone()
            )
            if target is None:
                return _reset_result(False, "account_lookup", "Password reset failed: lecturer account was not found.")
            if str(target.get("role")) != "lecturer":
                return _reset_result(False, "account_lookup", "Password reset failed: selected account is not a lecturer account.")
            update_cursor = conn.execute(
                convert_placeholders(
                    """
                    UPDATE user_accounts
                    SET password_hash = ?, password_salt = ?, must_change_password = 1, updated_at = ?
                    WHERE username = ? AND role = 'lecturer'
                    """
                ),
                (password_hash, password_salt, now, target_username),
            )
            rowcount = getattr(update_cursor, "rowcount", None)
            if rowcount not in (None, -1, 1):
                return _reset_result(False, "account_update", "Password reset failed during account update.")
            if hasattr(conn, "commit"):
                conn.commit()
            verified = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT username, role, lecturer_id, must_change_password, password_hash, password_salt
                        FROM user_accounts
                        WHERE username = ?
                        """
                    ),
                    (target_username,),
                ).fetchone()
            )
            if not verified:
                return _reset_result(False, "verification", "Password reset failed during verification.")
            if (
                str(verified.get("username")) != target_username
                or str(verified.get("role")) != "lecturer"
                or verified.get("lecturer_id") != target.get("lecturer_id")
                or int(verified.get("must_change_password") or 0) != 1
                or not verify_password(temporary_password, verified["password_hash"], verified["password_salt"])
            ):
                return _reset_result(False, "verification", "Password reset failed during verification.")
    except Exception as exc:
        _log_reset_diagnostic("account_update", exc)
        return _reset_result(False, "account_update", "Password reset failed during account update.")
    audit_warning = None
    try:
        log_audit_event(
            "admin_password_reset",
            user=admin_user,
            entity_type="user_account",
            entity_id=target_username,
            details={"target_username": target_username},
            success=True,
        )
    except Exception as exc:
        _log_reset_diagnostic("audit", exc)
        audit_warning = "Audit logging did not complete, but the password reset was saved."
    return _reset_result(
        True,
        "complete",
        f"Password reset for {target_username}. Must change password at next login.",
        username=target_username,
        must_change_password=1,
        audit_warning=audit_warning,
    )
