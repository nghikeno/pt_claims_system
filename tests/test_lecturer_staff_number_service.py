from app.auth_service import authenticate_user, create_or_update_user_account, lecturer_id_for_staff_number
from app.database import get_connection, init_db
from app.dev_reset import dev_reset
from app.lecturer_staff_number_service import CONFIRMATION_PHRASE, correct_lecturer_staff_number


def insert_lecturer(staff_number="990001", full_name="Lonia Nghitotelwa"):
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES (?, 'Ms', ?, 'MSc', 'ID', 'PAYE', 'Address',
                    '0810000000', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """,
            (staff_number, full_name),
        )


def account_row(username):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT username, role, lecturer_id, password_hash, password_salt, active,
                   must_change_password, created_at, updated_at, last_login_at
            FROM user_accounts
            WHERE username = ?
            """,
            (username,),
        ).fetchone()


def test_successful_staff_number_correction_updates_lecturer_and_login_username():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    create_or_update_user_account("990001", "SamePass2026", "lecturer", lecturer_id, must_change_password=False)
    before = account_row("990001")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "990001", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is True
    assert result["stage"] == "complete"
    assert result["account_username_updated"] is True
    assert lecturer_id_for_staff_number("990001") is None
    assert lecturer_id_for_staff_number("990002") == lecturer_id
    after = account_row("990002")
    assert after["username"] == "990002"
    assert after["role"] == "lecturer"
    assert int(after["lecturer_id"]) == int(lecturer_id)
    assert after["password_hash"] == before["password_hash"]
    assert after["password_salt"] == before["password_salt"]
    assert int(after["active"]) == int(before["active"])
    assert int(after["must_change_password"]) == int(before["must_change_password"])
    assert authenticate_user("990001", "SamePass2026") is None
    assert authenticate_user("990002", "SamePass2026") is not None


def test_duplicate_lecturer_staff_number_is_blocked():
    dev_reset()
    insert_lecturer("990001")
    insert_lecturer("990002", "Other Lecturer")
    lecturer_id = lecturer_id_for_staff_number("990001")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "990001", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is False
    assert result["stage"] == "duplicate_lecturer"
    assert lecturer_id_for_staff_number("990001") == lecturer_id


def test_duplicate_user_account_username_is_blocked():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    create_or_update_user_account("990001", "SamePass2026", "lecturer", lecturer_id, must_change_password=False)
    create_or_update_user_account("990002", "AdminPass2026", "admin", None, must_change_password=False)
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "990001", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is False
    assert result["stage"] == "duplicate_account"
    assert account_row("990001") is not None


def test_wrong_old_staff_number_is_blocked():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "999999", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is False
    assert result["stage"] == "validation"


def test_wrong_confirmation_phrase_is_blocked():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "990001", "990002", "yes")

    assert result["success"] is False
    assert result["stage"] == "confirmation"


def test_non_admin_cannot_correct_staff_number():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    lecturer_user = {"id": 2, "username": "990001", "role": "lecturer", "lecturer_id": lecturer_id}

    result = correct_lecturer_staff_number(lecturer_user, lecturer_id, "990001", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is False
    assert result["stage"] == "authorisation"


def test_missing_linked_lecturer_account_succeeds_with_warning():
    dev_reset()
    insert_lecturer("990001")
    lecturer_id = lecturer_id_for_staff_number("990001")
    admin = {"id": 1, "username": "admin", "role": "admin"}

    result = correct_lecturer_staff_number(admin, lecturer_id, "990001", "990002", CONFIRMATION_PHRASE)

    assert result["success"] is True
    assert result["account_username_updated"] is False
    assert result["warnings"]
    assert lecturer_id_for_staff_number("990002") == lecturer_id


def test_postgresql_style_provider_path_commits_and_preserves_account(monkeypatch):
    state = {"committed": False, "rolled_back": False, "lecturer_staff": "990001", "account_username": "990001"}

    class FakeCursor:
        rowcount = 1

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
            sql_text = " ".join(str(sql).split()).lower()
            if "from lecturers" in sql_text and "where id =" in sql_text and str(sql_text).startswith("select"):
                return FakeCursor({"id": 3, "staff_number": state["lecturer_staff"], "full_name": "Training Lecturer"})
            if "from lecturers" in sql_text and "id <>" in sql_text:
                return FakeCursor(None)
            if "from user_accounts" in sql_text and "username =" in sql_text and "id <>" in sql_text:
                return FakeCursor(None)
            if "from user_accounts" in sql_text and "lecturer_id =" in sql_text and "order by id" in sql_text:
                return FakeCursor(
                    {
                        "id": 8,
                        "username": state["account_username"],
                        "role": "lecturer",
                        "lecturer_id": 3,
                        "password_hash": "hash",
                        "password_salt": "salt",
                        "active": 1,
                        "must_change_password": 0,
                        "created_at": "created",
                        "updated_at": "updated",
                        "last_login_at": "last",
                    }
                )
            if str(sql_text).startswith("update lecturers"):
                state["lecturer_staff"] = params[0]
                return FakeCursor()
            if str(sql_text).startswith("update user_accounts"):
                state["account_username"] = params[0]
                return FakeCursor()
            if "select staff_number from lecturers" in sql_text:
                return FakeCursor({"staff_number": state["lecturer_staff"]})
            if "select username, role, lecturer_id" in sql_text:
                return FakeCursor(
                    {
                        "username": state["account_username"],
                        "role": "lecturer",
                        "lecturer_id": 3,
                        "password_hash": "hash",
                        "password_salt": "salt",
                        "active": 1,
                        "must_change_password": 0,
                        "created_at": "created",
                        "last_login_at": "last",
                    }
                )
            raise AssertionError(f"Unexpected SQL: {sql}")

        def commit(self):
            state["committed"] = True

        def rollback(self):
            state["rolled_back"] = True

    monkeypatch.setattr("app.lecturer_staff_number_service.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.lecturer_staff_number_service.get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr("app.lecturer_staff_number_service.log_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.lecturer_staff_number_service.convert_placeholders", lambda sql: sql.replace("?", "%s"))

    result = correct_lecturer_staff_number(
        {"id": 1, "username": "admin", "role": "admin"},
        3,
        "990001",
        "990002",
        CONFIRMATION_PHRASE,
    )

    assert result["success"] is True
    assert result["account_username_updated"] is True
    assert state["committed"] is True
    assert state["rolled_back"] is False
    assert state["lecturer_staff"] == "990002"
    assert state["account_username"] == "990002"
