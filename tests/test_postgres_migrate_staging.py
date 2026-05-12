import pytest

from app.config import REAL_DB_PATH
from app.database import get_connection, init_db
from app.postgres_migrate_staging import dry_run, ensure_safe_source, migrate, target_url_from_env


def _build_safe_staging_source(path):
    init_db(path)
    with get_connection(path) as conn:
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES ('900001', 'Ms', 'Demo Lecturer One', 'Demo Qualification', 'DEMO-ID',
                    'DEMO-PAYE', 'Demo Address', '0810000000', 410, 'Windhoek Main Campus',
                    '2026-01-01', '2026-12-31', 1)
            """
        )


def test_migration_refuses_real_database_source():
    with pytest.raises(ValueError, match="Refusing to migrate real"):
        ensure_safe_source(REAL_DB_PATH)


def test_migration_requires_disposable_confirmation(tmp_path):
    source = tmp_path / "data" / "staging" / "pt_claims_staging_anonymised.db"
    source.parent.mkdir(parents=True)
    _build_safe_staging_source(source)

    with pytest.raises(PermissionError, match="--confirm-disposable"):
        migrate(source=source, confirm_disposable=False, yes=True)


def test_dry_run_does_not_require_postgres_connection(tmp_path, monkeypatch):
    source = tmp_path / "data" / "staging" / "pt_claims_staging_anonymised.db"
    source.parent.mkdir(parents=True)
    _build_safe_staging_source(source)
    monkeypatch.delenv("PT_CLAIMS_TEST_DATABASE_URL", raising=False)

    result = dry_run(source)

    assert result["writes_postgres"] is False
    assert result["target_configured"] is False
    assert result["source_validation"]["valid"] is True


def test_target_url_uses_test_environment_variable(monkeypatch):
    monkeypatch.setenv("PT_CLAIMS_TEST_DATABASE_URL", "postgresql://user:pass@localhost/db")

    assert target_url_from_env() == "postgresql://user:pass@localhost/db"
