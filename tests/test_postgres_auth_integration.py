import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("PT_CLAIMS_TEST_DATABASE_URL"),
    reason="PT_CLAIMS_TEST_DATABASE_URL is not set; disposable PostgreSQL auth integration skipped.",
)


def test_postgres_staging_authentication(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["PT_CLAIMS_TEST_DATABASE_URL"])
    monkeypatch.delenv("PT_CLAIMS_DB_PATH", raising=False)

    from app.auth_service import authenticate_user, get_user_by_username

    admin = authenticate_user("staging_admin", "StagingAdmin@2026")
    lecturer = authenticate_user("900001", "Staging@2026")

    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["must_change_password"] is True
    assert lecturer is not None
    assert lecturer["role"] == "lecturer"
    assert lecturer["staff_number"] == "900001"
    assert lecturer["must_change_password"] is True
    assert authenticate_user("900001", "WrongPassword2026") is None
    refreshed = get_user_by_username("900001")
    assert refreshed["last_login_at"]
