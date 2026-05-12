from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config import DB_PATH
from app.dev_reset import dev_reset
from app.lecturer_service import (
    create_lecturer,
    export_lecturers_to_csv,
    find_duplicate_lecturers,
    get_lecturer_by_staff_number,
    lecturer_exists,
    list_lecturers,
    reject_bank_detail_text,
    update_lecturer,
    validate_lecturer_data,
)


def valid_lecturer_data() -> dict:
    return {
        "staff_number": " 300001 ",
        "title": "Ms",
        "full_name": "Manual Entry Lecturer",
        "highest_qualification": "Dummy Qualification",
        "id_or_passport_number": "DUMMY-ID-300001",
        "paye_number": "DUMMY-PAYE-300001",
        "physical_address": "P.O. Box 000, Windhoek",
        "contact_number": "0810000002",
        "tariff_per_hour": "410",
        "campus": "Windhoek Main Campus",
        "contract_start_date": "2026-02-01",
        "contract_end_date": "2026-06-05",
        "active": "Yes",
    }


def test_validate_lecturer_data_accepts_valid_data_with_sensitive_optional_fields():
    is_valid, errors = validate_lecturer_data(valid_lecturer_data())

    assert is_valid is True
    assert errors == []


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("staff_number", "", "Staff number is required."),
        ("full_name", "", "Full name is required."),
        ("title", "Mx", "Title must be one of Prof, Dr, Mr, or Ms."),
        ("tariff_per_hour", "abc", "Tariff per hour must be numeric and greater than zero."),
        ("tariff_per_hour", 0, "Tariff per hour must be numeric and greater than zero."),
    ],
)
def test_validate_lecturer_data_rejects_invalid_required_values(field, value, expected):
    data = valid_lecturer_data()
    data[field] = value

    is_valid, errors = validate_lecturer_data(data)

    assert is_valid is False
    assert expected in errors


def test_validate_lecturer_data_rejects_end_date_before_start_date():
    data = valid_lecturer_data()
    data["contract_start_date"] = "2026-06-05"
    data["contract_end_date"] = "2026-02-01"

    is_valid, errors = validate_lecturer_data(data)

    assert is_valid is False
    assert "Contract end date must not be earlier than contract start date." in errors


def test_validate_lecturer_data_rejects_bank_detail_text():
    data = valid_lecturer_data()
    data["physical_address"] = "First National Bank account number 123"

    is_valid, errors = validate_lecturer_data(data)

    assert is_valid is False
    assert "Bank details must not be stored in this system." in errors
    assert reject_bank_detail_text({"notes": "branch code 123"}) == [
        "Bank details must not be stored in this system."
    ]


def test_create_lecturer_inserts_and_gets_lecturer():
    dev_reset()

    record = create_lecturer(valid_lecturer_data())
    fetched = get_lecturer_by_staff_number("300001")
    lecturers = list_lecturers()

    assert record["staff_number"] == "300001"
    assert fetched["full_name"] == "Manual Entry Lecturer"
    assert "300001" in set(lecturers["staff_number"])
    assert lecturer_exists("300001") is True
    assert lecturer_exists("399999") is False
    assert len(lecturers["staff_number"]) == len(set(lecturers["staff_number"]))


def test_create_lecturer_creates_protection_backup():
    dev_reset()
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_lecturer_save_*.db")) if backup_dir.exists() else set()

    create_lecturer(valid_lecturer_data())

    after = set(backup_dir.glob("pt_claims_before_lecturer_save_*.db"))
    assert after - before


def test_create_lecturer_rejects_duplicate_staff_number():
    dev_reset()
    create_lecturer(valid_lecturer_data())

    with pytest.raises(ValueError, match="already exists"):
        create_lecturer(valid_lecturer_data())


def test_update_lecturer_updates_allowed_fields():
    dev_reset()
    create_lecturer(valid_lecturer_data())
    updated_data = valid_lecturer_data() | {
        "title": "Dr",
        "full_name": "Updated Lecturer",
        "campus": "Distance / Online",
        "tariff_per_hour": 460,
        "contract_start_date": "2026-03-01",
        "contract_end_date": "2026-07-01",
        "active": False,
    }

    record = update_lecturer("300001", updated_data)

    assert record["title"] == "Dr"
    assert record["full_name"] == "Updated Lecturer"
    assert record["campus"] == "Distance / Online"
    assert record["tariff_per_hour"] == 460
    assert record["contract_start_date"] == "2026-03-01"
    assert record["contract_end_date"] == "2026-07-01"
    assert record["active"] == 0
    lecturers = list_lecturers()
    assert list(lecturers["staff_number"]).count("300001") == 1


def test_update_lecturer_creates_protection_backup():
    dev_reset()
    create_lecturer(valid_lecturer_data())
    backup_dir = DB_PATH.parent / "backups"
    before = set(backup_dir.glob("pt_claims_before_lecturer_save_*.db")) if backup_dir.exists() else set()

    update_lecturer("300001", valid_lecturer_data() | {"full_name": "Backup Update Lecturer"})

    after = set(backup_dir.glob("pt_claims_before_lecturer_save_*.db"))
    assert after - before


def test_update_lecturer_can_reactivate_lecturer():
    dev_reset()
    create_lecturer(valid_lecturer_data())
    inactive_data = valid_lecturer_data() | {"active": False}
    active_data = valid_lecturer_data() | {"active": True}

    inactive = update_lecturer("300001", inactive_data)
    active = update_lecturer("300001", active_data)

    assert inactive["active"] == 0
    assert active["active"] == 1


def test_update_lecturer_fails_for_missing_staff_number():
    dev_reset()

    with pytest.raises(ValueError, match="does not exist"):
        update_lecturer("999999", valid_lecturer_data())


def test_export_lecturers_to_csv_creates_recovery_export(tmp_path):
    dev_reset()
    create_lecturer(valid_lecturer_data())
    output_path = tmp_path / "lecturers.csv"

    result = Path(export_lecturers_to_csv(output_path))
    text = result.read_text(encoding="utf-8")

    assert result == output_path
    assert "staff_number,title,full_name" in text
    assert "300001" in text
    assert "Manual Entry Lecturer" in text
    assert "bank" not in text.lower()


def test_find_duplicate_lecturers_detects_manually_existing_duplicates(monkeypatch, tmp_path):
    db_path = tmp_path / "duplicates.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE lecturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_number TEXT NOT NULL,
                title TEXT,
                full_name TEXT,
                campus TEXT,
                tariff_per_hour REAL,
                contract_start_date TEXT,
                contract_end_date TEXT,
                active INTEGER
            );
            INSERT INTO lecturers (
                staff_number, title, full_name, campus, tariff_per_hour,
                contract_start_date, contract_end_date, active
            )
            VALUES
                ('300001', 'Ms', 'First Lecturer', 'Windhoek Main Campus', 410, '2026-02-01', '2026-06-05', 1),
                ('300001', 'Ms', 'Duplicate Lecturer', 'Windhoek Main Campus', 410, '2026-02-01', '2026-06-05', 1),
                ('300002', 'Mr', 'Unique Lecturer', 'Windhoek Main Campus', 410, '2026-02-01', '2026-06-05', 1);
            """
        )

    def temp_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.lecturer_service.init_db", lambda: None)
    monkeypatch.setattr("app.lecturer_service.get_connection", temp_connection)

    duplicates = find_duplicate_lecturers()
    lecturers = list_lecturers()

    assert duplicates.to_dict("records") == [{"staff_number": "300001", "count": 2}]
    assert list(lecturers["staff_number"]).count("300001") == 1
