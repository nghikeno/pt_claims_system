import os
from pathlib import Path
from typing import Any


VALID_APP_ENVS = {"development", "staging", "production"}
VALID_GENERATED_FILE_MODES = {"local", "ephemeral", "object_storage_pending", "object_storage"}


def _streamlit_secret(name: str, default: Any = None) -> Any:
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


def get_setting(name: str, default: Any = None) -> Any:
    value = os.environ.get(name)
    if value is not None:
        return value
    return _streamlit_secret(name, default)


def get_app_env() -> str:
    env = str(get_setting("APP_ENV", "development")).strip().lower()
    return env if env in VALID_APP_ENVS else "development"


def is_production() -> bool:
    return get_app_env() == "production"


def is_development() -> bool:
    return get_app_env() == "development"


def _bool_setting(name: str, default: bool) -> bool:
    value = get_setting(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def session_timeout_minutes() -> int:
    try:
        return max(1, int(get_setting("SESSION_TIMEOUT_MINUTES", 30)))
    except (TypeError, ValueError):
        return 30


def enable_development_page() -> bool:
    return _bool_setting("ENABLE_DEVELOPMENT_PAGE", is_development()) and not is_production()


def enable_debug_stack_traces() -> bool:
    return _bool_setting("ENABLE_DEBUG_STACK_TRACES", is_development()) and not is_production()


def generated_file_mode() -> str:
    mode = str(get_setting("GENERATED_FILE_MODE", "ephemeral" if is_production() else "local")).strip().lower()
    return mode if mode in VALID_GENERATED_FILE_MODES else "local"


def generated_file_mode_warning() -> str | None:
    if generated_file_mode() == "ephemeral":
        return "Generated files are available for immediate download only and may not persist after a cloud restart."
    return None


def database_url() -> str:
    return str(get_setting("DATABASE_URL", "") or "").strip()


def database_provider() -> str:
    url = database_url()
    if url.startswith(("postgresql://", "postgresql+psycopg://")):
        return "postgresql"
    return "sqlite"


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
EXPORTS_DIR = DATA_DIR / "exports"
TEMPLATES_DIR = DATA_DIR / "templates"
DOCX_TEMPLATES_DIR = DATA_DIR / "docx_templates"
GENERATED_DIR = DATA_DIR / "generated"
PILOTS_DIR = DATA_DIR / "pilots"
REAL_DB_PATH = DATA_DIR / "pt_claims.db"
DB_PATH = Path(os.environ.get("PT_CLAIMS_DB_PATH", REAL_DB_PATH)).expanduser().resolve()
