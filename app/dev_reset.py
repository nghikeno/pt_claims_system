import argparse
import sys

from app.backup_database import backup_database
from app.config import DB_PATH, REAL_DB_PATH
from app.database import get_connection, init_db
from app.seed_data import REAL_SEED_PHRASE, seed_clean_demo_data, seed_database

REAL_RESET_PHRASE = "I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA"


def _is_real_database() -> bool:
    return DB_PATH.resolve() == REAL_DB_PATH.resolve()


def _lecturer_count() -> int:
    if not DB_PATH.exists():
        return 0
    init_db()
    with get_connection(DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) AS count FROM lecturers").fetchone()["count"])


def _drop_existing_tables() -> None:
    with get_connection(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        for table in tables:
            if table["name"] != "sqlite_sequence":
                conn.execute(f"DROP TABLE IF EXISTS {table['name']}")
        conn.execute("DELETE FROM sqlite_sequence")
        conn.execute("PRAGMA foreign_keys = ON")


def _assert_reset_allowed(confirm_real_reset: bool = False, confirmation_phrase: str = "") -> None:
    if not _is_real_database():
        return
    count = _lecturer_count()
    if not confirm_real_reset or confirmation_phrase != REAL_RESET_PHRASE:
        detail = " because lecturer records exist" if count > 0 else ""
        raise RuntimeError(
            f"Refusing to reset real data/pt_claims.db{detail}. "
            "This command deletes data. To proceed intentionally, pass --confirm-real-reset "
            f"--phrase {REAL_RESET_PHRASE}"
        )


def dev_reset(confirm_real_reset: bool = False, confirmation_phrase: str = "") -> None:
    _assert_reset_allowed(confirm_real_reset, confirmation_phrase)
    if DB_PATH.exists():
        backup_database(prefix="pt_claims_before_dev_reset")
        try:
            DB_PATH.unlink()
        except PermissionError:
            _drop_existing_tables()
    init_db()
    seed_database(confirm_real_seed=confirm_real_reset, confirmation_phrase=REAL_SEED_PHRASE)
    seed_clean_demo_data(confirm_real_seed=confirm_real_reset, confirmation_phrase=REAL_SEED_PHRASE)


def main() -> None:
    print("DEVELOPMENT ONLY: THIS WILL DELETE LOCAL DATA.")
    print("Do not use this command on production or real imported data.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-real-reset", action="store_true")
    parser.add_argument("--phrase", default="")
    args = parser.parse_args()
    try:
        dev_reset(confirm_real_reset=args.confirm_real_reset, confirmation_phrase=args.phrase)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(f"Recreated and seeded development database at {DB_PATH}")
    print("Seeded clash test dataset and clean no-clash demo dataset.")


if __name__ == "__main__":
    main()
