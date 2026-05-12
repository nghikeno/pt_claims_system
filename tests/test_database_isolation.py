from app.config import DB_PATH, REAL_DB_PATH


def test_pytest_uses_temporary_database_path():
    assert DB_PATH != REAL_DB_PATH
    assert DB_PATH.name == "pt_claims_test.db"
    assert "pt_claims_pytest_" in str(DB_PATH)
