import pandas as pd
import pytest
import zipfile
import inspect

import app_ui.ui_helpers as ui_helpers
from app.dev_reset import dev_reset
from app_docxtpl.manual_templates import MANUAL_CLAIM_TEMPLATE_V2, MANUAL_REGISTER_TEMPLATE_V2
from app_ui.ui_helpers import (
    bank_detail_columns_exist,
    build_group_name,
    can_import_workbook,
    course_option_label,
    create_registers_zip,
    database_status_text,
    download_label,
    export_status_payload,
    file_metadata,
    file_path_display_html,
    output_file_display_html,
    get_file_metadata,
    format_hours_value,
    format_namibian_currency,
    format_session_date,
    grouped_sessions_summary_df,
    group_option_label,
    is_supported_upload_filename,
    lecturer_alias_from_full_name,
    lecturer_group_stale_keys,
    lecturer_option_label,
    lecturer_record_by_staff_number,
    lecturer_display_details,
    mask_sensitive_value,
    mask_sensitive_columns,
    missing_v2_manual_templates,
    month_number,
    output_folder_for,
    read_file_bytes,
    remove_lecturer_group_stale_keys,
    safe_sessions_display_df,
    v2_output_folder_for,
)


def test_mask_sensitive_columns_hides_lecturer_sensitive_values():
    df = pd.DataFrame(
        [
            {
                "staff_number": "200001",
                "id_or_passport_number": "DUMMY-ID-200001",
                "paye_number": "DUMMY-PAYE-200001",
            }
        ]
    )

    masked = mask_sensitive_columns(df)

    assert masked.loc[0, "id_or_passport_number"] != "DUMMY-ID-200001"
    assert masked.loc[0, "paye_number"] != "DUMMY-PAYE-200001"


def test_month_number_accepts_names_abbreviations_and_numbers():
    assert month_number("February") == 2
    assert month_number("Feb") == 2
    assert month_number("2") == 2
    assert month_number(2) == 2


def test_output_folder_for_matches_generation_structure():
    path = output_folder_for("200001", 2026, 2)

    assert path.parts[-3:] == ("2026", "02", "200001")


def test_v2_output_folder_for_matches_generated_v2_structure():
    path = v2_output_folder_for("1008977", 2026, 4)

    assert path.parts[-4:] == ("generated_v2", "2026", "04", "1008977")


def test_ui_bank_detail_columns_do_not_exist():
    dev_reset()

    assert bank_detail_columns_exist() is False


def test_safe_sessions_display_df_removes_sensitive_session_columns():
    df = pd.DataFrame(
        [
            {
                "lecturer_name": "Demo Clean Lecturer",
                "staff_number": "200001",
                "highest_qualification": "Dummy Qualification",
                "id_or_passport_number": "DUMMY-ID-200001",
                "paye_number": "DUMMY-PAYE-200001",
                "physical_address": "P.O. Box 000",
                "contact_number": "0810000001",
                "group_name": "Demo Group A",
                "session_date": "2026-02-02",
                "start_time": "08:00",
                "end_time": "09:00",
                "hours": 1,
                "amount": 410,
            }
        ]
    )

    safe_df = safe_sessions_display_df(df)

    assert "id_or_passport_number" not in safe_df.columns
    assert "paye_number" not in safe_df.columns
    assert "physical_address" not in safe_df.columns
    assert "contact_number" not in safe_df.columns
    assert "highest_qualification" not in safe_df.columns
    assert "lecturer_name" not in safe_df.columns
    assert "staff_number" not in safe_df.columns
    for column in ("group_name", "session_date", "start_time", "end_time", "hours", "amount"):
        assert column in safe_df.columns


