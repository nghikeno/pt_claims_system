import argparse
import calendar
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.academic_calendar_service import calendar_exclusion_applies, fetch_calendar_exclusions_for_period
from app.claim_period_service import resolve_claim_period
from app.config import EXPORTS_DIR
from app.db_provider import convert_placeholders, get_runtime_connection, row_to_dict, rows_to_dicts
from app.export_excel import export_sessions_to_excel
from app.validators import calculate_hours, detect_clashes, parse_date


DAY_NAMES = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def dates_between(start_date: date, end_date: date) -> list[date]:
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def get_excluded_dates(year: int, month: int) -> set[date]:
    claim_period = resolve_claim_period(year, month)
    period_start, period_end = claim_period.start_date, claim_period.end_date
    excluded = {day for day in dates_between(period_start, period_end) if day.weekday() == DAY_NAMES["Sunday"]}

    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT start_date, end_date
            FROM academic_calendar
            WHERE lower(action) = 'exclude'
              AND COALESCE(active, 1) = 1
              AND COALESCE(exclude_from_claims_and_registers, 1) = 1
              AND COALESCE(scope_type, 'all') = 'all'
              AND COALESCE(start_time, '') = ''
              AND COALESCE(end_time, '') = ''
              AND date(start_date) <= date(?)
              AND date(end_date) >= date(?)
            """),
            (period_end.isoformat(), period_start.isoformat()),
        ).fetchall()

    for row in rows:
        row = row_to_dict(row) or {}
        start = max(parse_date(row["start_date"]), period_start)
        end = min(parse_date(row["end_date"]), period_end)
        excluded.update(dates_between(start, end))
    return excluded


def _calendar_exclusion_label(row: dict) -> str:
    title = str(row.get("title") or "Academic calendar exclusion")
    calendar_type = str(row.get("calendar_type") or "").replace("_", " ").title()
    return f"{title} ({calendar_type})" if calendar_type else title


def resolve_lecturer_id(lecturer_identifier: int) -> int:
    with get_runtime_connection() as conn:
        by_id = conn.execute(
            convert_placeholders("SELECT * FROM lecturers WHERE id = ? AND active = 1"),
            (lecturer_identifier,),
        ).fetchone()
        if by_id is not None:
            return int((row_to_dict(by_id) or {})["id"])
        by_staff = conn.execute(
            convert_placeholders("SELECT id FROM lecturers WHERE staff_number = ? AND active = 1"),
            (str(lecturer_identifier),),
        ).fetchone()
        if by_staff is not None:
            return int((row_to_dict(by_staff) or {})["id"])
    raise ValueError(f"No active lecturer found for id or staff number {lecturer_identifier}")


def _fetch_lecturer(lecturer_id: int) -> dict:
    resolved_lecturer_id = resolve_lecturer_id(lecturer_id)
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT * FROM lecturers WHERE id = ? AND active = 1"),
            (resolved_lecturer_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"No active lecturer found for id {lecturer_id}")
    return row_to_dict(row) or {}


def _fetch_timetable_entries(lecturer_id: int) -> list[dict]:
    resolved_lecturer_id = resolve_lecturer_id(lecturer_id)
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT
                te.*,
                sg.group_name,
                sg.campus AS group_campus,
                c.course_code,
                c.id AS course_id,
                c.course_name,
                c.faculty,
                c.department,
                c.budget_allocation
            FROM timetable_entries te
            JOIN student_groups sg ON sg.id = te.group_id
            JOIN courses c ON c.id = sg.course_id
            WHERE te.lecturer_id = ?
              AND te.active = 1
              AND sg.active = 1
              AND c.active = 1
            """),
            (resolved_lecturer_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def generate_monthly_sessions(lecturer_id: int, year: int, month: int) -> pd.DataFrame:
    lecturer = _fetch_lecturer(lecturer_id)
    timetable_entries = _fetch_timetable_entries(lecturer_id)
    excluded_dates = get_excluded_dates(year, month)
    claim_period = resolve_claim_period(year, month)
    period_start, period_end = claim_period.start_date, claim_period.end_date
    contract_start = parse_date(lecturer["contract_start_date"])
    contract_end = parse_date(lecturer["contract_end_date"])
    calendar_exclusions = fetch_calendar_exclusions_for_period(period_start.isoformat(), period_end.isoformat())

    generation_start = max(period_start, contract_start)
    generation_end = min(period_end, contract_end)
    columns = [
        "lecturer_name",
        "title",
        "staff_number",
        "highest_qualification",
        "id_or_passport_number",
        "paye_number",
        "physical_address",
        "contact_number",
        "course_code",
        "lecturer_id",
        "course_id",
        "group_id",
        "course_name",
        "faculty",
        "department",
        "budget_allocation",
        "group_name",
        "campus",
        "session_date",
        "day_of_week",
        "start_time",
        "end_time",
        "hours",
        "tariff_per_hour",
        "amount",
        "exclusion_status",
        "notes",
    ]
    if generation_start > generation_end:
        empty_df = pd.DataFrame(columns=columns)
        empty_df.attrs["excluded_dates_count"] = len(excluded_dates)
        empty_df.attrs["claim_period_start"] = period_start.isoformat()
        empty_df.attrs["claim_period_end"] = period_end.isoformat()
        empty_df.attrs["claim_period_label"] = claim_period.label
        empty_df.attrs["applied_calendar_exclusions"] = []
        empty_df.attrs["excluded_session_details"] = []
        return empty_df

    sessions = []
    applied_exclusions: dict[int | str, dict] = {}
    excluded_session_details: list[dict] = []
    for session_date in dates_between(generation_start, generation_end):
        day_name = session_date.strftime("%A")
        for entry in timetable_entries:
            if entry["day_of_week"] != day_name:
                continue
            if not (parse_date(entry["effective_start_date"]) <= session_date <= parse_date(entry["effective_end_date"])):
                continue
            session_scope = {
                "session_date": session_date.isoformat(),
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "lecturer_id": entry["lecturer_id"],
                "course_id": entry["course_id"],
                "group_id": entry["group_id"],
            }
            applied = [row for row in calendar_exclusions if calendar_exclusion_applies(row, session_scope)]
            if session_date in excluded_dates and not applied:
                excluded_session_details.append(
                    {
                        "session_date": session_date.isoformat(),
                        "course_code": entry["course_code"],
                        "group_name": entry["group_name"],
                        "start_time": entry["start_time"],
                        "end_time": entry["end_time"],
                        "reason": "Sunday or full-day all-scope exclusion",
                    }
                )
                continue
            if applied:
                for exclusion in applied:
                    exclusion_key = exclusion.get("id") or exclusion.get("calendar_id") or _calendar_exclusion_label(exclusion)
                    applied_exclusions[exclusion_key] = {
                        "id": exclusion.get("id") or exclusion.get("calendar_id"),
                        "title": exclusion.get("title"),
                        "calendar_type": exclusion.get("calendar_type"),
                        "start_date": exclusion.get("start_date"),
                        "end_date": exclusion.get("end_date"),
                        "start_time": exclusion.get("start_time"),
                        "end_time": exclusion.get("end_time"),
                        "scope_type": exclusion.get("scope_type"),
                    }
                    excluded_session_details.append(
                        {
                            "session_date": session_date.isoformat(),
                            "course_code": entry["course_code"],
                            "group_name": entry["group_name"],
                            "start_time": entry["start_time"],
                            "end_time": entry["end_time"],
                            "reason": _calendar_exclusion_label(exclusion),
                        }
                    )
                continue
            hours = calculate_hours(entry["start_time"], entry["end_time"])
            tariff = float(lecturer["tariff_per_hour"])
            amount = float(round(hours * tariff, 2))
            sessions.append(
                {
                    "lecturer_name": lecturer["full_name"],
                    "title": lecturer["title"],
                    "staff_number": lecturer["staff_number"],
                    "highest_qualification": lecturer["highest_qualification"],
                    "id_or_passport_number": lecturer["id_or_passport_number"],
                    "paye_number": lecturer["paye_number"],
                    "physical_address": lecturer["physical_address"],
                    "contact_number": lecturer["contact_number"],
                    "course_code": entry["course_code"],
                    "lecturer_id": entry["lecturer_id"],
                    "course_id": entry["course_id"],
                    "group_id": entry["group_id"],
                    "course_name": entry["course_name"],
                    "faculty": entry["faculty"],
                    "department": entry["department"],
                    "budget_allocation": entry["budget_allocation"],
                    "group_name": entry["group_name"],
                    "campus": entry["group_campus"],
                    "session_date": session_date.isoformat(),
                    "day_of_week": day_name,
                    "start_time": entry["start_time"],
                    "end_time": entry["end_time"],
                    "hours": hours,
                    "tariff_per_hour": tariff,
                    "amount": amount,
                    "exclusion_status": "included",
                    "notes": "",
                }
            )
    sessions_df = pd.DataFrame(sessions, columns=columns).sort_values(
        ["session_date", "start_time", "group_name"], ignore_index=True
    )
    sessions_df.attrs["excluded_dates_count"] = len(excluded_dates)
    sessions_df.attrs["claim_period_start"] = period_start.isoformat()
    sessions_df.attrs["claim_period_end"] = period_end.isoformat()
    sessions_df.attrs["claim_period_label"] = claim_period.label
    sessions_df.attrs["applied_calendar_exclusions"] = list(applied_exclusions.values())
    sessions_df.attrs["excluded_session_details"] = excluded_session_details
    return sessions_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly lecturer sessions.")
    parser.add_argument("--lecturer-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--export", action="store_true", help="Export generated sessions to Excel.")
    args = parser.parse_args()

    sessions_df = generate_monthly_sessions(args.lecturer_id, args.year, args.month)
    clashes_df = detect_clashes(sessions_df)
    print(sessions_df.to_string(index=False))
    print(f"\nTotal sessions: {len(sessions_df)}")
    print(f"Total hours: {sessions_df['hours'].sum() if not sessions_df.empty else 0}")
    print(f"Total amount: {sessions_df['amount'].sum() if not sessions_df.empty else 0}")
    print(f"Clashes detected: {len(clashes_df)}")

    if args.export:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = Path(EXPORTS_DIR) / f"sessions_lecturer_{args.lecturer_id}_{args.year}_{args.month:02d}.xlsx"
        export_sessions_to_excel(sessions_df, clashes_df, output_path)
        print(f"Exported Excel file to {output_path}")


if __name__ == "__main__":
    main()
