from __future__ import annotations

import argparse

from app.auth_service import create_or_update_user_account
from app.backup_database import backup_database
from app.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an admin account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        parser.error("Use --yes to create or update an admin account.")
    init_db()
    backup = backup_database(prefix="pt_claims_before_admin_account")
    result = create_or_update_user_account(
        username=args.username,
        password=args.password,
        role="admin",
        lecturer_id=None,
        must_change_password=False,
        active=True,
    )
    print(f"Admin account {result}: {args.username}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