def test_safe_sessions_display_df_formats_session_date_as_iso_date():
    df = pd.DataFrame(
        [
            {
                "session_date": pd.Timestamp("2026-04-13"),
                "group_name": "ICT GREY",
                "start_time": "14:00",
                "end_time": "15:00",
                "hours": 1,
                "amount": 460,
            }
        ]
    )

    safe_df = safe_sessions_display_df(df)

    assert safe_df.loc[0, "session_date"] == "2026-04-13"
    assert format_session_date("2026-04-13") == "2026-04-13"


def test_lecturer_display_details_returns_full_name_and_staff_number():
    df = pd.DataFrame([{"lecturer_name": "Maria Matias", "staff_number": "1008977"}])

    details = lecturer_display_details(df)

    assert details == {"lecturer": "Maria Matias", "staff_number": "1008977"}


def test_lecturer_selector_helper_uses_runtime_database_provider():
    source = inspect.getsource(ui_helpers.lecturers_for_selector)

    assert "get_runtime_connection" in source
    assert "get_connection" not in source


def test_lecturer_option_label_uses_staff_number_and_name():
    assert lecturer_option_label({"staff_number": "1008977", "full_name": "Maria Matias"}) == "1008977 - Maria Matias"


def test_lecturer_record_by_staff_number_is_single_source_for_selection():
    records = [
        {"staff_number": "1001259", "full_name": "Mervin Nolin Shaun Mokhatu"},
        {"staff_number": "1009470", "full_name": "Alvina Niiro Hilifavali Hailonga"},
    ]

    selected = lecturer_record_by_staff_number(records, "1009470")

    assert selected["full_name"] == "Alvina Niiro Hilifavali Hailonga"
    assert lecturer_alias_from_full_name(selected["full_name"]) == "ALVINA"
    assert build_group_name("ALVINA", "GREEN_FT", "SEM1", 2026) == "ALVINA_GREEN_FT_SEM1_2026"


def test_course_and_group_option_labels_are_readable():
    course = {"course_code": "CUS411S", "course_name": "Computer User Skills"}
    group = {"course_code": "CUS411S", "group_name": "CUS GROUP A"}

    assert course_option_label(course) == "CUS411S - Computer User Skills"
    assert group_option_label(group) == "CUS411S - CUS GROUP A"


def test_build_group_name_formats_lecturer_scoped_names():
    assert build_group_name("Victoria", "Green FT", "SEM1", "2026") == "VICTORIA_GREEN_FT_SEM1_2026"
    assert build_group_name("ALVINA", "GREEN_FT", "SEM1", "2026") == "ALVINA_GREEN_FT_SEM1_2026"
    assert build_group_name("Matheus", "Lunch", "SEM1", "2026") == "MATHEUS_LUNCH_SEM1_2026"
    assert build_group_name("Mervin", "07BURP", "SEM1", "2026") == "MERVIN_07BURP_SEM1_2026"
    assert build_group_name(" Victoria ", " Green__FT ", " SEM1 ", "2026") == "VICTORIA_GREEN_FT_SEM1_2026"


def test_lecturer_alias_from_full_name_uses_first_meaningful_name():
    assert lecturer_alias_from_full_name("Alvina Niiro Hilifavali Hailonga") == "ALVINA"
    assert lecturer_alias_from_full_name("Mervin Nolin Shaun Mokhatu") == "MERVIN"
    assert lecturer_alias_from_full_name("Victoria Ndafapawa Haidula") == "VICTORIA"
    assert lecturer_alias_from_full_name("Maria Matias") == "MARIA"
    assert lecturer_alias_from_full_name("Elifas Mutomeka") == "ELIFAS"


def test_lecturer_alias_and_group_name_clean_special_characters_and_blanks():
    assert lecturer_alias_from_full_name("  Anne-Marie Example ") == "ANNEMARIE"
    assert lecturer_alias_from_full_name("") == ""
    assert build_group_name(" Anne-Marie ", " Green / FT ", " SEM 1 ", "2026") == "ANNE_MARIE_GREEN_FT_SEM_1_2026"
    assert build_group_name("", "", "", "") == ""


