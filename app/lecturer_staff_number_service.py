from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.audit_service import log_audit_event
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict


CONFIRMATION_PHRASE = "CORRECT STAFF NUMBER"
STAFF_NUMBER_PATTERN = re.compile(r"^\d+$")


def _result(success: bool, stage: str, safe_message: str, **extra: Any) -> dict[str, Any]:
    return {
        "success": success,
        "stage": stage,
        "safe_message": safe_message,
        "lecturer_id": extra.pop("lecturer_id", None),
        "old_staff_number": extra.pop("old_staff_number", None),
        "new_staff_number": extra.pop("new_staff_number", None),
        "account_username_updated": extra.pop("account_username_updated", False),
        "warnings": extra.pop("warnings", []),
        **extra,
    }


def _clean_staff_number(value: str | int | None) -> str:
    return str(value or "").strip().replace(" ", "")


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _rollback_safely(conn: Any) -> None:
    try:
        if hasattr(conn, "rollback"):
            conn.rollback()
    except Exception:
        return


def _commit_safely(conn: Any) -> None:
    if hasattr(conn, "commit"):
        conn.commit()


def _rowcount_ok(cursor: Any) -> bool:
    rowcount = getattr(cursor, "rowcount", None)
    return rowcount in (None, -1, 1)


def _log_diagnostic(stage: str, exc: Exception) -> None:
    print(f"STAFF_NUMBER_CORRECTION_DIAGNOSTIC stage={stage} exception={type(exc).__name__}")


def _find_lecturer(conn: Any, target_lecturer_identifier: str | int) -> dict | None:
    if isinstance(target_lecturer_identifier, int):
        row = conn.execute(
            convert_placeholders(
                """
                SELECT id, staff_number, full_name
                FROM lecturers
                WHERE id = ?
                """
            ),
            (int(target_lecturer_identifier),),
        ).fetchone()
    else:
        identifier = _clean_staff_number(target_lecturer_identifier)
        row = conn.execute(
            convert_placeholders(
                """
                SELECT id, staff_number, full_name
                FROM lecturers
                WHERE staff_number = ?
                """
            ),
            (identifier,),
        ).fetchone()
    return row_to_dict(row)


