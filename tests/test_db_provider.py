from app import db_provider


def test_provider_summary_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    summary = db_provider.current_database_summary()

    assert summary["provider"] == "sqlite"


def test_provider_detects_postgresql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@example/db")

    status = db_provider.postgresql_readiness_status()

    assert status["provider"] == "postgresql"
    assert status["postgresql_configured"] is True
    assert status["status"] == "partial"
    assert any("SQLite" in note for note in status["notes"])


def test_postgresql_mode_uses_percent_s_placeholders(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@example/db")

    assert db_provider.sql_placeholder() == "%s"
    assert db_provider.convert_placeholders("WHERE username = ? AND id = ?") == "WHERE username = %s AND id = %s"
