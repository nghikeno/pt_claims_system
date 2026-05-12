import subprocess
import sys
from pathlib import Path

from app.backup_database import backup_database
from app.dev_reset import dev_reset
from app.inspect_data import lecturers_df, summary_df
from app.master_data_template import generate_master_data_template
from app.preflight import run_preflight


def test_backup_command_creates_backup_file():
    dev_reset()

    backup_path = Path(backup_database())

    assert backup_path.exists()
    assert backup_path.name.startswith("pt_claims_backup_")


def test_inspect_data_summary_runs_without_error():
    dev_reset()

    df = summary_df()

    assert not df.empty
    assert "lecturers" in set(df["table"])


def test_lecturer_inspection_masks_sensitive_fields_by_default():
    dev_reset()

    df = lecturers_df(show_sensitive=False)
    row = df[df["staff_number"] == "200001"].iloc[0]

    assert "DUMMY-ID-200001" not in row["id_or_passport_number"]
    assert "*" in row["id_or_passport_number"]
    assert "DUMMY-PAYE-200001" not in row["paye_number"]


def test_preflight_runs_and_returns_expected_status(tmp_path):
    dev_reset()
    workbook_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    status, messages = run_preflight(workbook_path, 2026, 2)

    assert status in {"PASS", "WARNING"}
    assert any("Dry-run validation passed" in message for message in messages)


def test_import_cli_supports_yes_when_database_has_existing_records(tmp_path):
    dev_reset()
    workbook_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.import_master_data",
            "--file",
            str(workbook_path),
            "--yes",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Database write mode: Import" in result.stdout
