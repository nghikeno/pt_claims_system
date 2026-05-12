import argparse
import sys

from app.backup_database import backup_database
from app.config import DB_PATH, EXPORTS_DIR
from app.create_maria_pilot_workbook import (
    EXPECTED_AMOUNT,
    EXPECTED_HOURS,
    EXPECTED_SESSIONS,
    create_maria_pilot_workbook,
)
from app.document_generator import generate_monthly_documents
from app.export_excel import export_sessions_to_excel
from app.import_master_data import import_master_data, print_import_report, read_workbook, validate_workbook
from app.inspect_data import summary_df
from app.session_generator import generate_monthly_sessions
from app.validators import detect_clashes


PILOT_YEAR = 2026
PILOT_MONTH = 4
PILOT_STAFF_NUMBER = 1008977


def _dry_run(workbook_path):
    workbook = read_workbook(workbook_path)
    errors = validate_workbook(workbook)
    if errors:
        print_import_report(workbook_path, workbook, "FAILED", "Dry run", None, len(errors))
        for error in errors:
            print(f"- {error.format()}", file=sys.stderr)
        raise SystemExit(1)
    summary = import_master_data(workbook_path, dry_run=True)
    print_import_report(workbook_path, workbook, "PASSED", "Dry run", summary, 0)
    print("DRY RUN PASSED. No database changes were made.")


def _print_recommended_commands(workbook_path) -> None:
    print("Recommended next commands:")
    print("python -m app.backup_database")
    print(f"python -m app.import_master_data --file {workbook_path} --yes")
    print(f"python -m app.session_generator --lecturer-id {PILOT_STAFF_NUMBER} --year {PILOT_YEAR} --month {PILOT_MONTH} --export")
    print(f"python -m app.document_generator --lecturer-id {PILOT_STAFF_NUMBER} --year {PILOT_YEAR} --month {PILOT_MONTH}")


def run_maria_pilot(import_data: bool = False) -> None:
    workbook_path = create_maria_pilot_workbook()
    print("Maria Matias April 2026 pilot workbook ready.")
    print("PILOT WARNING: reconstructed from a submitted claim, not an official approved timetable.")
    print(f"Workbook path: {workbook_path}")
    _dry_run(workbook_path)

    if not import_data:
        _print_recommended_commands(workbook_path)
        return

    if DB_PATH.exists():
        print(f"Database backup: {backup_database()}")
    summary = import_master_data(workbook_path)
    print("Import completed.")
    for table, counts in summary.items():
        print(f"- {table}: {counts['inserted']} inserted, {counts['updated']} updated, {counts['skipped']} skipped")
    print("Database summary:")
    print(summary_df().to_string(index=False))

    sessions_df = generate_monthly_sessions(PILOT_STAFF_NUMBER, PILOT_YEAR, PILOT_MONTH)
    clashes_df = detect_clashes(sessions_df)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sessions_export = EXPORTS_DIR / f"sessions_lecturer_{PILOT_STAFF_NUMBER}_{PILOT_YEAR}_{PILOT_MONTH:02d}.xlsx"
    export_sessions_to_excel(sessions_df, clashes_df, sessions_export)
    documents = generate_monthly_documents(PILOT_STAFF_NUMBER, PILOT_YEAR, PILOT_MONTH)

    actual_sessions = len(sessions_df)
    actual_hours = round(float(sessions_df["hours"].sum()), 2)
    actual_amount = round(float(sessions_df["amount"].sum()), 2)
    clashes_count = len(clashes_df)
    print("Maria pilot final totals:")
    print(f"- expected sessions: {EXPECTED_SESSIONS}")
    print(f"- actual sessions: {actual_sessions}")
    print(f"- expected hours: {EXPECTED_HOURS:.2f}")
    print(f"- actual hours: {actual_hours:.2f}")
    print(f"- expected amount: {EXPECTED_AMOUNT:.2f}")
    print(f"- actual amount: {actual_amount:.2f}")
    print(f"- clashes detected: {clashes_count}")
    print(f"Sessions export: {sessions_export}")
    print(f"Attendance register: {documents['attendance_path']}")
    print(f"Claim form: {documents['claim_path']}")
    print(f"Verification checklist: {documents['verification_path']}")

    if (
        actual_sessions != EXPECTED_SESSIONS
        or actual_hours != EXPECTED_HOURS
        or actual_amount != EXPECTED_AMOUNT
        or clashes_count != 0
    ):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Maria Matias April 2026 pilot workflow.")
    parser.add_argument("--import", dest="import_data", action="store_true", help="Import and generate outputs after dry-run validation.")
    args = parser.parse_args()
    run_maria_pilot(args.import_data)


if __name__ == "__main__":
    main()
