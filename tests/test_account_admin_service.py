import pytest

from app.account_admin_service import reset_user_password
from app.auth_service import authenticate_user, create_or_update_user_account, lecturer_id_for_staff_number
from app.audit_service import list_audit_events
from app.database import get_connection, init_db
from app.dev_reset import dev_reset


def insert_lecturer():
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES ('100718', 'Ms', 'Lonia Nghitotelwa', 'MSc', 'ID', 'PAYE', 'Address',
                    '0810000000', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """
        )


def test_admin_can_reset_lecturer_password_and_force_change():
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    create_or_update_user_account("admin", "AdminPass2026", "admin", None, must_change_password=False)
    admin = authenticate_user("admin", "AdminPass2026")

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result["must_change_password"] == 1
    assert authenticate_user("100718", "OldPass2026") is None
    lecturer = authenticate_user("100718", "TempPass2026")
    assert lecturer["must_change_password"] is True
    assert "admin_password_reset" in set(list_audit_events()["action"])


def test_lecturer_cannot_reset_password():
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    lecturer = authenticate_user("100718", "OldPass2026")

    with pytest.raises(PermissionError):
        reset_user_password(lecturer, "100718", "TempPass2026", "TempPass2026")


def test_reset_preserves_username_role_and_lecturer_id():
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, role, lecturer_id, must_change_password, password_hash FROM user_accounts WHERE username = ?",
            ("100718",),
        ).fetchone()
    assert row["username"] == "100718"
    assert row["role"] == "lecturer"
    assert int(row["lecturer_id"]) == int(lecturer_id)
    assert int(row["must_change_password"]) == 1
    assert row["password_hash"] != "TempPass2026"


def test_reset_uses_provider_connection_and_commits_postgresql_style(monkeypatch):
    state = {"committed": False, "updated_params": None}

    class FakeResult:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            if str(sql).strip().upper().startswith("SELECT"):
                return FakeResult({"id": 7, "username": "100718", "role": "lecturer", "lecturer_id": 3})
            state["updated_params"] = params
            return FakeResult()

        def commit(self):
            state["committed"] = True

    monkeypatch.setattr("app.account_admin_service.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.account_admin_service.get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr("app.account_admin_service.log_audit_event", lambda *args, **kwargs: None)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result == {"username": "100718", "must_change_password": 1}
    assert state["committed"] is True
    assert state["updated_params"][2]
    assert state["updated_params"][3] == "100718"


def test_reset_audit_failure_does_not_block(monkeypatch):
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    def broken_audit(*args, **kwargs):
        raise RuntimeError("audit backend unavailable")

    monkeypatch.setattr("app.account_admin_service.log_audit_event", broken_audit)

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result["must_change_password"] == 1
    assert authenticate_user("100718", "TempPass2026")["must_change_password"] is True
