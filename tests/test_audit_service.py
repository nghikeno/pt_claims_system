from app.audit_service import list_audit_events, log_audit_event
from app.auth_service import authenticate_user, create_or_update_user_account, lecturer_id_for_staff_number
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


def test_audit_log_inserts_event_without_plaintext_password():
    dev_reset()
    log_audit_event("test_event", user={"id": None, "username": "admin", "role": "admin"}, details={"password": "Secret123"})

    events = list_audit_events()

    assert events.iloc[0]["action"] == "test_event"
    assert "Secret123" not in str(events.iloc[0]["details_json"])


def test_login_success_and_failure_create_audit_events():
    dev_reset()
    insert_lecturer()
    lecturer_id = lecturer_id_for_staff_number("100718")
    create_or_update_user_account("100718", "Nust@2026", "lecturer", lecturer_id)

    assert authenticate_user("100718", "wrong") is None
    assert authenticate_user("100718", "Nust@2026") is not None
    actions = set(list_audit_events()["action"])

    assert "login_failure" in actions
    assert "login_success" in actions
