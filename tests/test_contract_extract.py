from __future__ import annotations

from app.data_extraction.contract_extract import parse_contract_text


DUMMY_CONTRACT_TEXT = """
Registration Number: 123456
Title: Ms
Full Name(s): Demo
Surname: Lecturer
Highest Qualification: Master of Dummy Systems
Identity/passport Number: DUMMY-ID-123456
Income Tax Number: DUMMY-PAYE-123456
Physical Address: P.O. Box 000, Windhoek
Telephone Number (Cell): 0810000000
Campus: Windhoek Main Campus
Agreement Period: 2026-02-01 to 2026-06-05
Faculty: Computing and Informatics
Department: Informatics
Course/s to be taught: CUS411S Computer User Skills and ICT521S Information Competence
Remuneration Rate: N$ 460 per hour
Bank Name: First National Bank
Account Number: 123456789
Branch Code: 000000
"""


def test_parse_contract_text_maps_dummy_staff_number_title_and_name():
    extraction = parse_contract_text(DUMMY_CONTRACT_TEXT, source_file="dummy.pdf")

    assert extraction.staff_number == "123456"
    assert extraction.title == "Ms"
    assert extraction.full_name == "Demo Lecturer"
    assert extraction.surname == "Lecturer"


def test_parse_contract_text_maps_qualification_contact_courses_and_dates():
    extraction = parse_contract_text(DUMMY_CONTRACT_TEXT)

    assert extraction.highest_qualification == "Master of Dummy Systems"
    assert extraction.contact_number == "0810000000"
    assert extraction.contract_start_date == "2026-02-01"
    assert extraction.contract_end_date == "2026-06-05"
    assert extraction.tariff_per_hour == "460"
    assert extraction.course_codes == ["CUS411S", "ICT521S"]


def test_parse_contract_text_detects_and_ignores_bank_details():
    extraction = parse_contract_text(DUMMY_CONTRACT_TEXT)
    extracted_values = " ".join(str(value) for value in extraction.__dict__.values()).lower()

    assert extraction.bank_details_detected is True
    assert "first national bank" not in extracted_values
    assert "123456789" not in extracted_values
    assert "branch code" not in extracted_values
