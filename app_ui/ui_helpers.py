from __future__ import annotations

import calendar
from datetime import datetime
from pathlib import Path
import html
import re
import zipfile

import pandas as pd

from app.config import DATA_DIR, DB_PATH, get_app_env
from app.database import get_connection, init_db
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, rows_to_dicts
from app.config import database_provider
from app.performance_queries import admin_dashboard_counts
from app.inspect_data import _mask
from app.document_generator import output_directory
from app_docxtpl.context_builders import generated_v2_directory
from app_docxtpl.manual_templates import MANUAL_CLAIM_TEMPLATE_V2, MANUAL_REGISTER_TEMPLATE_V2


UPLOADS_DIR = DATA_DIR / "uploads"
SENSITIVE_LECTURER_FIELDS = {"id_or_passport_number", "paye_number"}
SENSITIVE_SESSION_FIELDS = {
    "id_or_passport_number",
    "paye_number",
    "physical_address",
    "contact_number",
    "highest_qualification",
}
SESSION_DISPLAY_COLUMNS = [
    "session_date",
    "day_of_week",
    "course_code",
    "course_name",
    "group_name",
    "start_time",
    "end_time",
    "hours",
    "tariff_per_hour",
    "amount",
    "exclusion_status",
    "notes",
]
BANK_FIELD_MARKERS = ("bank", "account", "branch_code", "swift", "iban")
NON_BANK_ACCOUNT_COLUMNS = {"user_account_id"}


def month_options() -> list[tuple[int, str]]:
    return [(month, calendar.month_name[month]) for month in range(1, 13)]


def month_number(month: int | str) -> int:
    if isinstance(month, int):
        if 1 <= month <= 12:
            return month
        raise ValueError("Month number must be between 1 and 12")
    text = str(month).strip()
    if text.isdigit():
        return month_number(int(text))
    lookup = {calendar.month_name[i].lower(): i for i in range(1, 13)}
    lookup.update({calendar.month_abbr[i].lower(): i for i in range(1, 13)})
    key = text.lower()
    if key not in lookup:
        raise ValueError(f"Unknown month: {month}")
    return lookup[key]


def timetable_time_options(step_minutes: int = 5) -> list[str]:
    if step_minutes <= 0 or 60 % step_minutes != 0:
        raise ValueError("step_minutes must be a positive divisor of 60")
    return [
        f"{hour:02d}:{minute:02d}"
        for hour in range(24)
        for minute in range(0, 60, step_minutes)
    ]


def mask_sensitive_columns(df: pd.DataFrame, show_sensitive: bool = False) -> pd.DataFrame:
    masked = df.copy()
    if show_sensitive:
        return masked
    for column in SENSITIVE_LECTURER_FIELDS:
        if column in masked.columns:
            masked[column] = masked[column].map(_mask)
    return masked


def safe_sessions_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[column for column in SESSION_DISPLAY_COLUMNS if df is None or column in df.columns])
    available_columns = [column for column in SESSION_DISPLAY_COLUMNS if column in df.columns]
    safe_df = df.drop(columns=[column for column in SENSITIVE_SESSION_FIELDS if column in df.columns])
    display_df = safe_df[available_columns].copy()
    if "session_date" in display_df.columns:
        display_df["session_date"] = display_df["session_date"].map(format_session_date)
    return display_df


def format_session_date(value) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)


def lecturer_display_details(df: pd.DataFrame) -> dict[str, str]:
    if df is None or df.empty:
        return {"lecturer": "", "staff_number": ""}
    lecturer = str(df["lecturer_name"].iloc[0]) if "lecturer_name" in df.columns else ""
    staff_number = str(df["staff_number"].iloc[0]) if "staff_number" in df.columns else ""
    return {"lecturer": lecturer, "staff_number": staff_number}


def lecturer_option_label(record: dict) -> str:
    return f"{record.get('staff_number', '')} - {record.get('full_name', '')}"