def test_remove_lecturer_group_stale_keys_removes_old_phase_keys_only():
    state = {
        "add_lecturer_group_lecturer_alias_readonly_1001259": "MERVIN",
        "add_lecturer_group_manual_group_name": "MERVIN_GREEN_FT_SEM1_2026",
        "phase_6_3_add_lecturer_group_staff_number": "1009470",
        "sessions_df": "keep",
    }

    removed = remove_lecturer_group_stale_keys(state)

    assert set(removed) == {
        "add_lecturer_group_lecturer_alias_readonly_1001259",
        "add_lecturer_group_manual_group_name",
    }
    assert state == {
        "phase_6_3_add_lecturer_group_staff_number": "1009470",
        "sessions_df": "keep",
    }
    assert lecturer_group_stale_keys(state) == []


def test_mask_sensitive_value_keeps_only_safe_prefix():
    assert mask_sensitive_value("94020500509") == "940205*****"
    assert mask_sensitive_value("07847076") == "0784****"


def test_upload_filename_validation_accepts_only_xlsx():
    assert is_supported_upload_filename("real_master_data.xlsx") is True
    assert is_supported_upload_filename("real_master_data.XLSX") is True
    for filename in ("real_master_data.csv", "real_master_data.docx", "real_master_data.pdf"):
        assert is_supported_upload_filename(filename) is False


def test_import_workflow_requires_passed_dry_run_and_confirmation():
    assert can_import_workbook(True, True) is True
    assert can_import_workbook(False, True) is False
    assert can_import_workbook(True, False) is False
    assert can_import_workbook(False, False) is False


def test_file_metadata_returns_path_size_and_modified_timestamp(tmp_path):
    output = tmp_path / "sessions.xlsx"
    output.write_bytes(b"dummy excel bytes")

    metadata = file_metadata(output)

    assert metadata["path"] == str(output)
    assert metadata["size"] == len(b"dummy excel bytes")
    assert isinstance(metadata["modified"], str)


def test_file_path_display_html_escapes_and_uses_readable_class():
    html = file_path_display_html(r"C:\Output\claim<demo>.docx", label="Claim DOCX")

    assert "pt-file-path" in html
    assert "Claim DOCX" in html
    assert "&lt;demo&gt;" in html


def test_output_file_display_html_includes_metadata():
    html = output_file_display_html(r"C:\Output\claim.docx", "Claim", "12 KB", "2026-05-12 10:00:00")

    assert "pt-file-path" in html
    assert "pt-file-path-meta" in html
    assert "12 KB" in html
    assert "2026-05-12 10:00:00" in html


def test_file_metadata_handles_missing_file_cleanly(tmp_path):
    with pytest.raises(FileNotFoundError, match="Output file was not found"):
        file_metadata(tmp_path / "missing.xlsx")


def test_get_file_metadata_returns_exists_false_for_missing_file(tmp_path):
    metadata = get_file_metadata(tmp_path / "missing.xlsx")

    assert metadata["exists"] is False
    assert metadata["path"].endswith("missing.xlsx")
    assert metadata["size_bytes"] is None
    assert metadata["size_display"] == ""
    assert metadata["modified_timestamp_display"] == ""


def test_get_file_metadata_returns_readable_size_and_timestamp(tmp_path):
    output = tmp_path / "verification_checklist.xlsx"
    output.write_bytes(b"x" * 2048)

    metadata = get_file_metadata(output)

    assert metadata["exists"] is True
    assert metadata["path"] == str(output)
    assert metadata["size_bytes"] == 2048
    assert metadata["size_display"] == "2.0 KB"
    assert isinstance(metadata["modified_timestamp_display"], str)
    assert len(metadata["modified_timestamp_display"]) == 19


def test_read_file_bytes_returns_bytes_for_existing_file(tmp_path):
    output = tmp_path / "sessions.xlsx"
    output.write_bytes(b"excel-content")

    assert read_file_bytes(output) == b"excel-content"


