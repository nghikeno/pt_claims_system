from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.audit_service import log_audit_event
from app.auth_service import hash_password, validate_new_password, verify_password
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict, rows_to_dicts


def _reset_result(success: bool, stage: str, safe_message: str, **extra) -> dict:
    return {"success": success, "stage": stage, "safe_message": safe_message, **extra}


def _account_result(success: bool, stage: str, safe_message: str, **extra) -> dict:
    return {
        "success": success,
        "stage": stage,
        "safe_message": safe_message,
        "created_count": extra.pop("created_count", 0),
        "skipped_count": extra.pop("skipped_count", 0),
        "warnings": extra.pop("warnings", []),
        **extra,
    }


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


def list_lecturers_without_accounts() -> pd.DataFrame:
    init_runtime_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.id AS lecturer_id, l.staff_number, l.full_name, l.active,
                   CASE WHEN ua.id IS NULL THEN 0 ELSE 1 END AS account_exists
            FROM lecturers AS l
            LEFT JOIN user_accounts AS ua
              ON ua.lecturer_id = l.id AND ua.role = 'lecturer'
            WHERE ua.id IS NULL
            ORDER BY l.active DESC, l.staff_number
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def create_lecturer_account_for_lecturer(
    admin_user: dict,
    lecturer_id: int | str,
    temporary_password: str,
    confirm_password: str | None = None,
) -> dict:
    if not admin_user or admin_user.get("role") != "admin":
        return _account_result(False, "authorisation", "Only admins can create lecturer accounts.", skipped_count=1)

    confirm = temporary_password if confirm_password is None else confirm_password
    try:
        target_lecturer_id = int(lecturer_id)
    except (TypeError, ValueError):
        return _account_result(False, "validation", "Select a valid lecturer before creating an account.", skipped_count=1)

    now = datetime.now().isoformat(sep=" ", timespec="seconds")

    try:
        init_runtime_db()
    except Exception as exc:
        _log_reset_diagnostic("database_initialisation", exc)
        return _account_result(
            False,
            "database_initialisation",
            "Lecturer account creation failed during database initialisation.",
            skipped_count=1,
        )

    try:
        with get_runtime_connection() as conn:
            lecturer = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, staff_number, full_name, active
                        FROM lecturers
                        WHERE id = ?
                        """
                    ),
                    (target_lecturer_id,),
                ).fetchone()
            )
            if not lecturer:
                return _account_result(False, "lecturer_lookup", "Selected lecturer was not found.", skipped_count=1)

            username = str(lecturer.get("staff_number") or "").strip()
            if not username:
                return _account_result(False, "validation", "Selected lecturer does not have a staff number.", skipped_count=1)

            errors = validate_new_password(username, temporary_password, confirm)
            if errors:
                return _account_result(False, "validation", "; ".join(errors), username=username, lecturer_id=target_lecturer_id, skipped_count=1)

            linked_account = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, username
                        FROM user_accounts
                        WHERE lecturer_id = ? AND role = 'lecturer'
                        ORDER BY id
                        LIMIT 1
                        """
                    ),
                    (target_lecturer_id,),
                ).fetchone()
            )
            if linked_account:
                return _account_result(
                    False,
                    "duplicate_check",
                    "This lecturer already has a login account.",
                    username=str(linked_account.get("username") or username),
                    lecturer_id=target_lecturer_id,
                    skipped_count=1,
                )

            username_account = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, username, lecturer_id, role
                        FROM user_accounts
                        WHERE username = ?
                        """
                    ),
                    (username,),
                ).fetchone()
            )
            if username_account:
                return _account_result(
                    False,
                    "duplicate_check",
                    "This staff number is already used by another user account.",
                    username=username,
                    lecturer_id=target_lecturer_id,
                    skipped_count=1,
                )

            password_hash, password_salt = hash_password(temporary_password)
            conn.execute(
                convert_placeholders(
                    """
                    INSERT INTO user_accounts (
                        username, password_hash, password_salt, role, lecturer_id,
                        must_change_password, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'lecturer', ?, 1, 1, ?, ?)
                    """
                ),
                (username, password_hash, password_salt, target_lecturer_id, now, now),
            )
            if hasattr(conn, "commit"):
                conn.commit()

            created = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT username, role, lecturer_id, active, must_change_password,
                               password_hash, password_salt
                        FROM user_accounts
                        WHERE username = ?
                        """
                    ),
                    (username,),
                ).fetchone()
            )
            if (
                not created
                or str(created.get("username")) != username
                or str(created.get("role")) != "lecturer"
                or int(created.get("lecturer_id") or 0) != target_lecturer_id
                or int(created.get("active") or 0) != 1
                or int(created.get("must_change_password") or 0) != 1
                or not verify_password(temporary_password, created["password_hash"], created["password_salt"])
            ):
                return _account_result(
                    False,
                    "verification",
                    "Lecturer account creation failed during verification.",
                    username=username,
                    lecturer_id=target_lecturer_id,
                    skipped_count=1,
                )
    except Exception as exc:
        _log_reset_diagnostic("account_creation", exc)
        return _account_result(
            False,
            "account_creation",
            "Lecturer account creation failed during account update.",
            skipped_count=1,
        )

    warnings: list[str] = []
    try:
        log_audit_event(
            "lecturer_account_created",
            user=admin_user,
            entity_type="user_account",
            entity_id=username,
            details={"target_username": username, "lecturer_id": target_lecturer_id},
            success=True,
        )
    except Exception as exc:
        _log_reset_diagnostic("audit", exc)
        warnings.append("Audit logging did not complete, but the lecturer account was created.")

    return _account_result(
        True,
        "complete",
        f"Lecturer account created. Username: {username}. The lecturer must change the temporary password at next login.",
        username=username,
        lecturer_id=target_lecturer_id,
        created_count=1,
        skipped_count=0,
        warnings=warnings,
    )


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
