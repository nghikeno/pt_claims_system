from __future__ import annotations

from openpyxl import load_workbook

from app.data_extraction.ocr_contract_extract import (
    REVIEW_COLUMNS,
    create_review_workbook,
    parse_ocr_contract_text,
    review_notes_for_extraction,
)


DUMMY_OCR_TEXT = """
Registration Number: 654321
Title: Dr
Full Name(s): Dummy
Surname: Reviewer
Identity/passport Number: DUMMY-ID-654321
Telephone Number (Cell): 0811111111
Income Tax Number: 987654321
Qualifications: Doctor of Dummy Analytics
Course/s to be taught: CUS4115 Computer User Skills, ICT5211S Information Competence
Faculty: Computing and Informatics
Department: Informatics
Agreement Period: 2026/02/01 to 2026/06/05
Remuneration Rate: N$ 460 per hour
Bank Name: FNB
Account Number: 123456789
"""


def test_parse_ocr_contract_text_extracts_dummy_fields_and_course_variants():
    extraction = parse_ocr_contract_text(DUMMY_OCR_TEXT, "dummy.pdf")

    assert extraction.staff_number == "654321"
    assert extraction.title == "Dr"
    assert extraction.full_name == "Dummy Reviewer"
    assert extraction.contact_number == "0811111111"
    assert extraction.paye_number == "987654321"
    assert extraction.id_or_passport_number == "DUMMYID654321"
    assert extraction.highest_qualification == "Doctor of Dummy Analytics"
    assert extraction.course_codes == ["CUS411S", "ICT521S"]
    assert extraction.contract_start_date == "2026-02-01"
    assert extraction.contract_end_date == "2026-06-05"


def test_parse_ocr_contract_text_detects_bank_but_does_not_extract_values():
    extraction = parse_ocr_contract_text(DUMMY_OCR_TEXT)
    values = " ".join(str(value) for value in extraction.__dict__.values()).lower()

    assert extraction.bank_details_detected is True
    assert "123456789" not in values
    assert "fnb" not in values


def test_ocr_parser_cleans_staff_number_from_noisy_label():
    extraction = parse_ocr_contract_text("Registration Number (if applicable): 100751")

    assert extraction.staff_number == "100751"


def test_ocr_parser_extracts_ms_and_mr_from_title_checkbox_lines():
    assert parse_ocr_contract_text("Title: Prof Dr Mr Ms X").title == "Ms"
    assert parse_ocr_contract_text("Title: Prof Dr Mr X Ms").title == "Mr"


def test_ocr_parser_leaves_title_blank_when_uncertain():
    assert parse_ocr_contract_text("Title: Prof Dr Mr Ms").title == ""


def test_ocr_parser_cleans_surname_and_full_name_prefixes():
    extraction = parse_ocr_contract_text("Full Name(s): DUMMY NAME\nSurname: (s): SURNAME")

    assert extraction.full_name == "Dummy Name Surname"
    assert extraction.surname == "Surname"


def test_ocr_parser_extracts_department_faculty_period_and_blank_uncertain_tariff():
    text = """
    Faculty of Computing and Informatics
    In the Department of Informatics
    for the period __09/02/26__ to __30/11/26__
    Remuneration fee: handwritten
    """
    extraction = parse_ocr_contract_text(text)

    assert extraction.faculty == "Computing and Informatics"
    assert extraction.department == "Informatics"
    assert extraction.contract_start_date == "2026-02-09"
    assert extraction.contract_end_date == "2026-11-30"
    assert extraction.tariff_per_hour == ""


def test_ocr_review_notes_include_cleaning_and_manual_review_messages():
    text = "Registration Number (if applicable): 100751\nTitle: Prof Dr Mr Ms\nBank Name: FNB"
    extraction = parse_ocr_contract_text(text)
    notes = review_notes_for_extraction(extraction, text)

    assert "Staff number cleaned from noisy OCR label" in notes
    assert "Title uncertain" in notes
    assert "Bank details detected and ignored" in notes
    assert "Scanned OCR result requires manual review" in notes


def test_create_review_workbook_with_missing_ocr_dependencies_creates_blank_rows(monkeypatch, tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "dummy.pdf").write_bytes(b"%PDF scanned")
    output = tmp_path / "ocr_contract_review.xlsx"

    monkeypatch.setattr(
        "app.data_extraction.ocr_contract_extract.extract_text_with_ocr",
        lambda _path, _pages: ("", "OCR dependencies not available"),
    )
    result = create_review_workbook(contracts_dir, output)
    workbook = load_workbook(output)
    sheet = workbook["Contract_Review"]

    assert result["contracts_scanned"] == 1
    assert output.exists()
    assert [cell.value for cell in sheet[1]] == REVIEW_COLUMNS
    assert sheet["A2"].value == "dummy.pdf"
    assert sheet["B2"].value == "Manual review required"
    assert sheet["C2"].value == "Needs review"


def test_create_review_workbook_save_ocr_text_writes_sanitized_debug_text(monkeypatch, tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "dummy.pdf").write_bytes(b"%PDF scanned")
    output = tmp_path / "ocr_contract_review.xlsx"

    monkeypatch.setattr(
        "app.data_extraction.ocr_contract_extract.extract_text_with_ocr",
        lambda _path, _pages: ("Registration Number: 123456\nBank Name: FNB\nAccount Number: 111", "OCR completed"),
    )
    create_review_workbook(contracts_dir, output, save_ocr_text=True)
    debug_text = (tmp_path / "extracted_contracts" / "ocr_text" / "DUMMY.txt").read_text(encoding="utf-8")

    assert "Registration Number: 123456" in debug_text
    assert "FNB" not in debug_text
    assert "111" not in debug_text
