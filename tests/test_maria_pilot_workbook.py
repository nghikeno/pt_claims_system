from pathlib import Path

import pandas as pd
import pytest

from app.create_maria_pilot_workbook import (
    EXPECTED_AMOUNT,
    EXPECTED_HOURS,
    EXPECTED_SESSIONS,
    PILOT_PATH,
    create_maria_pilot_workbook,
)
from app.database import get_connection
from app.dev_reset import dev_reset
from app.import_master_data import import_master_data
from app.master_data_template import META_SHEETS, SHEET_COLUMNS
from app.session_generator import generate_monthly_sessions
from app.validators import assert_no_bank_fields, detect_clashes


@pytest.fixture(autouse=True)
def reset_database():
    dev_reset()


def test_maria_pilot_workbook_is_created_at_required_path():
    path = create_maria_pilot_workbook()

    assert path == PILOT_PATH
    assert Path("data/pilots/maria_matias_april_2026_master_data.xlsx").exists()


def test_maria_pilot_workbook_contains_all_required_sheets():
    path = create_maria_pilot_workbook()
    workbook = pd.read_excel(path, sheet_name=None)

    for sheet_name in [*META_SHEETS, *SHEET_COLUMNS.keys()]:
        assert sheet_name in workbook


def test_maria_pilot_dry_run_import_passes():
    path = create_maria_pilot_workbook()

    summary = import_master_data(path, dry_run=True)

    assert summary["lecturers"]["inserted"] == 1
    assert summary["students"]["inserted"] == 96


def test_maria_pilot_import_succeeds_and_generates_expected_april_sessions():
    path = create_maria_pilot_workbook()

    import_master_data(path)
    sessions_df = generate_monthly_sessions(1008977, 2026, 4)
    clashes_df = detect_clashes(sessions_df)

    assert len(sessions_df) == EXPECTED_SESSIONS
    assert round(float(sessions_df["hours"].sum()), 2) == EXPECTED_HOURS
    assert round(float(sessions_df["amount"].sum()), 2) == EXPECTED_AMOUNT
    assert clashes_df.empty
    assert {
        "CUS HORTICULTURE",
        "CUS GROUP A",
        "CUS GROUP B",
        "ICT GROUP A",
        "ICT GROUP B",
        "ICT BOA-EENANHA",
        "ICT GREY",
        "ICT Distance",
    }.issubset(set(sessions_df["group_name"]))


def test_maria_pilot_database_has_no_bank_detail_columns():
    path = create_maria_pilot_workbook()
    import_master_data(path)

    assert_no_bank_fields()