def correct_lecturer_staff_number(
    admin_user: dict | None,
    target_lecturer_identifier: str | int,
    old_staff_number: str,
    new_staff_number: str,
    confirmation_phrase: str,
) -> dict[str, Any]:
    """Correct a lecturer staff-number data-entry error and linked login username."""

    if not admin_user or admin_user.get("role") != "admin":
        return _result(False, "authorisation", "Only admins can correct lecturer staff numbers.")

    old_clean = _clean_staff_number(old_staff_number)
    new_clean = _clean_staff_number(new_staff_number)
    if str(confirmation_phrase or "").strip() != CONFIRMATION_PHRASE:
        return _result(False, "confirmation", f'Type "{CONFIRMATION_PHRASE}" to confirm this correction.')
    if not old_clean:
        return _result(False, "validation", "Current staff number is required.")
    if not new_clean:
        return _result(False, "validation", "New staff number is required.")
    if old_clean == new_clean:
        return _result(False, "validation", "New staff number must be different from the current staff number.")
    if not STAFF_NUMBER_PATTERN.fullmatch(new_clean):
        return _result(False, "validation", "New staff number must contain digits only.")

    try:
        init_runtime_db()
    except Exception as exc:
        _log_diagnostic("database_initialisation", exc)
        return _result(False, "database_initialisation", "Staff number correction failed during database initialisation.")

    account_username_updated = False
    warnings: list[str] = []
    lecturer_id: int | None = None
    try:
        with get_runtime_connection() as conn:
            lecturer = _find_lecturer(conn, target_lecturer_identifier)
            if lecturer is None:
                return _result(False, "lecturer_lookup", "Staff number correction failed: lecturer was not found.")
            lecturer_id = int(lecturer["id"])
            current_staff_number = _clean_staff_number(lecturer.get("staff_number"))
            if current_staff_number != old_clean:
                return _result(False, "validation", "Current staff number does not match the selected lecturer.")

            duplicate_lecturer = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id
                        FROM lecturers
                        WHERE staff_number = ? AND id <> ?
                        """
                    ),
                    (new_clean, lecturer_id),
                ).fetchone()
            )
            if duplicate_lecturer is not None:
                return _result(False, "duplicate_lecturer", "New staff number is already used by another lecturer.")

            linked_account = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, username, role, lecturer_id, password_hash, password_salt,
                               active, must_change_password, created_at, updated_at, last_login_at
                        FROM user_accounts
                        WHERE lecturer_id = ? AND role = 'lecturer'
                        ORDER BY id
                        LIMIT 1
                        """
                    ),
                    (lecturer_id,),
                ).fetchone()
            )
            linked_account_id = linked_account.get("id") if linked_account else None
            duplicate_account = row_to_dict(
                conn.execute(
                    convert_placeholders(
                        """
                        SELECT id, username
                        FROM user_accounts
                        WHERE username = ? AND (? IS NULL OR id <> ?)
                        """
                    ),
                    (new_clean, linked_account_id, linked_account_id),
                ).fetchone()
            )
            if duplicate_account is not None:
                return _result(False, "duplicate_account", "New staff number is already used as another user account username.")

            update_lecturer = conn.execute(
                convert_placeholders(
                    """
                    UPDATE lecturers
                    SET staff_number = ?
                    WHERE id = ? AND staff_number = ?
                    """
                ),
                (new_clean, lecturer_id, old_clean),
            )
            if not _rowcount_ok(update_lecturer):
                _rollback_safely(conn)
                return _result(False, "lecturer_update", "Staff number correction failed during lecturer update.")

            if linked_account is None:
                warnings.append("No linked lecturer login account was found, so no username was updated.")
            else:
                account_username = _clean_staff_number(linked_account.get("username"))
                if account_username != old_clean:
                    warnings.append("Linked lecturer account username did not match the old staff number, so it was not changed.")
                else:
                    update_account = conn.execute(
                        convert_placeholders(
                            """
                            UPDATE user_accounts
                            SET username = ?, updated_at = ?
                            WHERE id = ? AND role = 'lecturer' AND lecturer_id = ?
                            """
                        ),
                        (new_clean, _now(), int(linked_account["id"]), lecturer_id),
                    )
                    if not _rowcount_ok(update_account):
                        _rollback_safely(conn)
                        return _result(False, "account_update", "Staff number correction failed during account username update.")
                    account_username_updated = True

            _commit_safely(conn)

            verified_lecturer = row_to_dict(
                conn.execute(
                    convert_placeholders("SELECT staff_number FROM lecturers WHERE id = ?"),
                    (lecturer_id,),
                ).fetchone()
            )
            if not verified_lecturer or _clean_staff_number(verified_lecturer.get("staff_number")) != new_clean:
                return _result(False, "verification", "Staff number correction failed during lecturer verification.")
            if linked_account is not None and account_username_updated:
                verified_account = row_to_dict(
                    conn.execute(
                        convert_placeholders(
                            """
                            SELECT username, role, lecturer_id, password_hash, password_salt,
                                   active, must_change_password, created_at, last_login_at
                            FROM user_accounts
                            WHERE id = ?
                            """
                        ),
                        (int(linked_account["id"]),),
                    ).fetchone()
                )
                if not verified_account:
                    return _result(False, "verification", "Staff number correction failed during account verification.")
                preserved_fields = (
                    verified_account.get("role") == linked_account.get("role")
                    and int(verified_account.get("lecturer_id") or 0) == lecturer_id
                    and verified_account.get("password_hash") == linked_account.get("password_hash")
                    and verified_account.get("password_salt") == linked_account.get("password_salt")
                    and int(verified_account.get("active") or 0) == int(linked_account.get("active") or 0)
                    and int(verified_account.get("must_change_password") or 0)
                    == int(linked_account.get("must_change_password") or 0)
                    and verified_account.get("created_at") == linked_account.get("created_at")
                    and verified_account.get("last_login_at") == linked_account.get("last_login_at")
                )
                if _clean_staff_number(verified_account.get("username")) != new_clean or not preserved_fields:
                    return _result(False, "verification", "Staff number correction failed during account verification.")
    except Exception as exc:
        _log_diagnostic("correction", exc)
        return _result(False, "correction", "Staff number correction failed during database update.")

    audit_warning = None
    try:
        log_audit_event(
            "lecturer_staff_number_correction",
            user=admin_user,
            entity_type="lecturer",
            entity_id=lecturer_id,
            details={
                "old_staff_number": old_clean,
                "new_staff_number": new_clean,
                "account_username_updated": account_username_updated,
            },
            success=True,
        )
    except Exception as exc:
        _log_diagnostic("audit", exc)
        audit_warning = "Audit logging did not complete, but the staff number correction was saved."
        warnings.append(audit_warning)

    message = f"Staff number corrected from {old_clean} to {new_clean}."
    if account_username_updated:
        message += f" The lecturer must now use {new_clean} as the username."
    return _result(
        True,
        "complete",
        message,
        lecturer_id=lecturer_id,
        old_staff_number=old_clean,
        new_staff_number=new_clean,
        account_username_updated=account_username_updated,
        warnings=warnings,
        audit_warning=audit_warning,
    )
