from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from typing import Any

from app.audit_service import log_audit_event
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict


DEFAULT_LECTURER_PASSWORD = "Nust@2026"
PBKDF2_ITERATIONS = 260_000
PASSWORD_RULES = "Password must be at least 8 characters and must not equal the default password or username."


class AccessDeniedError(PermissionError):
    pass


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if not password:
        raise ValueError("Password must not be blank.")
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    expected_hash, _salt = hash_password(password, password_salt)
    return hmac.compare_digest(expected_hash, password_hash)


def get_user_by_username(username: str) -> dict | None:
    init_runtime_db()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders(
                """
            SELECT ua.*, l.staff_number, l.full_name AS lecturer_name
            FROM user_accounts AS ua
            LEFT JOIN lecturers AS l ON l.id = ua.lecturer_id
            WHERE ua.username = ?
            """
            ),
            (str(username).strip(),),
        ).fetchone()
    return row_to_dict(row)


def count_admin_accounts() -> int:
    init_runtime_db()
    with get_runtime_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM user_accounts WHERE role = 'admin' AND active = 1").fetchone()
    data = row_to_dict(row)
    return int(data["count"] if data else 0)


def authenticate_user(username: str, password: str) -> dict | None:
    user = get_user_by_username(username)
    if not user or not int(user["active"]):
        log_audit_event("login_failure", user={"username": str(username).strip(), "role": None}, success=False)
        return None
    if not verify_password(password, user["password_hash"], user["password_salt"]):
        log_audit_event("login_failure", user=public_user(user), success=False)
        return None
    mark_last_login(int(user["id"]))
    user = get_user_by_username(username)
    log_audit_event("login_success", user=public_user(user), success=True)
    return public_user(user)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(user["id"]),
        "username": str(user["username"]),
        "role": str(user["role"]),
        "lecturer_id": int(user["lecturer_id"]) if user.get("lecturer_id") is not None else None,
        "staff_number": user.get("staff_number"),
        "lecturer_name": user.get("lecturer_name"),
        "must_change_password": bool(user.get("must_change_password")),
        "active": bool(user.get("active")),
    }


def mark_last_login(user_id: int) -> None:
    init_runtime_db()
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders("UPDATE user_accounts SET last_login_at = ?, updated_at = ? WHERE id = ?"),
            (_now(), _now(), int(user_id)),
        )


def validate_new_password(username: str, new_password: str, confirm_password: str) -> list[str]:
    errors: list[str] = []
    if not new_password:
        errors.append("New password must not be blank.")
    if new_password != confirm_password:
        errors.append("Password confirmation does not match.")
    if len(new_password or "") < 8:
        errors.append("New password must be at least 8 characters.")
    if new_password == DEFAULT_LECTURER_PASSWORD:
        errors.append("New password must not equal the default password.")
    if new_password == str(username):
        errors.append("New password must not equal username or staff number.")
    return errors


def change_password(username: str, current_password: str, new_password: str, confirm_password: str) -> dict:
    user = get_user_by_username(username)
    if not user or not verify_password(current_password, user["password_hash"], user["password_salt"]):
        raise ValueError("Current password is incorrect.")
    errors = validate_new_password(username, new_password, confirm_password)
    if errors:
        raise ValueError("; ".join(errors))
    password_hash, password_salt = hash_password(new_password)
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders(
                """
            UPDATE user_accounts
            SET password_hash = ?, password_salt = ?, must_change_password = 0, updated_at = ?
            WHERE username = ?
            """,
            ),
            (password_hash, password_salt, _now(), username),
        )
    changed_user = public_user(get_user_by_username(username))
    log_audit_event("password_change", user=changed_user, entity_type="user_account", entity_id=changed_user["id"])
    return changed_user


def create_or_update_user_account(
    username: str,
    password: str,
    role: str,
    lecturer_id: int | None = None,
    must_change_password: bool = True,
    active: bool = True,
) -> str:
    if role not in {"admin", "lecturer"}:
        raise ValueError("Role must be admin or lecturer.")
    init_runtime_db()
    password_hash, password_salt = hash_password(password)
    now = _now()
    with get_runtime_connection() as conn:
        existing = conn.execute(convert_placeholders("SELECT id FROM user_accounts WHERE username = ?"), (username,)).fetchone()
        if existing:
            conn.execute(
                convert_placeholders(
                    """
                UPDATE user_accounts
                SET password_hash = ?, password_salt = ?, role = ?, lecturer_id = ?,
                    must_change_password = ?, active = ?, updated_at = ?
                WHERE username = ?
                """,
                ),
                (password_hash, password_salt, role, lecturer_id, int(must_change_password), int(active), now, username),
            )
            return "updated"
        conn.execute(
            convert_placeholders(
                """
            INSERT INTO user_accounts (
                username, password_hash, password_salt, role, lecturer_id,
                must_change_password, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ),
            (username, password_hash, password_salt, role, lecturer_id, int(must_change_password), int(active), now, now),
        )
        return "created"


def lecturer_id_for_staff_number(staff_number: str) -> int | None:
    init_runtime_db()
    with get_runtime_connection() as conn:
        row = conn.execute(convert_placeholders("SELECT id FROM lecturers WHERE staff_number = ?"), (str(staff_number),)).fetchone()
    data = row_to_dict(row)
    return int(data["id"]) if data else None


def lecturer_exists_by_id(lecturer_id: int) -> bool:
    init_runtime_db()
    with get_runtime_connection() as conn:
        row = conn.execute(convert_placeholders("SELECT id FROM lecturers WHERE id = ?"), (int(lecturer_id),)).fetchone()
    return row is not None


def authorize_lecturer_access(user: dict | None, lecturer_identifier: int | str) -> int:
    if not user:
        raise AccessDeniedError("Access denied. Login is required.")
    if str(lecturer_identifier).isdigit():
        numeric_identifier = int(lecturer_identifier)
        if lecturer_exists_by_id(numeric_identifier):
            requested_lecturer_id = numeric_identifier
        else:
            requested_lecturer_id = lecturer_id_for_staff_number(str(lecturer_identifier))
    else:
        requested_lecturer_id = lecturer_id_for_staff_number(str(lecturer_identifier))
    if requested_lecturer_id is None:
        raise AccessDeniedError("Access denied. Lecturer was not found.")
    if user.get("role") == "admin":
        return int(requested_lecturer_id)
    if user.get("role") == "lecturer" and int(user.get("lecturer_id") or 0) == int(requested_lecturer_id):
        return int(requested_lecturer_id)
    raise AccessDeniedError("Access denied. Lecturers can only access their own records.")


def lecturer_scoped_staff_number(user: dict) -> str:
    if user.get("role") != "lecturer" or not user.get("staff_number"):
        raise AccessDeniedError("Lecturer-scoped access requires a lecturer account.")
    return str(user["staff_number"])
