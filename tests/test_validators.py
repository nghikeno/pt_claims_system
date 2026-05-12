import pytest

from app.database import get_connection
from app.seed_data import seed_database
from app.validators import assert_no_bank_fields, get_table_columns


@pytest.fixture(autouse=True)
def seeded_database():
    seed_database()


def test_lecturer_sensitive_fields_exist_in_database_schema():
    columns = set(get_table_columns("lecturers"))

    assert "id_or_passport_number" in columns
    assert "paye_number" in columns
    assert "physical_address" in columns
    assert "contact_number" in columns


def test_bank_details_do_not_exist_in_database_schema():
    assert_no_bank_fields()

    with get_connection() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        for table in tables:
            columns = conn.execute(f"PRAGMA table_info({table['name']})").fetchall()
            column_names = {column["name"].lower() for column in columns}
            assert not any("bank" in name for name in column_names)
            assert not any("account" in name for name in column_names)
