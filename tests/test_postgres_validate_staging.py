import pytest

from app.postgres_validate_staging import EXPECTED_STAGING_COUNTS, validate_target_env_present


def test_validation_fails_clearly_when_target_url_missing(monkeypatch):
    monkeypatch.delenv("PT_CLAIMS_TEST_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="PT_CLAIMS_TEST_DATABASE_URL is not configured"):
        validate_target_env_present()


def test_validation_knows_expected_staging_counts():
    assert EXPECTED_STAGING_COUNTS["lecturers"] == 15
    assert EXPECTED_STAGING_COUNTS["courses"] == 2
    assert EXPECTED_STAGING_COUNTS["student_groups"] == 36
    assert EXPECTED_STAGING_COUNTS["timetable_entries"] == 95
    assert EXPECTED_STAGING_COUNTS["students"] == 1038
    assert EXPECTED_STAGING_COUNTS["group_enrolments"] == 1053
    assert EXPECTED_STAGING_COUNTS["user_accounts"] == 5
