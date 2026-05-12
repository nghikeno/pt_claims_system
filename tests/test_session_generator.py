from datetime import date

import pandas as pd
import pytest

from app.database import get_connection
from app.seed_data import seed_database
from app.session_generator import generate_monthly_sessions, get_excluded_dates
from app.validators import detect_clashes


@pytest.fixture(autouse=True)
def seeded_database():
    seed_database()


def test_sunday_exclusion():
    excluded_dates = get_excluded_dates(2026, 2)

    assert date(2026, 2, 1) in excluded_dates
    sessions_df = generate_monthly_sessions(1, 2026, 2)
    assert "Sunday" not in set(sessions_df["day_of_week"])


def test_public_holiday_or_closure_exclusion():
    excluded_dates = get_excluded_dates(2026, 2)

    assert date(2026, 2, 9) in excluded_dates
    sessions_df = generate_monthly_sessions(1, 2026, 2)
    assert "2026-02-09" not in set(sessions_df["session_date"])
    assert "2026-02-18" not in set(sessions_df["session_date"])


def test_session_generation_inside_lecturer_contract_dates_only():
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE lecturers
            SET contract_start_date = '2026-02-10',
                contract_end_date = '2026-02-20'
            WHERE id = 1
            """
        )

    sessions_df = generate_monthly_sessions(1, 2026, 2)
    session_dates = pd.to_datetime(sessions_df["session_date"]).dt.date

    assert session_dates.min() >= date(2026, 2, 10)
    assert session_dates.max() <= date(2026, 2, 20)


def test_correct_hours_calculation():
    sessions_df = generate_monthly_sessions(1, 2026, 2)
    saturday = sessions_df[
        (sessions_df["group_name"] == "Group 7") & (sessions_df["session_date"] == "2026-02-07")
    ].iloc[0]

    assert saturday["hours"] == 3


def test_correct_amount_calculation():
    sessions_df = generate_monthly_sessions(1, 2026, 2)
    two_hour_session = sessions_df[sessions_df["hours"] == 2].iloc[0]

    assert two_hour_session["amount"] == 820


def test_clash_detection():
    sessions_df = generate_monthly_sessions(1, 2026, 2)
    clashes_df = detect_clashes(sessions_df)

    assert not clashes_df.empty
    assert any(clashes_df["session_date"] == "2026-02-02")
    assert any(clashes_df["first_group"].str.contains("Group 1") | clashes_df["second_group"].str.contains("Group 1"))


def test_back_to_back_sessions_not_treated_as_clashes():
    sessions_df = pd.DataFrame(
        [
            {
                "lecturer_name": "Lonia Nghitotelwa",
                "staff_number": "100718",
                "session_date": "2026-02-03",
                "group_name": "Group 3",
                "start_time": "09:00",
                "end_time": "11:00",
            },
            {
                "lecturer_name": "Lonia Nghitotelwa",
                "staff_number": "100718",
                "session_date": "2026-02-03",
                "group_name": "Group 9",
                "start_time": "11:00",
                "end_time": "12:00",
            },
        ]
    )

    clashes_df = detect_clashes(sessions_df)

    assert clashes_df.empty
