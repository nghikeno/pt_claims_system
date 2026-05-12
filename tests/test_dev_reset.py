import pytest

from app.config import DB_PATH
from app.database import get_connection
from app.dev_reset import REAL_RESET_PHRASE, dev_reset
from app.validators import assert_no_bank_fields


def test_dev_reset_creates_clash_and_no_clash_demo_lecturers():
    dev_reset()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT staff_number, full_name
            FROM lecturers
            WHERE staff_number IN ('100718', '200001')
            ORDER BY staff_number
            """
        ).fetchall()

    assert [(row["staff_number"], row["full_name"]) for row in rows] == [
        ("100718", "Lonia Nghitotelwa"),
        ("200001", "Demo Clean Lecturer"),
    ]


def test_dev_reset_database_has_no_bank_detail_columns():
    dev_reset()

    assert_no_bank_fields()


def test_dev_reset_refuses_simulated_real_database_with_lecturers(monkeypatch):
    dev_reset()
    monkeypatch.setattr("app.dev_reset.REAL_DB_PATH", DB_PATH)

    with pytest.raises(RuntimeError, match="Refusing to reset real data"):
        dev_reset()


def test_dev_reset_with_explicit_confirmation_backs_up_simulated_real_database(monkeypatch):
    dev_reset()
    monkeypatch.setattr("app.dev_reset.REAL_DB_PATH", DB_PATH)
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_dev_reset_*.db")) if backup_dir.exists() else set()

    dev_reset(confirm_real_reset=True, confirmation_phrase=REAL_RESET_PHRASE)

    after = set(backup_dir.glob("pt_claims_before_dev_reset_*.db"))
    assert after - before
