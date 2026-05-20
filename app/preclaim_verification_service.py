from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.academic_calendar_service import NUST_2026_REFERENCE_ITEMS, fetch_calendar_exclusions_for_period
from app.config import EXPORTS_DIR, database_provider
from app.database import init_db
from app.db_provider import convert_placeholders, get_runtime_connection, row_to_dict, rows_to_dicts
from app.generation_period_service import GenerationPeriod, resolve_standard_generation_period
from app.session_generator import generate_monthly_sessions, generate_sessions_for_period
from app.student_row_safety import suspicious_student_row_reason
from app.validators import detect_clashes, parse_date


HIGH_HOURS_WARNING_THRESHOLD = 120.0


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _month_label(year: int, month: int) -> str:
    return f"{int(year)}-{int(month):02d}"


def _month_overlaps(start_date: str, end_date: str, year: int, month: int) -> tuple[bool, bool]:
    return _period_overlaps(start_date, end_date, resolve_standard_generation_period(int(year), int(month)))


def _period_overlaps(start_date: str, end_date: str, period: GenerationPeriod) -> tuple[bool, bool]:
    month_start, month_end = period.start_date, period.end_date
    contract_start = parse_date(start_date)
    contract_end = parse_date(end_date)
    overlaps = contract_start <= month_end and contract_end >= month_start
    full = contract_start <= month_start and contract_end >= month_end
    return overlaps, full


def _fetch_lecturer(staff_number: str) -> dict[str, Any] | None:
    if database_provider() == "sqlite":
        init_db()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("""
            SELECT id, staff_number, title, full_name, campus, tariff_per_hour,
                   contract_start_date, contract_end_date, active
            FROM lecturers
            WHERE staff_number = ?
            """),
            (str(staff_number),),
        ).fetchone()
    return row_to_dict(row)


def _fetch_active_groups(staff_number: str) -> pd.DataFrame:
    if database_provider() == "sqlite":
        init_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT g.id AS group_id, g.group_name, c.course_code, c.course_name,
                   g.campus, g.study_mode, g.active,
                   COALESCE(SUM(CASE WHEN ge.active = 1 THEN 1 ELSE 0 END), 0) AS active_enrolments
            FROM student_groups AS g
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            LEFT JOIN group_enrolments AS ge ON ge.group_id = g.id
            WHERE l.staff_number = ? AND g.lecturer_id IS NOT NULL AND g.active = 1
            GROUP BY g.id, g.group_name, c.course_code, c.course_name, g.campus, g.study_mode, g.active
            ORDER BY c.course_code, g.group_name
            """),
            (str(staff_number),),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def _fetch_active_timetable(staff_number: str) -> pd.DataFrame:
    if database_provider() == "sqlite":
        init_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT t.id AS timetable_id, g.id AS group_id, g.group_name,
                   c.course_code, c.course_name, t.day_of_week, t.start_time, t.end_time,
                   t.effective_start_date, t.effective_end_date, t.active
            FROM timetable_entries AS t
            JOIN lecturers AS l ON l.id = t.lecturer_id
            JOIN student_groups AS g ON g.id = t.group_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND t.active = 1 AND g.active = 1
            ORDER BY c.course_code, g.group_name, t.day_of_week, t.start_time
            """),
            (str(staff_number),),
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def _fetch_suspicious_enrolments(staff_number: str) -> pd.DataFrame:
    if database_provider() == "sqlite":
        init_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            convert_placeholders("""
            SELECT s.student_number, s.surname, s.initials, s.full_name,
                   g.group_name, c.course_code
            FROM group_enrolments AS ge
            JOIN students AS s ON s.id = ge.student_id
            JOIN student_groups AS g ON g.id = ge.group_id
            JOIN lecturers AS l ON l.id = g.lecturer_id
            JOIN courses AS c ON c.id = g.course_id
            WHERE l.staff_number = ? AND ge.active = 1 AND s.active = 1
            ORDER BY c.course_code, g.group_name, s.surname, s.initials, s.student_number
            """),
            (str(staff_number),),
        ).fetchall()
    suspicious = []
    for row in rows_to_dicts(rows):
        reason = suspicious_student_row_reason(
            row.get("student_number"),
            row.get("surname"),
            row.get("initials"),
            row.get("full_name"),
            " ".join(str(row.get(key) or "") for key in ("surname", "initials", "full_name", "student_number")),
        )
        if reason:
            item = dict(row)
            item["reason"] = reason
            suspicious.append(item)
    return pd.DataFrame(suspicious)


def _expected_calendar_items(year: int, month: int) -> list[dict[str, str]]:
    return _expected_calendar_items_for_period(resolve_standard_generation_period(int(year), int(month)))


def _expected_calendar_items_for_period(period: GenerationPeriod) -> list[dict[str, str]]:
    month_start, month_end = period.start_date, period.end_date
    expected: list[dict[str, str]] = []
    for item in NUST_2026_REFERENCE_ITEMS:
        if item.get("category") == "Reference":
            continue
        try:
            start = parse_date(item["start_date"])
            end = parse_date(item["end_date"])
        except Exception:
            continue
        if start <= month_end and end >= month_start:
            expected.append(item)
    return expected


