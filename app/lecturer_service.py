from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.audit_service import log_audit_event
from app.backup_database import backup_database
from app.config import EXPORTS_DIR
from app.data_validation import parse_bool, parse_date_value, parse_positive_float
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict, rows_to_dicts
from app.database import get_connection, init_db
from app.config import database_provider


TITLE_OPTIONS = {"Prof", "Dr", "Mr", "Ms"}
BANK_DETAIL_MARKERS = (
    "bank",
    "account number",
    "account holder",
    "branch code",
    "swift",
    "first national bank",
    "fnb",
)
LECTURER_COLUMNS = [
    "staff_number",
    "title",
    "full_name",
    "highest_qualification",
    "id_or_passport_number",
    "paye_number",
    "physical_address",
    "contact_number",
    "tariff_per_hour",
    "campus",
    "contract_start_date",
    "contract_end_date",
    "active",
]
LECTURER_EXPORT_COLUMNS = LECTURER_COLUMNS.copy()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value).strip()


def reject_bank_detail_text(data: dict[str, Any]) -> list[str]:
    for key, value in data.items():
        haystack = f"{key} {value}".lower()
        if any(marker in haystack for marker in BANK_DETAIL_MARKERS):
            return ["Bank details must not be stored in this system."]
    return []


def _normalise_data(data: dict[str, Any]) -> dict[str, Any]:
    active_value = parse_bool(data.get("active", 1))
    return {
        "staff_number": _clean(data.get("staff_number")).replace(" ", ""),
        "title": _clean(data.get("title")),
        "full_name": _clean(data.get("full_name")),
        "highest_qualification": _clean(data.get("highest_qualification")),
        "id_or_passport_number": _clean(data.get("id_or_passport_number")),
        "paye_number": _clean(data.get("paye_number")),
        "physical_address": _clean(data.get("physical_address")),
        "contact_number": _clean(data.get("contact_number")),
        "tariff_per_hour": parse_positive_float(data.get("tariff_per_hour")),
        "campus": _clean(data.get("campus")),
        "contract_start_date": parse_date_value(data.get("contract_start_date")),
        "contract_end_date": parse_date_value(data.get("contract_end_date")),
        "active": active_value,
    }


def validate_lecturer_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = reject_bank_detail_text(data)
    cleaned = _normalise_data(data)
    if not cleaned["staff_number"]:
        errors.append("Staff number is required.")
    if not cleaned["full_name"]:
        errors.append("Full name is required.")
    if cleaned["title"] not in TITLE_OPTIONS:
        errors.append("Title must be one of Prof, Dr, Mr, or Ms.")
    if not cleaned["highest_qualification"]:
        errors.append("Highest qualification is required.")
    if cleaned["tariff_per_hour"] is None:
        errors.append("Tariff per hour must be numeric and greater than zero.")
    if not cleaned["campus"]:
        errors.append("Campus is required.")
    if cleaned["contract_start_date"] is None:
        errors.append("Contract start date is required and must be valid.")
    if cleaned["contract_end_date"] is None:
        errors.append("Contract end date is required and must be valid.")
    if (
        cleaned["contract_start_date"]
        and cleaned["contract_end_date"]
        and cleaned["contract_end_date"] < cleaned["contract_start_date"]
    ):
        errors.append("Contract end date must not be earlier than contract start date.")
    if cleaned["active"] is None:
        errors.append("Active must be true/false, yes/no, or 1/0.")
    return len(errors) == 0, errors


def _row_to_dict(row) -> dict | None:
    return row_to_dict(row)


def _ensure_sqlite_schema() -> None:
    if database_provider() == "sqlite":
        init_db()


def backup_before_write_if_supported(prefix: str = "pt_claims_before_lecturer_save") -> dict[str, Any]:
    provider = database_provider()
    if provider != "sqlite":
        return {
            "performed": False,
            "mode": provider,
            "safe_message": "Production PostgreSQL mode: local SQLite backup skipped; provider backup/audit applies.",
            "path": None,
        }
    path = backup_database(prefix=prefix)
    return {
        "performed": True,
        "mode": provider,
        "safe_message": "Local SQLite backup created before lecturer write.",
        "path": path,
    }


def _rowcount_ok(cursor: Any) -> bool:
    rowcount = getattr(cursor, "rowcount", None)
    return rowcount in (None, -1, 1)


def _commit_if_supported(conn: Any) -> None:
    if hasattr(conn, "commit"):
        conn.commit()


def _attach_backup_result(record: dict | None, backup_result: dict[str, Any]) -> dict:
    output = dict(record or {})
    output["_backup_result"] = backup_result
    return output


def _audit_lecturer_write(action: str, staff_number: str, success: bool = True) -> None:
    try:
        log_audit_event(
            action,
            user=None,
            entity_type="lecturer",
            entity_id=staff_number,
            details={"staff_number": staff_number},
            success=success,
        )
    except Exception:
        return


