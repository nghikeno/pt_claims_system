from __future__ import annotations

from datetime import datetime, timedelta


AUTH_KEYS = {
    "auth_user",
    "view_as_admin_user",
    "view_as_lecturer_user",
    "last_activity_at",
    "lecturer_navigation",
    "force_my_dashboard_after_password_change",
    "post_password_change_notice",
}


def session_expired(last_activity_at: datetime | None, now: datetime, timeout_minutes: int) -> bool:
    if last_activity_at is None:
        return False
    return now - last_activity_at > timedelta(minutes=timeout_minutes)


def clear_sensitive_session_state(session_state: dict) -> None:
    for key in list(session_state.keys()):
        if key in AUTH_KEYS or key.startswith("last_") or "export" in key or "password" in key:
            session_state.pop(key, None)


def can_start_view_as(user: dict | None) -> bool:
    return bool(user and user.get("role") == "admin")


def enter_view_as_lecturer(session_state: dict, admin_user: dict, lecturer_user: dict) -> None:
    if not can_start_view_as(admin_user):
        raise PermissionError("Only admins can start lecturer view.")
    if lecturer_user.get("role") != "lecturer":
        raise PermissionError("View-as target must be a lecturer.")
    session_state["view_as_admin_user"] = dict(admin_user)
    session_state["view_as_lecturer_user"] = dict(lecturer_user)
    session_state["lecturer_navigation"] = "My Dashboard"


def exit_view_as_lecturer(session_state: dict) -> None:
    session_state.pop("view_as_lecturer_user", None)
    session_state.pop("view_as_admin_user", None)
    session_state.pop("lecturer_navigation", None)


def effective_user(session_state: dict) -> dict | None:
    return session_state.get("view_as_lecturer_user") or session_state.get("auth_user")
