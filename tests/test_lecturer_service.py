from app.database import get_connection, init_db
from app.dev_reset import dev_reset
from app.lecturer_service import backup_before_write_if_supported, update_lecturer


def insert_lecturer(staff_number="990101"):
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES (?, 'Ms', 'Test Lecturer', 'MSc', 'ID', 'PAYE', 'Address',
                    '0810000000', 410, 'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
            """,
            (staff_number,),
        )


def update_payload(**overrides):
    data = {
        "title": "Dr",
        "full_name": "Updated Test Lecturer",
        "highest_qualification": "PhD",
        "id_or_passport_number": "ID",
        "paye_number": "PAYE",
        "physical_address": "Address",
        "contact_number": "0810000000",
        "tariff_per_hour": 510,
        "campus": "Windhoek Main Campus",
        "contract_start_date": "2026-02-01",
        "contract_end_date": "2026-11-30",
        "active": 1,
    }
    data.update(overrides)
    return data


def test_sqlite_lecturer_update_creates_local_backup(monkeypatch):
    dev_reset()
    insert_lecturer("990101")
    backup_calls = []

    def fake_backup(prefix):
        backup_calls.append(prefix)
        return "data/backups/fake.db"

    monkeypatch.setattr("app.lecturer_service.backup_database", fake_backup)

    record = update_lecturer("990101", update_payload())

    assert backup_calls == ["pt_claims_before_lecturer_save"]
    assert record["_backup_result"]["performed"] is True
    assert record["_backup_result"]["mode"] == "sqlite"
    assert record["staff_number"] == "990101"
    assert record["full_name"] == "Updated Test Lecturer"


def test_postgresql_backup_helper_skips_local_sqlite_backup(monkeypatch):
    monkeypatch.setattr("app.lecturer_service.database_provider", lambda: "postgresql")

    def fail_backup(*args, **kwargs):
        raise AssertionError("local SQLite backup should not be called in PostgreSQL mode")

    monkeypatch.setattr("app.lecturer_service.backup_database", fail_backup)

    result = backup_before_write_if_supported()

    assert result["performed"] is False
    assert result["mode"] == "postgresql"
    assert "local SQLite backup skipped" in result["safe_message"]


def test_postgresql_style_lecturer_update_uses_runtime_provider_and_commits(monkeypatch):
    state = {"committed": False, "updated_params": None}

    class FakeCursor:
        rowcount = 1

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            state["updated_params"] = params
            return FakeCursor()

        def commit(self):
            state["committed"] = True

    def fail_backup(*args, **kwargs):
        raise AssertionError("local SQLite backup should not be called in PostgreSQL mode")

    monkeypatch.setattr("app.lecturer_service.database_provider", lambda: "postgresql")
    monkeypatch.setattr("app.lecturer_service.lecturer_exists", lambda staff_number: True)
    monkeypatch.setattr("app.lecturer_service.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.lecturer_service.get_runtime_connection", lambda: FakeConnection())
    monkeypatch.setattr("app.lecturer_service.backup_database", fail_backup)
    monkeypatch.setattr("app.lecturer_service.convert_placeholders", lambda sql: sql.replace("?", "%s"))
    monkeypatch.setattr("app.lecturer_service.log_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.lecturer_service.get_lecturer_by_staff_number",
        lambda staff_number: {"staff_number": staff_number, "full_name": "Updated Test Lecturer"},
    )

    record = update_lecturer("990101", update_payload())

    assert state["committed"] is True
    assert state["updated_params"][-1] == "990101"
    assert record["_backup_result"]["performed"] is False
    assert record["_backup_result"]["mode"] == "postgresql"
    assert record["staff_number"] == "990101"