def lecturer_record_by_staff_number(records: list[dict], staff_number: str) -> dict:
    target = str(staff_number or "").strip()
    for record in records:
        if str(record.get("staff_number", "")).strip() == target:
            return record
    return {}


def course_option_label(record: dict) -> str:
    return f"{record.get('course_code', '')} - {record.get('course_name', '')}"


def group_option_label(record: dict) -> str:
    return f"{record.get('course_code', '')} - {record.get('group_name', '')}"


def lecturer_alias_from_full_name(full_name: str) -> str:
    text = str(full_name or "").strip()
    if not text:
        return ""
    for part in text.split():
        alias = re.sub(r"[^A-Za-z0-9]+", "", part).upper()
        if alias:
            return alias
    return ""


def build_group_name(lecturer_alias: str, group_label: str, semester: str, year: str | int) -> str:
    parts = [lecturer_alias, group_label, semester, str(year)]
    text = "_".join(str(part or "").strip() for part in parts)
    text = text.upper().replace(" ", "_")
    text = re.sub(r"[^A-Z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


LECTURER_GROUP_STALE_KEY_PREFIXES = (
    "add_lecturer_group_lecturer",
    "add_lecturer_group_course",
    "add_lecturer_group_lecturer_alias",
    "add_lecturer_group_customise_alias",
    "add_lecturer_group_generated_group_name",
    "add_lecturer_group_suggested_group_name",
    "add_lecturer_group_manual_group_name",
)


def lecturer_group_stale_keys(state: dict) -> list[str]:
    return [
        key
        for key in state
        if any(str(key).startswith(prefix) for prefix in LECTURER_GROUP_STALE_KEY_PREFIXES)
        and not str(key).startswith("phase_6_3_")
    ]


def remove_lecturer_group_stale_keys(state: dict) -> list[str]:
    keys = lecturer_group_stale_keys(state)
    for key in keys:
        state.pop(key, None)
    return keys


def mask_sensitive_value(value: str) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return f"{text[:4]}****"
    return f"{text[:6]}*****"


def file_path_display_html(path: str | Path, label: str = "Path") -> str:
    safe_label = html.escape(str(label))
    safe_path = html.escape(str(path))
    return (
        "<div class='pt-file-path'>"
        f"<span class='pt-file-path-label'>{safe_label}</span>"
        f"<code>{safe_path}</code>"
        "</div>"
    )


def output_file_display_html(path: str | Path, label: str = "Output file", size: str = "", modified: str = "") -> str:
    details = []
    if size:
        details.append(f"<span>Size: {html.escape(str(size))}</span>")
    if modified:
        details.append(f"<span>Modified: {html.escape(str(modified))}</span>")
    details_html = f"<div class='pt-file-path-meta'>{''.join(details)}</div>" if details else ""
    return file_path_display_html(path, label).replace("</div>", f"{details_html}</div>", 1)


def is_supported_upload_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".xlsx"


def can_import_workbook(dry_run_passed: bool, confirmation_checked: bool) -> bool:
    return bool(dry_run_passed and confirmation_checked)


def file_metadata(path: str | Path) -> dict[str, str | int]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Output file was not found: {file_path}")
    stat = file_path.stat()
    return {
        "path": str(file_path),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_file_metadata(path: str | Path) -> dict[str, str | int | bool | None]:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "exists": False,
            "path": str(file_path),
            "size_bytes": None,
            "size_display": "",
            "modified_timestamp_display": "",
        }
    stat = file_path.stat()
    return {
        "exists": True,
        "path": str(file_path),
        "size_bytes": stat.st_size,
        "size_display": format_file_size(stat.st_size),
        "modified_timestamp_display": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def read_file_bytes(path: str | Path) -> bytes:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Download file was not found: {file_path}")
    return file_path.read_bytes()


def export_status_payload(path: str | Path) -> dict[str, str | int | bool | None]:
    metadata = get_file_metadata(path)
    if not metadata["exists"]:
        raise FileNotFoundError("Export command completed, but output file was not found.")
    if not metadata["size_bytes"] or int(metadata["size_bytes"]) <= 0:
        raise ValueError("Export command completed, but output file is empty.")
    return metadata


def download_label(label: str, path: str | Path) -> str:
    return f"{label}: {Path(path).name}"


def grouped_sessions_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["course_code", "group_name", "sessions", "hours", "amount"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        df.groupby(["course_code", "group_name"], dropna=False)
        .agg(sessions=("session_date", "count"), hours=("hours", "sum"), amount=("amount", "sum"))
        .reset_index()
        .sort_values(["course_code", "group_name"], ignore_index=True)
    )
    grouped["hours"] = grouped["hours"].astype(float).round(2)
    grouped["amount"] = grouped["amount"].astype(float).map(format_namibian_currency)
    return grouped[columns]


def format_hours_value(value: float | int) -> str:
    return f"{float(value):.2f}"


def format_namibian_currency(value: float | int) -> str:
    return f"N$ {float(value):,.2f}"


def dashboard_counts() -> dict[str, int]:
    return admin_dashboard_counts()


def table_df(table: str, limit: int = 500) -> pd.DataFrame:
    init_runtime_db()
    allowed = {
        "lecturers",
        "courses",
        "student_groups",
        "students",
        "group_enrolments",
        "timetable_entries",
        "academic_calendar",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    with get_runtime_connection() as conn:
        rows = conn.execute(convert_placeholders(f"SELECT * FROM {table} LIMIT ?"), (int(limit),)).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def lecturers_for_selector() -> pd.DataFrame:
    init_runtime_db()
    with get_runtime_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, staff_number, full_name
            FROM lecturers
            WHERE active = 1
            ORDER BY staff_number
            """
        ).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def save_uploaded_workbook(uploaded_file, uploads_dir: Path = UPLOADS_DIR) -> Path:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    output_path = uploads_dir / Path(uploaded_file.name).name
    output_path.write_bytes(uploaded_file.getbuffer())
    return output_path


def format_import_summary(summary: dict[str, dict[str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "table": table,
                "inserted": counts.get("inserted", 0),
                "updated": counts.get("updated", 0),
                "planned": counts.get("inserted", 0) + counts.get("updated", 0),
                "skipped": counts.get("skipped", 0),
            }
            for table, counts in summary.items()
        ]
    )


def output_folder_for(staff_number: str, year: int, month: int) -> Path:
    return output_directory(year, month, str(staff_number))


def v2_output_folder_for(staff_number: str, year: int, month: int) -> Path:
    return generated_v2_directory(year, month, str(staff_number))


def missing_v2_manual_templates() -> list[Path]:
    return [
        path
        for path in (MANUAL_CLAIM_TEMPLATE_V2, MANUAL_REGISTER_TEMPLATE_V2)
        if not path.exists()
    ]


def create_registers_zip(register_paths: list[str | Path], output_zip: str | Path) -> Path:
    zip_path = Path(output_zip)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for register_path in register_paths:
            path = Path(register_path)
            if not path.exists():
                raise FileNotFoundError(f"Register file was not found: {path}")
            archive.write(path, arcname=path.name)
    return zip_path


def bank_detail_columns_exist() -> bool:
    init_db()
    with get_connection() as conn:
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        ]
        for table in tables:
            columns = [row["name"].lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            columns = [column for column in columns if column not in NON_BANK_ACCOUNT_COLUMNS]
            if any(any(marker in column for marker in BANK_FIELD_MARKERS) for column in columns):
                return True
    return False


def database_path_text() -> str:
    return str(DB_PATH)


def database_status_text() -> str:
    provider = database_provider()
    if provider == "postgresql":
        return f"Current database: PostgreSQL via DATABASE_URL | Provider: postgresql | Environment: {get_app_env()}"
    return f"Current database: {DB_PATH} | Provider: sqlite | Environment: {get_app_env()}"
