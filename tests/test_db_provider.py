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


def test_init_runtime_db_recovers_from_admin_shutdown_once(monkeypatch):
    from psycopg import errors

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@example/db")
    monkeypatch.setattr(db_provider, "require_postgresql_dependency", lambda: None)
    monkeypatch.setattr(db_provider, "POSTGRES_SCHEMA_SQL", "CREATE TABLE IF NOT EXISTS demo (id integer);")
    monkeypatch.setattr(db_provider.time, "sleep", lambda _seconds: None)
    state = {"schema_execs": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _statement):
            state["schema_execs"] += 1
            if state["schema_execs"] == 1:
                raise errors.AdminShutdown("server closed the connection")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            assert statement == "SELECT 1"

        def cursor(self):
            return FakeCursor()

        def commit(self):
            state["committed"] = True

    class FakePool:
        def __init__(self):
            self.closed = 0

        def connection(self):
            return FakeConnection()

        def close(self):
            self.closed += 1

    fake_pool = FakePool()
    monkeypatch.setattr(db_provider, "_POSTGRES_POOL", fake_pool)
    monkeypatch.setattr(db_provider, "get_postgres_pool", lambda: fake_pool)

    db_provider.init_runtime_db()

    assert state["schema_execs"] == 2
    assert state["committed"] is True
    assert fake_pool.closed == 1


def test_sqlite_runtime_connection_still_uses_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "local.db"

    with db_provider.get_runtime_connection(db_path) as conn:
        conn.execute("CREATE TABLE sample (id integer)")
        conn.execute("INSERT INTO sample (id) VALUES (1)")
        count = conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0]

    assert count == 1
