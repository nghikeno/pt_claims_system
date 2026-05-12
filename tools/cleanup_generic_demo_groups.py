from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DB_PATH

BACKUP_PATH = DB_PATH.parent / "pt_claims_BEFORE_GENERIC_GROUP_CLEANUP_20260511.db"


def _connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def analyse_generic_groups(db_path: str | Path = DB_PATH) -> dict:
    with _connect(db_path) as conn:
        generic_groups = conn.execute(
            """
            SELECT g.id, g.group_name, c.course_code, c.course_name, g.campus, g.study_mode, g.active
            FROM student_groups AS g
            JOIN courses AS c ON c.id = g.course_id
            WHERE g.lecturer_id IS NULL
            ORDER BY c.course_code, g.group_name
            """
        ).fetchall()
        group_ids = [int(row["id"]) for row in generic_groups]
        placeholders = ",".join("?" for _ in group_ids) or "NULL"
        timetable_entries = conn.execute(
            f"""
            SELECT t.id, t.group_id, g.group_name, c.course_code, t.lecturer_id,
                   t.day_of_week, t.start_time, t.end_time,
                   t.effective_start_date, t.effective_end_date
            FROM timetable_entries AS t
            JOIN student_groups AS g ON g.id = t.group_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE t.group_id IN ({placeholders})
            ORDER BY t.id
            """,
            tuple(group_ids),
        ).fetchall()
        enrolments = conn.execute(
            f"""
            SELECT e.id, e.group_id, g.group_name, c.course_code
            FROM group_enrolments AS e
            JOIN student_groups AS g ON g.id = e.group_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE e.group_id IN ({placeholders})
            ORDER BY e.id
            """,
            tuple(group_ids),
        ).fetchall()
        counts = {
            "lecturers": conn.execute("SELECT COUNT(*) FROM lecturers").fetchone()[0],
            "courses": conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
            "student_groups": conn.execute("SELECT COUNT(*) FROM student_groups").fetchone()[0],
            "generic_groups": len(generic_groups),
            "lecturer_scoped_groups": conn.execute(
                "SELECT COUNT(*) FROM student_groups WHERE lecturer_id IS NOT NULL"
            ).fetchone()[0],
            "timetable_entries": conn.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0],
            "linked_timetable_entries": len(timetable_entries),
            "linked_group_enrolments": len(enrolments),
        }
    return {
        "generic_groups": [dict(row) for row in generic_groups],
        "linked_timetable_entries": [dict(row) for row in timetable_entries],
        "linked_group_enrolments": [dict(row) for row in enrolments],
        "counts": counts,
    }


def cleanup_generic_groups(db_path: str | Path = DB_PATH, yes: bool = False) -> dict:
    before = analyse_generic_groups(db_path)
    if not yes:
        return {"before": before, "after": before, "backup": None, "changed": False}

    db_path = Path(db_path)
    backup_path = db_path.parent / BACKUP_PATH.name
    shutil.copy2(db_path, backup_path)
    group_ids = [int(row["id"]) for row in before["generic_groups"]]
    if group_ids:
        placeholders = ",".join("?" for _ in group_ids)
        with _connect(db_path) as conn:
            conn.execute(f"DELETE FROM timetable_entries WHERE group_id IN ({placeholders})", tuple(group_ids))
            conn.execute(f"DELETE FROM group_enrolments WHERE group_id IN ({placeholders})", tuple(group_ids))
            conn.execute(f"DELETE FROM student_groups WHERE id IN ({placeholders})", tuple(group_ids))
    after = analyse_generic_groups(db_path)
    return {"before": before, "after": after, "backup": str(backup_path), "changed": True}


def _print_rows(title: str, rows: list[dict]) -> None:
    print(title)
    if not rows:
        print("  none")
        return
    for row in rows:
        print(f"  {row}")


def print_report(result: dict, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"Generic demo group cleanup: {mode}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    before = result["before"]
    after = result["after"]
    print("Counts before:")
    for key, value in before["counts"].items():
        print(f"  {key}: {value}")
    _print_rows("Generic groups to be deleted:", before["generic_groups"])
    _print_rows("Linked timetable entries to be deleted:", before["linked_timetable_entries"])
    _print_rows("Linked group enrolments to be deleted because of foreign-key references:", before["linked_group_enrolments"])
    print("Counts after:")
    for key, value in after["counts"].items():
        print(f"  {key}: {value}")
    if result.get("backup"):
        print(f"Backup created: {result['backup']}")
    if dry_run:
        print("No changes made. Re-run with --yes to apply cleanup after reviewing this output.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely remove old generic demo groups with lecturer_id NULL.")
    parser.add_argument("--dry-run", action="store_true", help="Print cleanup plan without changing the database.")
    parser.add_argument("--yes", action="store_true", help="Apply cleanup after creating a backup.")
    args = parser.parse_args()
    dry_run = not args.yes
    result = cleanup_generic_groups(DB_PATH, yes=args.yes)
    print_report(result, dry_run=dry_run)


if __name__ == "__main__":
    main()