def _calendar_exclusions_df(year: int, month: int) -> pd.DataFrame:
    return _calendar_exclusions_df_for_period(resolve_standard_generation_period(int(year), int(month)))


def _calendar_exclusions_df_for_period(period: GenerationPeriod) -> pd.DataFrame:
    month_start, month_end = period.start_date, period.end_date
    rows = fetch_calendar_exclusions_for_period(month_start.isoformat(), month_end.isoformat())
    return pd.DataFrame(rows)


def _totals_by(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return _empty_df(columns + ["sessions", "hours", "amount"])
    grouped = (
        df.groupby(columns, dropna=False)
        .agg(sessions=("session_date", "count"), hours=("hours", "sum"), amount=("amount", "sum"))
        .reset_index()
        .sort_values(columns, ignore_index=True)
    )
    grouped["hours"] = grouped["hours"].round(2)
    grouped["amount"] = grouped["amount"].round(2)
    return grouped


def build_preclaim_verification(staff_number: str, year: int, month: int) -> dict[str, Any]:
    return build_preclaim_verification_for_period(
        staff_number,
        int(year),
        int(month),
        resolve_standard_generation_period(int(year), int(month)),
    )


def build_preclaim_verification_for_period(
    staff_number: str,
    year: int,
    month: int,
    generation_period: GenerationPeriod,
) -> dict[str, Any]:
    staff_number = str(staff_number).strip()
    year = int(year)
    month = int(month)
    claim_period = generation_period
    blockers: list[str] = []
    warnings: list[str] = []

    lecturer = _fetch_lecturer(staff_number)
    if lecturer is None:
        return {
            "status": "BLOCK",
            "blockers": ["Lecturer was not found."],
            "warnings": [],
            "summary": {"staff_number": staff_number, "year": year, "month": month},
            "tables": {},
        }

    if not int(lecturer.get("active") or 0):
        blockers.append("Lecturer is inactive.")

    overlaps_contract, full_contract_overlap = _period_overlaps(
        lecturer["contract_start_date"], lecturer["contract_end_date"], generation_period
    )
    if not overlaps_contract:
        blockers.append(
            "Selected month is completely outside the lecturer contract period."
            if generation_period.mode == "standard"
            else "Selected period is completely outside the lecturer contract period."
        )
    elif not full_contract_overlap:
        warnings.append(
            "Selected month only partially overlaps the lecturer contract period."
            if generation_period.mode == "standard"
            else "Selected period only partially overlaps the lecturer contract period."
        )

    groups_df = _fetch_active_groups(staff_number)
    timetable_df = _fetch_active_timetable(staff_number)
    suspicious_enrolments_df = _fetch_suspicious_enrolments(staff_number)
    if groups_df.empty:
        blockers.append("No active lecturer-scoped groups exist for this lecturer.")
    if timetable_df.empty:
        blockers.append("No active timetable entries exist for this lecturer.")

    zero_enrolment_groups = groups_df[groups_df["active_enrolments"].fillna(0).astype(int) == 0] if not groups_df.empty else groups_df
    if not zero_enrolment_groups.empty:
        warnings.append("One or more active groups have zero active enrolments.")
    if not timetable_df.empty and not zero_enrolment_groups.empty:
        zero_group_ids = set(zero_enrolment_groups["group_id"].astype(int))
        if any(int(group_id) in zero_group_ids for group_id in timetable_df["group_id"]):
            warnings.append("Timetable entries exist for groups with zero active enrolments.")
    if not suspicious_enrolments_df.empty:
        warnings.append("One or more enrolments look like imported header rows.")

    calendar_df = _calendar_exclusions_df_for_period(generation_period)
    expected_calendar_items = _expected_calendar_items_for_period(generation_period)
    if expected_calendar_items and calendar_df.empty:
        warnings.append("Official NUST calendar items are expected for this period, but no active academic calendar exclusions were found.")

    try:
        sessions_df = (
            generate_sessions_for_period(int(staff_number), generation_period)
            if generation_period.mode == "custom"
            else generate_monthly_sessions(int(staff_number), year, month)
        )
    except Exception as exc:
        sessions_df = _empty_df([
            "course_code",
            "course_name",
            "group_name",
            "session_date",
            "start_time",
            "end_time",
            "hours",
            "amount",
        ])
        blockers.append(f"Generated sessions could not be calculated: {exc}")

    clashes_df = detect_clashes(sessions_df)
    if not clashes_df.empty:
        blockers.append("Timetable clashes exist in generated sessions.")
    if sessions_df.empty:
        warnings.append("Generated session count is zero.")

    total_sessions = int(len(sessions_df))
    total_hours = float(sessions_df["hours"].sum()) if not sessions_df.empty and "hours" in sessions_df else 0.0
    total_amount = float(sessions_df["amount"].sum()) if not sessions_df.empty and "amount" in sessions_df else 0.0
    if total_hours == 0:
        warnings.append("Generated claimable hours are zero.")
    elif total_hours > HIGH_HOURS_WARNING_THRESHOLD:
        warnings.append(f"Generated claimable hours are unusually high ({total_hours:.2f}).")

    if not sessions_df.empty and not zero_enrolment_groups.empty:
        zero_group_names = set(zero_enrolment_groups["group_name"].astype(str))
        session_zero_groups = sorted(set(sessions_df[sessions_df["group_name"].isin(zero_group_names)]["group_name"]))
        if session_zero_groups:
            warnings.append("Generated sessions include groups with missing student enrolments.")

    status = "BLOCK" if blockers else "WARN" if warnings else "PASS"
    excluded_dates_count = int(sessions_df.attrs.get("excluded_dates_count", 0)) if hasattr(sessions_df, "attrs") else 0
    applied_exclusions = sessions_df.attrs.get("applied_calendar_exclusions", []) if hasattr(sessions_df, "attrs") else []
    excluded_session_details = sessions_df.attrs.get("excluded_session_details", []) if hasattr(sessions_df, "attrs") else []
    summary = {
        "lecturer_name": lecturer["full_name"],
        "staff_number": lecturer["staff_number"],
        "campus": lecturer["campus"],
        "tariff_per_hour": float(lecturer["tariff_per_hour"]),
        "contract_start_date": lecturer["contract_start_date"],
        "contract_end_date": lecturer["contract_end_date"],
        "year": year,
        "month": month,
        "year_month": _month_label(year, month),
        "claim_period_start": claim_period.start_date.isoformat(),
        "claim_period_end": claim_period.end_date.isoformat(),
        "claim_period": claim_period.display,
        "claim_period_custom": claim_period.custom,
        "generation_period_mode": generation_period.mode,
        "generation_period_label": generation_period.label,
        "generation_period_slug": generation_period.slug,
        "month_overlaps_contract": overlaps_contract,
        "month_fully_within_contract": full_contract_overlap,
        "active_group_count": int(len(groups_df)),
        "active_timetable_entry_count": int(len(timetable_df)),
        "calendar_exclusion_count": int(len(calendar_df)),
        "excluded_dates_count": excluded_dates_count,
        "applied_calendar_exclusion_count": len(applied_exclusions),
        "total_claimable_sessions": total_sessions,
        "total_claimable_hours": round(total_hours, 2),
        "estimated_claim_amount": round(total_amount, 2),
    }
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "summary": summary,
        "tables": {
            "groups": groups_df,
            "timetable": timetable_df,
            "calendar_exclusions": calendar_df,
            "applied_calendar_exclusions": pd.DataFrame(applied_exclusions),
            "excluded_session_details": pd.DataFrame(excluded_session_details),
            "generated_sessions": sessions_df,
            "clashes": clashes_df,
            "totals_by_course": _totals_by(sessions_df, ["course_code", "course_name"]),
            "totals_by_group": _totals_by(sessions_df, ["course_code", "course_name", "group_name"]),
            "zero_enrolment_groups": zero_enrolment_groups.copy() if not zero_enrolment_groups.empty else _empty_df(list(groups_df.columns)),
            "suspicious_enrolments": suspicious_enrolments_df,
            "expected_calendar_items": pd.DataFrame(expected_calendar_items),
        },
    }


