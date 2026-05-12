from app.auth_bootstrap_lecturers import LECTURER_ACCOUNTS, bootstrap_lecturer_accounts
from app.auth_service import get_user_by_username, verify_password
from app.database import get_connection, init_db
from app.dev_reset import dev_reset


def insert_bootstrap_lecturers():
    init_db()
    with get_connection() as conn:
        for staff_number, full_name in LECTURER_ACCOUNTS.items():
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


def test_bootstrap_dry_run_does_not_write_accounts():
    dev_reset()
    insert_bootstrap_lecturers()

    summary = bootstrap_lecturer_accounts(write=False)

    assert sorted(summary["would_process"]) == sorted(LECTURER_ACCOUNTS)
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0] == 0


def test_bootstrap_creates_lecturer_accounts_linked_to_lecturers():
    dev_reset()
    insert_bootstrap_lecturers()

    summary = bootstrap_lecturer_accounts(write=True)

    assert sorted(summary["created"]) == sorted(LECTURER_ACCOUNTS)
    for staff_number in LECTURER_ACCOUNTS:
        user = get_user_by_username(staff_number)
        assert user["username"] == staff_number
        assert user["role"] == "lecturer"
        assert user["lecturer_id"] is not None
        assert user["active"] == 1
        assert user["must_change_password"] == 1
        assert user["password_hash"] != "Nust@2026"
        assert verify_password("Nust@2026", user["password_hash"], user["password_salt"]) is True


def test_bootstrap_is_idempotent():
    dev_reset()
    insert_bootstrap_lecturers()
    bootstrap_lecturer_accounts(write=True)

    summary = bootstrap_lecturer_accounts(write=True)

    assert sorted(summary["updated"]) == sorted(LECTURER_ACCOUNTS)
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_accounts WHERE role = 'lecturer'").fetchone()[0] == 4
