import sqlite3
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.config import DB_PATH
from app.database import get_connection


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    return datetime.strptime(value, "%H:%M").time()


def calculate_hours(start_time: str, end_time: str) -> float:
    start = datetime.combine(date.today(), parse_time(start_time))
    end = datetime.combine(date.today(), parse_time(end_time))
    if end <= start:
        raise ValueError("end_time must be after start_time")
    total_minutes = int((end - start).total_seconds() // 60)
    return float(minutes_to_claim_hours(total_minutes))


def minutes_to_claim_hours(minutes: int) -> Decimal:
    """Return claimable hours truncated to two decimals, never rounded."""
    if minutes < 0:
        raise ValueError("minutes must not be negative")
    truncated_hundredths = minutes * 100 // 60
    return Decimal(truncated_hundredths) / Decimal(100)


def detect_clashes(sessions_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "lecturer_name",
        "staff_number",
        "session_date",
        "first_group",
        "first_time",
        "second_group",
        "second_time",
        "clash_reason",
    ]
    if sessions_df.empty:
        return pd.DataFrame(columns=columns)

    clashes: list[dict[str, str]] = []
    sort_df = sessions_df.sort_values(["lecturer_name", "session_date", "start_time", "end_time"])
    for (_, session_date), day_df in sort_df.groupby(["staff_number", "session_date"], sort=False):
        records = day_df.to_dict("records")
        for idx, first in enumerate(records):
            first_start = parse_time(first["start_time"])
            first_end = parse_time(first["end_time"])
            for second in records[idx + 1 :]:
                second_start = parse_time(second["start_time"])
                second_end = parse_time(second["end_time"])
                if first_start < second_end and second_start < first_end:
                    clashes.append(
                        {
                            "lecturer_name": first["lecturer_name"],
                            "staff_number": first["staff_number"],
                            "session_date": session_date,
                            "first_group": first["group_name"],
                            "first_time": f"{first['start_time']}-{first['end_time']}",
                            "second_group": second["group_name"],
                            "second_time": f"{second['start_time']}-{second['end_time']}",
                            "clash_reason": "Overlapping timetable sessions for the same lecturer",
                        }
                    )
    return pd.DataFrame(clashes, columns=columns)


def get_table_columns(table_name: str, db_path: str | Path = DB_PATH) -> list[str]:
    with get_connection(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row["name"] for row in rows]


def assert_no_bank_fields(db_path: str | Path = DB_PATH) -> None:
    forbidden_fragments = ("bank", "account", "branch", "iban", "swift")
    with get_connection(db_path) as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        for table in tables:
            columns = conn.execute(f"PRAGMA table_info({table['name']})").fetchall()
            for column in columns:
                lower_name = column["name"].lower()
                if any(fragment in lower_name for fragment in forbidden_fragments):
                    raise sqlite3.DatabaseError(f"Forbidden banking field found: {table['name']}.{column['name']}")
