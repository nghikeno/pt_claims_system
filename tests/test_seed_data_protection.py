import pytest

from app.config import DB_PATH
from app.dev_reset import dev_reset
from app.seed_data import REAL_SEED_PHRASE, seed_database


def test_seed_database_refuses_simulated_real_database_with_lecturers(monkeypatch):
    dev_reset()
    monkeypatch.setattr("app.seed_data.REAL_DB_PATH", DB_PATH)

    with pytest.raises(RuntimeError, match="Refusing to seed real data"):
        seed_database()


def test_seed_database_refuses_simulated_real_database_even_when_empty(monkeypatch, tmp_path):
    empty_db_path = tmp_path / "empty_real.db"
    monkeypatch.setattr("app.seed_data.DB_PATH", empty_db_path)
    monkeypatch.setattr("app.seed_data.REAL_DB_PATH", empty_db_path)

    with pytest.raises(RuntimeError, match="Refusing to seed real data"):
        seed_database()


def test_seed_database_with_explicit_confirmation_backs_up_simulated_real_database(monkeypatch):
    dev_reset()
    monkeypatch.setattr("app.seed_data.REAL_DB_PATH", DB_PATH)
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_seed_data_*.db")) if backup_dir.exists() else set()

    seed_database(confirm_real_seed=True, confirmation_phrase=REAL_SEED_PHRASE)

    after = set(backup_dir.glob("pt_claims_before_seed_data_*.db"))
    assert after - before
