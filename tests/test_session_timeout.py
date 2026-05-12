from datetime import datetime, timedelta

from app_ui.session_security import clear_sensitive_session_state, session_expired


def test_active_session_remains_valid_before_timeout():
    now = datetime(2026, 5, 11, 12, 0)
    assert session_expired(now - timedelta(minutes=29), now, 30) is False


def test_session_expires_after_timeout():
    now = datetime(2026, 5, 11, 12, 0)
    assert session_expired(now - timedelta(minutes=31), now, 30) is True


def test_expired_session_clears_sensitive_state():
    state = {"auth_user": {"username": "100718"}, "last_activity_at": "x", "other": "kept", "last_sessions_export": "secret"}
    clear_sensitive_session_state(state)

    assert "auth_user" not in state
    assert "last_activity_at" not in state
    assert "last_sessions_export" not in state
    assert state["other"] == "kept"
