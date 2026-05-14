from app.account_admin_service import (
    create_lecturer_account_for_lecturer,
    list_lecturers_without_accounts,
    reset_user_password,
)
from app.auth_service import authenticate_user, create_or_update_user_account, lecturer_id_for_staff_number, verify_password
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


def insert_lecturer_record(staff_number="200001", full_name="New Lecturer"):
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES (?, 'Dr', ?, 'MSc', 'ID', 'PAYE', 'Address',
                    '0810000000', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """,
            (staff_number, full_name),
        )
    return lecturer_id_for_staff_number(staff_number)


def test_list_lecturers_without_accounts_excludes_existing_accounts():
    dev_reset()
    missing_id = insert_lecturer_record("200001", "Missing Account Lecturer")
    existing_id = insert_lecturer_record("200002", "Existing Account Lecturer")
    create_or_update_user_account("200002", "OldPass2026", "lecturer", existing_id, must_change_password=False)

    missing = list_lecturers_without_accounts()

    assert "password_hash" not in missing.columns
    assert "password_salt" not in missing.columns
    staff_numbers = set(missing["staff_number"].astype(str))
    assert "200001" in staff_numbers
    assert "200002" not in staff_numbers
    row = missing[missing["staff_number"].astype(str) == "200001"].iloc[0]
    assert int(row["lecturer_id"]) == int(missing_id)
    assert int(row["account_exists"]) == 0


def test_admin_can_create_lecturer_account_for_missing_lecturer():
    dev_reset()
    lecturer_id = insert_lecturer_record("200003", "Created Account Lecturer")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = create_lecturer_account_for_lecturer(admin, lecturer_id, "TempPass2026", "TempPass2026")

    assert result["success"] is True
    assert result["stage"] == "complete"
    assert result["username"] == "200003"
    assert result["created_count"] == 1
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT username, role, lecturer_id, active, must_change_password, password_hash, password_salt
            FROM user_accounts
            WHERE username = ?
            """,
            ("200003",),
        ).fetchone()
    assert row["username"] == "200003"
    assert row["role"] == "lecturer"
    assert int(row["lecturer_id"]) == int(lecturer_id)
    assert int(row["active"]) == 1
    assert int(row["must_change_password"]) == 1
    assert row["password_hash"] != "TempPass2026"
    assert row["password_salt"] != "TempPass2026"
    assert verify_password("TempPass2026", row["password_hash"], row["password_salt"]) is True
    assert authenticate_user("200003", "TempPass2026")["must_change_password"] is True