def export_preclaim_verification_report(result: dict[str, Any], output_dir: str | Path = EXPORTS_DIR) -> str:
    summary = result.get("summary", {})
    staff_number = str(summary.get("staff_number", "unknown")).replace(" ", "")
    year = int(summary.get("year", 0) or 0)
    month = int(summary.get("month", 0) or 0)
    period_slug = str(summary.get("generation_period_slug") or f"{year}_{month:02d}").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"preclaim_verification_{staff_number}_{period_slug}_{timestamp}.csv"

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "field", "value"])
        writer.writerow(["status", "status", result.get("status", "")])
        for key, value in summary.items():
            writer.writerow(["summary", key, value])
        for blocker in result.get("blockers", []):
            writer.writerow(["blocker", "message", blocker])
        for warning in result.get("warnings", []):
            writer.writerow(["warning", "message", warning])

        for table_name, table in result.get("tables", {}).items():
            if not isinstance(table, pd.DataFrame) or table.empty:
                continue
            safe_table = table.drop(
                columns=[
                    column
                    for column in table.columns
                    if column.lower() in {"id_or_passport_number", "paye_number", "password_hash", "password_salt"}
                ],
                errors="ignore",
            )
            writer.writerow([])
            writer.writerow([f"table:{table_name}"])
            writer.writerow(list(safe_table.columns))
            for row in safe_table.to_dict("records"):
                writer.writerow([row.get(column, "") for column in safe_table.columns])

    return str(output_path)
