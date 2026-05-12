from __future__ import annotations

import argparse

from app.auth_service import DEFAULT_LECTURER_PASSWORD, create_or_update_user_account, lecturer_id_for_staff_number
from app.backup_database import backup_database
from app.database import init_db


LECTURER_ACCOUNTS = {
    "1001259": "Mervin Nolin Shaun Mokhatu",
    "1009470": "Alvina Niiro Hilifavali Hailonga",
    "100718": "Lonia Nghitotelwa",
    "1008977": "Maria Matias",
}


def bootstrap_lecturer_accounts(write: bool = False) -> dict:
    init_db()
    summary = {"created": [], "updated": [], "missing": [], "dry_run": not write, "backup": None}
    plan: list[tuple[str, int]] = []
    for staff_number in LECTURER_ACCOUNTS:
        lecturer_id = lecturer_id_for_staff_number(staff_number)
        if lecturer_id is None:
            summary["missing"].append(staff_number)
        else:
            plan.append((staff_number, lecturer_id))
    if not write:
        summary["would_process"] = [staff_number for staff_number, _lecturer_id in plan]
        return summary
    summary["backup"] = backup_database(prefix="pt_claims_before_auth_bootstrap")
    for staff_number, lecturer_id in plan:
        result = create_or_update_user_account(
            username=staff_number,
            password=DEFAULT_LECTURER_PASSWORD,
            role="lecturer",
            lecturer_id=lecturer_id,
            must_change_password=True,
            active=True,
        )
        summary[result].append(staff_number)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap lecturer login accounts.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created or updated without writing.")
    parser.add_argument("--yes", action="store_true", help="Create/update lecturer accounts.")
    args = parser.parse_args()
    if not args.dry_run and not args.yes:
        parser.error("Use --dry-run to inspect or --yes to write.")
    summary = bootstrap_lecturer_accounts(write=args.yes)
    print("Lecturer account bootstrap summary")
    print(f"dry_run: {summary['dry_run']}")
    if summary.get("backup"):
        print(f"backup: {summary['backup']}")
    print(f"created accounts: {summary.get('created', [])}")
    print(f"updated accounts: {summary.get('updated', [])}")
    print(f"would process: {summary.get('would_process', [])}")
    print(f"skipped/missing lecturers: {summary.get('missing', [])}")


if __name__ == "__main__":
    main()
