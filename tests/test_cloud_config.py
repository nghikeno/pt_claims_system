import importlib
from pathlib import Path


def test_sqlite_is_default_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    import app.config as config

    importlib.reload(config)

    assert config.database_provider() == "sqlite"
    assert config.get_app_env() == "development"


def test_postgresql_url_is_detected_without_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@example/db")
    import app.config as config

    importlib.reload(config)

    assert config.database_provider() == "postgresql"


def test_generated_file_mode_defaults_to_ephemeral_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("GENERATED_FILE_MODE", raising=False)
    import app.config as config

    importlib.reload(config)

    assert config.generated_file_mode() == "ephemeral"
    assert config.generated_file_mode_warning()


def test_production_hides_development_and_debug_controls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_DEVELOPMENT_PAGE", "true")
    monkeypatch.setenv("ENABLE_DEBUG_STACK_TRACES", "true")
    import app.config as config

    assert config.enable_development_page() is False
    assert config.enable_debug_stack_traces() is False


def test_secrets_example_exists_without_live_secret_file():
    assert Path(".streamlit/secrets.example.toml").exists()
    assert ".streamlit/secrets.toml" in Path(".gitignore").read_text(encoding="utf-8")