def test_read_file_bytes_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Download file was not found"):
        read_file_bytes(tmp_path / "missing.xlsx")


def test_create_registers_zip_creates_zip_with_register_files(tmp_path):
    register_a = tmp_path / "register_a.docx"
    register_b = tmp_path / "register_b.docx"
    register_a.write_bytes(b"register-a")
    register_b.write_bytes(b"register-b")
    zip_path = create_registers_zip([register_a, register_b], tmp_path / "registers.zip")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["register_a.docx", "register_b.docx"]


def test_missing_v2_manual_templates_detects_missing_paths(monkeypatch, tmp_path):
    missing_claim = tmp_path / "missing_claim.docx"
    existing_register = tmp_path / "manual_register.docx"
    existing_register.write_bytes(b"docx")
    monkeypatch.setattr("app_ui.ui_helpers.MANUAL_CLAIM_TEMPLATE_V2", missing_claim)
    monkeypatch.setattr("app_ui.ui_helpers.MANUAL_REGISTER_TEMPLATE_V2", existing_register)

    assert missing_v2_manual_templates() == [missing_claim]


def test_missing_v2_manual_templates_empty_when_current_templates_exist():
    assert MANUAL_CLAIM_TEMPLATE_V2.exists()
    assert MANUAL_REGISTER_TEMPLATE_V2.exists()
    assert missing_v2_manual_templates() == []


def test_export_status_payload_contains_path_size_and_timestamp(tmp_path):
    output = tmp_path / "sessions.xlsx"
    output.write_bytes(b"x" * 100)

    payload = export_status_payload(output)

    assert payload["exists"] is True
    assert payload["path"] == str(output)
    assert payload["size_bytes"] == 100
    assert payload["size_display"] == "100 bytes"
    assert len(payload["modified_timestamp_display"]) == 19


def test_export_status_payload_rejects_empty_file(tmp_path):
    output = tmp_path / "sessions.xlsx"
    output.write_bytes(b"")

    with pytest.raises(ValueError, match="output file is empty"):
        export_status_payload(output)


def test_download_label_is_readable():
    assert download_label("Download generated sessions", "C:/tmp/sessions.xlsx") == "Download generated sessions: sessions.xlsx"


def test_database_status_text_hides_postgres_url(monkeypatch):
    secret_url = "postgresql://user:secret-password@example/db"
    monkeypatch.setenv("DATABASE_URL", secret_url)
    monkeypatch.setenv("APP_ENV", "production")

    text = database_status_text()

    assert "PostgreSQL via DATABASE_URL" in text
    assert "Provider: postgresql" in text
    assert "Environment: production" in text
    assert secret_url not in text
    assert "secret-password" not in text


def test_database_status_text_shows_sqlite_path_when_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")

    text = database_status_text()

    assert "Provider: sqlite" in text
    assert ".db" in text


def test_ui_number_formatting_helpers():
    assert format_namibian_currency(43240) == "N$ 43,240.00"
    assert format_hours_value(94) == "94.00"


def test_grouped_sessions_summary_calculates_sessions_hours_and_amount():
    df = pd.DataFrame(
        [
            {"course_code": "CUS411S", "group_name": "Demo Group A", "session_date": "2026-02-02", "hours": 1, "amount": 410},
            {"course_code": "CUS411S", "group_name": "Demo Group A", "session_date": "2026-02-16", "hours": 1.5, "amount": 615},
            {"course_code": "CUS411S", "group_name": "Demo Group B", "session_date": "2026-02-03", "hours": 1, "amount": 410},
        ]
    )

    summary = grouped_sessions_summary_df(df)

    group_a = summary[summary["group_name"] == "Demo Group A"].iloc[0]
    assert group_a["sessions"] == 2
    assert group_a["hours"] == 2.5
    assert group_a["amount"] == "N$ 1,025.00"
