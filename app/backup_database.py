import shutil
import sys
from datetime import datetime
from pathlib import Path

from app.config import DB_PATH


BACKUPS_DIR = DB_PATH.parent / "backups"


def backup_database(prefix: str = "pt_claims_backup", db_path: str | Path = DB_PATH, backups_dir: str | Path | None = None) -> str:
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"Database does not exist at {source}")
    target_dir = Path(backups_dir) if backups_dir is not None else source.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target_dir / f"{prefix}_{timestamp}.db"
    counter = 1
    while backup_path.exists():
        backup_path = target_dir / f"{prefix}_{timestamp}_{counter}.db"
        counter += 1
    shutil.copy2(source, backup_path)
    return str(backup_path)


def main() -> None:
    try:
        path = backup_database()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(f"Database backup created: {path}")


if __name__ == "__main__":
    main()
