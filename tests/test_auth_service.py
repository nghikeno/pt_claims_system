import pytest

from app.auth_service import (
    AccessDeniedError,
    authenticate_user,
    authorize_lecturer_access,
    change_password,
    create_or_update_user_account,
    get_user_by_username,
    hash_password,
    lecturer_id_for_staff_number,
    verify_password,
)
from app.database import get_connection, init_db
from app.dev_reset import dev_reset


def insert_lecturer(staff_number="100718", full_name="Lonia Nghitotelwa"):
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES (?, 'Ms', ?, 'MSc', 'ID', 'PAYE', 'Address', '0810000000', 410,
                    'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """,
            (staff_number, full_name),
        )
    return lecturer_id_for_staff_number(staff_number)


def test_password_hashing_does_not_store_plaintext_and_verifies():
    password_hash, salt = hash_password("StrongPass1")

    assert password_hash != "StrongPass1"
    assert verify_password("StrongPass1", password_hash, salt) is True
    assert verify_password("WrongPass1", password_hash, salt) is False


def test_authenticate_user_and_password_change_clears_must_change():
    dev_reset()
    lecturer_id = insert_lecturer()
    create_or_update_user_account("100718", "Nust@2026", "lecturer", lecturer_id, must_change_password=True)

    user = authenticate_user("100718", "Nust@2026")

    assert user["must_change_password"] is True
    changed = change_password("100718", "Nust@2026", "BetterPass2026", "BetterPass2026")
    assert changed["must_change_password"] is False
    assert authenticate_user("100718", "BetterPass2026") is not None
    assert authenticate_user("100718", "BetterPass2026")["lecturer_id"] == lecturer_id


def test_password_change_rejects_default_or_username_password():
    dev_reset()
    lecturer_id = insert_lecturer()
    create_or_update_user_account("100718", "Nust@2026", "lecturer", lecturer_id, must_change_password=True)

    with pytest.raises(ValueError, match="default password"):
        change_password("100718", "Nust@2026", "Nust@2026", "Nust@2026")
    with pytest.raises(ValueError, match="username"):
        change_password("100718", "Nust@2026", "100718", "100718")


def test_lecturer_role_cannot_access_another_lecturer_context():
    dev_reset()
    lonia_id = insert_lecturer("100718", "Lonia Nghitotelwa")
    mervin_id = insert_lecturer("1001259", "Mervin Mokhatu")
    create_or_update_user_account("100718", "Nust@2026", "lecturer", lonia_id, must_change_password=True)
    user = authenticate_user("100718", "Nust@2026")

    assert authorize_lecturer_access(user, lonia_id) == lonia_id
    with pytest.raises(AccessDeniedError):
        authorize_lecturer_access(user, mervin_id)


def test_admin_role_can_access_any_lecturer_context():
    dev_reset()
    lecturer_id = insert_lecturer("100718", "Lonia Nghitotelwa")
    create_or_update_user_account("admin", "AdminPass2026", "admin", None, must_change_password=False)
    admin = authenticate_user("admin", "AdminPass2026")

    assert authorize_lecturer_access(admin, lecturer_id) == lecturer_id
    assert get_user_by_username("admin")["password_hash"] != "AdminPass2026"


def test_authenticate_user_with_mock_postgresql_provider(monkeypatch):
    from app import auth_service

    password_hash, salt = hash_password("Staging@2026")
    state = {
        "last_login_updated": False,
        "queries": [],
        "user": {
            "id": 1,
            "username": "900001",
            "password_hash": password_hash,
            "password_salt": salt,
            "role": "lecturer",
            "lecturer_id": 1,
            "must_change_password": 1,
            "active": 1,
            "staff_number": "900001",
            "lecturer_name": "Demo Lecturer One",
        },
    }

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            state["queries"].append(sql)
            if "SELECT ua.*" in sql:
                return self
            if "UPDATE user_accounts SET last_login_at" in sql:
                state["last_login_updated"] = True
                return self
            raise AssertionError(f"Unexpected SQL: {sql}")

        def fetchone(self):
            return state["user"]

    monkeypatch.setattr(auth_service, "init_runtime_db", lambda: None)
    monkeypatch.setattr(auth_service, "get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr(auth_service, "convert_placeholders", lambda sql: sql.replace("?", "%s"))
    monkeypatch.setattr(auth_service, "log_audit_event", lambda *args, **kwargs: None)

    user = authenticate_user("900001", "Staging@2026")

    assert user["username"] == "900001"
    assert user["must_change_password"] is True
    assert state["last_login_updated"] is True
    assert any("%s" in query for query in state["queries"])