def test_create_lecturer_account_blocks_duplicate_linked_account():
    dev_reset()
    lecturer_id = insert_lecturer_record("200004", "Duplicate Linked Lecturer")
    create_or_update_user_account("200004", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = create_lecturer_account_for_lecturer(admin, lecturer_id, "TempPass2026", "TempPass2026")

    assert result["success"] is False
    assert result["stage"] == "duplicate_check"
    assert "already has a login account" in result["safe_message"]


def test_create_lecturer_account_blocks_duplicate_username_for_other_account():
    dev_reset()
    lecturer_id = insert_lecturer_record("200005", "Duplicate Username Lecturer")
    create_or_update_user_account("200005", "AdminPass2026", "admin", None, must_change_password=False)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = create_lecturer_account_for_lecturer(admin, lecturer_id, "TempPass2026", "TempPass2026")

    assert result["success"] is False
    assert result["stage"] == "duplicate_check"
    assert "already used by another user account" in result["safe_message"]


def test_non_admin_cannot_create_lecturer_account():
    dev_reset()
    lecturer_id = insert_lecturer_record("200006", "Non Admin Blocked Lecturer")
    lecturer = {"id": 2, "username": "200006", "role": "lecturer"}

    result = create_lecturer_account_for_lecturer(lecturer, lecturer_id, "TempPass2026", "TempPass2026")

    assert result["success"] is False
    assert result["stage"] == "authorisation"


def test_create_lecturer_account_uses_provider_connection_and_commits_postgresql_style(monkeypatch):
    state = {
        "committed": False,
        "insert_params": None,
        "select_count": 0,
        "inserted_hash": None,
        "inserted_salt": None,
    }

    class FakeResult:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            sql_text = " ".join(str(sql).lower().split())
            if sql_text.startswith("select id, staff_number"):
                state["select_count"] += 1
                return FakeResult({"id": 42, "staff_number": "200007", "full_name": "Postgres Row", "active": 1})
            if "from user_accounts" in sql_text and "lecturer_id =" in sql_text:
                return FakeResult(None)
            if "from user_accounts" in sql_text and "username =" in sql_text and "password_hash" not in sql_text:
                return FakeResult(None)
            if sql_text.startswith("insert into user_accounts"):
                state["insert_params"] = params
                state["inserted_hash"] = params[1]
                state["inserted_salt"] = params[2]
                return FakeResult()
            if "select username, role, lecturer_id" in sql_text:
                return FakeResult(
                    {
                        "username": "200007",
                        "role": "lecturer",
                        "lecturer_id": 42,
                        "active": 1,
                        "must_change_password": 1,
                        "password_hash": state["inserted_hash"],
                        "password_salt": state["inserted_salt"],
                    }
                )
            raise AssertionError(f"Unexpected SQL: {sql}")

        def commit(self):
            state["committed"] = True

    monkeypatch.setattr("app.account_admin_service.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.account_admin_service.get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr("app.account_admin_service.convert_placeholders", lambda sql: sql.replace("?", "%s"))
    monkeypatch.setattr("app.account_admin_service.log_audit_event", lambda *args, **kwargs: None)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = create_lecturer_account_for_lecturer(admin, 42, "TempPass2026", "TempPass2026")

    assert result["success"] is True
    assert result["username"] == "200007"
    assert state["committed"] is True
    assert state["insert_params"][0] == "200007"
    assert state["insert_params"][3] == 42


def test_admin_can_reset_lecturer_password_and_force_change():
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "OldPass2026", "lecturer", lecturer_id, must_change_password=False)
    create_or_update_user_account("admin", "AdminPass2026", "admin", None, must_change_password=False)
    admin = authenticate_user("admin", "AdminPass2026")

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result["success"] is True
    assert result["stage"] == "complete"
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

    result = reset_user_password(lecturer, "100718", "TempPass2026", "TempPass2026")

    assert result["success"] is False
    assert result["stage"] == "authorisation"


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
    state = {"committed": False, "updated_params": None, "select_count": 0}

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
                state["select_count"] += 1
                if state["select_count"] == 1:
                    return FakeResult({"id": 7, "username": "100718", "role": "lecturer", "lecturer_id": 3})
                return FakeResult(
                    {
                        "username": "100718",
                        "role": "lecturer",
                        "lecturer_id": 3,
                        "must_change_password": 1,
                        "password_hash": state["updated_params"][0],
                        "password_salt": state["updated_params"][1],
                    }
                )
            state["updated_params"] = params
            return FakeResult()

        def commit(self):
            state["committed"] = True

    monkeypatch.setattr("app.account_admin_service.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.account_admin_service.get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr("app.account_admin_service.log_audit_event", lambda *args, **kwargs: None)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result["success"] is True
    assert result["username"] == "100718"
    assert result["must_change_password"] == 1
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

    assert result["success"] is True
    assert result["audit_warning"]
    assert result["must_change_password"] == 1
    assert authenticate_user("100718", "TempPass2026")["must_change_password"] is True


def test_reset_fails_safely_when_lecturer_account_missing():
    dev_reset()
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = reset_user_password(admin, "100718", "TempPass2026", "TempPass2026")

    assert result["success"] is False
    assert result["stage"] == "account_lookup"
    assert "not found" in result["safe_message"]