def list_lecturers() -> pd.DataFrame:
    _ensure_sqlite_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT l.staff_number, l.title, l.full_name, l.campus, l.tariff_per_hour,
                   l.contract_start_date, l.contract_end_date, l.active
            FROM lecturers AS l
            INNER JOIN (
                SELECT staff_number, MIN(id) AS id
                FROM lecturers
                GROUP BY staff_number
            ) AS one_per_staff_number
                ON l.id = one_per_staff_number.id
            ORDER BY l.staff_number
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def get_lecturer_by_staff_number(staff_number: str) -> dict | None:
    _ensure_sqlite_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT * FROM lecturers WHERE staff_number = ? ORDER BY id LIMIT 1"),
            (_clean(staff_number).replace(" ", ""),),
        ).fetchone()
    return _row_to_dict(row)


def lecturer_exists(staff_number: str) -> bool:
    staff_number = _clean(staff_number).replace(" ", "")
    if not staff_number:
        return False
    _ensure_sqlite_schema()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT 1 FROM lecturers WHERE staff_number = ? LIMIT 1"),
            (staff_number,),
        ).fetchone()
    return row is not None


def find_duplicate_lecturers() -> pd.DataFrame:
    _ensure_sqlite_schema()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT staff_number, COUNT(*) AS count
            FROM lecturers
            GROUP BY staff_number
            HAVING COUNT(*) > 1
            ORDER BY staff_number
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def create_lecturer(data: dict[str, Any]) -> dict:
    is_valid, errors = validate_lecturer_data(data)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_data(data)
    if lecturer_exists(cleaned["staff_number"]):
        raise ValueError("Lecturer with this staff number already exists. Use Update Existing Lecturer.")
    init_runtime_db()
    backup_result = backup_before_write_if_supported(prefix="pt_claims_before_lecturer_save")
    with get_runtime_connection() as conn:
        conn.execute(
            convert_placeholders(
                """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification,
                id_or_passport_number, paye_number, physical_address, contact_number,
                tariff_per_hour, campus, contract_start_date, contract_end_date, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ),
            tuple(cleaned[column] for column in LECTURER_COLUMNS),
        )
        _commit_if_supported(conn)
    _audit_lecturer_write("lecturer_create", cleaned["staff_number"])
    return _attach_backup_result(get_lecturer_by_staff_number(cleaned["staff_number"]), backup_result)


def update_lecturer(staff_number: str, data: dict[str, Any]) -> dict:
    target_staff_number = _clean(staff_number).replace(" ", "")
    if not target_staff_number or not lecturer_exists(target_staff_number):
        raise ValueError("Lecturer with this staff number does not exist.")
    data_for_validation = dict(data) | {"staff_number": target_staff_number}
    is_valid, errors = validate_lecturer_data(data_for_validation)
    if not is_valid:
        raise ValueError("; ".join(errors))
    cleaned = _normalise_data(data_for_validation)
    init_runtime_db()
    backup_result = backup_before_write_if_supported(prefix="pt_claims_before_lecturer_save")
    with get_runtime_connection() as conn:
        cursor = conn.execute(
            convert_placeholders(
                """
            UPDATE lecturers
            SET title = ?, full_name = ?, highest_qualification = ?,
                id_or_passport_number = ?, paye_number = ?, physical_address = ?,
                contact_number = ?, tariff_per_hour = ?, campus = ?,
                contract_start_date = ?, contract_end_date = ?, active = ?
            WHERE staff_number = ?
            """,
            ),
            (
                cleaned["title"],
                cleaned["full_name"],
                cleaned["highest_qualification"],
                cleaned["id_or_passport_number"],
                cleaned["paye_number"],
                cleaned["physical_address"],
                cleaned["contact_number"],
                cleaned["tariff_per_hour"],
                cleaned["campus"],
                cleaned["contract_start_date"],
                cleaned["contract_end_date"],
                cleaned["active"],
                target_staff_number,
            ),
        )
        if not _rowcount_ok(cursor):
            raise ValueError("Lecturer update failed: selected lecturer was not updated.")
        _commit_if_supported(conn)
    _audit_lecturer_write("lecturer_update", target_staff_number)
    return _attach_backup_result(get_lecturer_by_staff_number(target_staff_number), backup_result)


def export_lecturers_to_csv(output_path: str | Path | None = None) -> str:
    init_db()
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = EXPORTS_DIR / f"lecturers_export_{timestamp}.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT staff_number, title, full_name, highest_qualification,
                   id_or_passport_number, paye_number, physical_address, contact_number,
                   tariff_per_hour, campus, contract_start_date, contract_end_date, active
            FROM lecturers
            ORDER BY staff_number
            """
        ).fetchall()

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LECTURER_EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in LECTURER_EXPORT_COLUMNS})

    return str(output_path)
