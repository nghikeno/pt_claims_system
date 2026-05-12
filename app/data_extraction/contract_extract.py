from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.docx_utils import safe_filename_text


REAL_IMPORTS_DIR = Path("data") / "real_imports"
EXTRACTED_CONTRACTS_DIR = REAL_IMPORTS_DIR / "extracted_contracts"
BANK_MARKERS = (
    "bank",
    "account holder",
    "account number",
    "branch code",
    "swift",
    "first national bank",
    "fnb",
)


@dataclass
class ContractExtraction:
    staff_number: str = ""
    title: str = ""
    full_name: str = ""
    surname: str = ""
    highest_qualification: str = ""
    id_or_passport_number: str = ""
    paye_number: str = ""
    physical_address: str = ""
    contact_number: str = ""
    campus: str = ""
    contract_start_date: str = ""
    contract_end_date: str = ""
    course_codes: list[str] = field(default_factory=list)
    course_names: list[str] = field(default_factory=list)
    faculty: str = ""
    department: str = ""
    tariff_per_hour: str = ""
    active: str = "Yes"
    source_file: str = ""
    machine_readable_text_found: bool = True
    bank_details_detected: bool = False


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" :\t\r\n")


def _clean_label_noise(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^\(?s\)?\s*:?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\(?if applicable\)?\s*:?\s*", "", value, flags=re.IGNORECASE)
    return _clean(value)


def _title_case_if_upper(value: str) -> str:
    cleaned = _clean(value)
    return cleaned.title() if cleaned.isupper() else cleaned


def _line_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = rf"(?im)^\s*{re.escape(label)}\s*(?:\([^)]*\))?\s*:?\s*(.+?)\s*$"
        match = re.search(pattern, text)
        if match:
            value = _clean_label_noise(match.group(1))
            if not _contains_bank_marker(value):
                return value
    return ""


def _contains_bank_marker(text: str) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in BANK_MARKERS)


def _strip_bank_lines(text: str) -> tuple[str, bool]:
    kept = []
    detected = False
    for line in text.splitlines():
        if _contains_bank_marker(line):
            detected = True
            continue
        kept.append(line)
    return "\n".join(kept), detected


def _normalise_date(value: str) -> str:
    value = _clean(value)
    if not value:
        return ""
    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", value)
    if iso:
        return f"{iso.group(1)}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}"
    dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", value)
    if dmy:
        return f"{dmy.group(3)}-{int(dmy.group(2)):02d}-{int(dmy.group(1)):02d}"
    dmy_short = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2})\b", value)
    if dmy_short:
        return f"20{int(dmy_short.group(3)):02d}-{int(dmy_short.group(2)):02d}-{int(dmy_short.group(1)):02d}"
    return value


def _extract_period(text: str) -> tuple[str, str]:
    match = re.search(
        r"(?is)(?:agreement|contract)?\s*period\s*:?\s*_*\s*(.+?)_*[\s_]+(?:to|until|-)[\s_]+_*(.+?)_*?(?:\n|$)",
        text,
    )
    if not match:
        match = re.search(r"(?is)for\s+the\s+period\s*_*\s*(.+?)_*[\s_]+to[\s_]+_*(.+?)_*?(?:\n|$)", text)
    if match:
        return _normalise_date(match.group(1)), _normalise_date(match.group(2))
    start = _line_value(text, ("Contract Start Date", "Start Date", "From"))
    end = _line_value(text, ("Contract End Date", "End Date", "To"))
    return _normalise_date(start), _normalise_date(end)


def _extract_courses(text: str) -> tuple[list[str], list[str]]:
    text = _correct_course_variants(text)
    codes = []
    names = []
    for code in ("CUS411S", "ICT521S"):
        if re.search(rf"\b{code}\b", text, flags=re.IGNORECASE):
            codes.append(code)
    if re.search(r"computer user skills", text, flags=re.IGNORECASE):
        names.append("Computer User Skills")
        if "CUS411S" not in codes:
            codes.append("CUS411S")
    if re.search(r"information competence", text, flags=re.IGNORECASE):
        names.append("Information Competence")
        if "ICT521S" not in codes:
            codes.append("ICT521S")
    return sorted(set(codes)), sorted(set(names))


def _correct_course_variants(text: str) -> str:
    replacements = {
        "CUS4115": "CUS411S",
        "CUS411s": "CUS411S",
        "ICT5215": "ICT521S",
        "ICT5211S": "ICT521S",
    }
    corrected = text
    for old, new in replacements.items():
        corrected = re.sub(old, new, corrected, flags=re.IGNORECASE)
    corrected = re.sub(r"ICTS21S(?=.*Information Competence)", "ICT521S", corrected, flags=re.IGNORECASE | re.DOTALL)
    return corrected


def _extract_staff_number(text: str) -> str:
    labels = ("Registration Number", "Personnel Number", "Staff Number", "Employee Number")
    for label in labels:
        pattern = rf"(?im)^\s*{re.escape(label)}[^\n:]*:?\s*(.+)$"
        match = re.search(pattern, text)
        if match:
            number = re.search(r"\b(\d{6,8})\b", match.group(1))
            if number:
                return number.group(1)
    return ""


def _extract_title(text: str) -> str:
    title_lines = [line for line in text.splitlines() if re.search(r"\b(title|prof|dr|mr|ms)\b", line, re.IGNORECASE)]
    for line in title_lines:
        marked = re.search(r"\b(Prof|Dr|Mr|Ms)\b\s*(?:\[[ xX]\]|\(?[xX]\)?|\b[xX]\b)", line, re.IGNORECASE)
        if marked:
            return marked.group(1).title().replace("Ms", "Ms")
        marked_before = re.search(r"(?:\[[ xX]\]|\(?[xX]\)?|\b[xX]\b)\s*\b(Prof|Dr|Mr|Ms)\b", line, re.IGNORECASE)
        if marked_before:
            return marked_before.group(1).title().replace("Ms", "Ms")
    value = _line_value(text, ("Title",))
    if value:
        candidates = re.findall(r"\b(Prof|Dr|Mr|Ms)\b", value, flags=re.IGNORECASE)
        unique = {candidate.casefold(): candidate for candidate in candidates}
        if len(unique) == 1:
            return next(iter(unique.values())).title().replace("Ms", "Ms")
    return ""


def _clean_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", _clean(value))


def _extract_contact_number(text: str) -> str:
    contact_value = _line_value(text, ("Telephone Number(s)", "Telephone Number (Cell)", "Cell", "Tel", "Phone", "Contact Number"))
    search_area = contact_value or text
    mobile = re.search(r"\b(08[15][\s-]?\d{3}[\s-]?\d{4})\b", search_area)
    if mobile:
        return re.sub(r"\D", "", mobile.group(1))
    return ""


def _extract_qualification(text: str) -> str:
    value = _line_value(
        text,
        (
            "Highest Qualification",
            "Qualifications",
            "Qualification",
            "The employee has the following qualifications",
            "Relevant qualification",
        ),
    )
    value = re.sub(r"^\d+[\).]\s*", "", value)
    if not value:
        return ""
    parts = [part.strip(" ;,") for part in re.split(r"\s*(?:;|\n|\band\b)\s*", value) if part.strip(" ;,")]
    return "; ".join(parts[:3]) if len(parts) > 1 else value


def _extract_faculty(text: str) -> str:
    if re.search(r"Faculty\s+of\s+Computing\s+and\s+Informatics", text, re.IGNORECASE):
        return "Computing and Informatics"
    return _line_value(text, ("Faculty",))


def _extract_department(text: str) -> str:
    if re.search(r"(?:Department\s+of\s+Informatics|in\s+the\s+Department\s+of\s+Informatics)", text, re.IGNORECASE):
        return "Informatics"
    return _line_value(text, ("Department",))


def _extract_tariff(text: str) -> str:
    labels = ("Remuneration fee", "Specify remuneration fee", "Remuneration Rate", "Tariff per hour", "Rate per hour", "Hourly Rate")
    for label in labels:
        value = _line_value(text, (label,))
        if value and not re.search(r"handwritten|manual|unclear", value, re.IGNORECASE):
            match = re.search(r"(\d+(?:\.\d{1,2})?)", value)
            if match:
                return match.group(1)
    return ""


def parse_contract_text(text: str, source_file: str = "") -> ContractExtraction:
    corrected_text = _correct_course_variants(text)
    stripped_text, bank_detected = _strip_bank_lines(corrected_text)
    start_date, end_date = _extract_period(stripped_text)
    course_codes, course_names = _extract_courses(stripped_text)
    full_names = _line_value(stripped_text, ("Full Name(s)", "Full Names", "Full Name", "Names"))
    surname = _line_value(stripped_text, ("Surname", "Last Name"))
    surname = _title_case_if_upper(surname)
    full_names = _title_case_if_upper(full_names)
    full_name = _clean(f"{full_names} {surname}") if full_names and surname and surname.lower() not in full_names.lower() else full_names
    return ContractExtraction(
        staff_number=_extract_staff_number(stripped_text),
        title=_extract_title(stripped_text),
        full_name=full_name,
        surname=surname,
        highest_qualification=_extract_qualification(stripped_text),
        id_or_passport_number=_clean_identifier(_line_value(stripped_text, ("Identity/passport Number", "Identity / Passport Number", "ID Number", "Passport Number"))),
        paye_number=_clean_identifier(_line_value(stripped_text, ("Income Tax Number", "PAYE Number", "PAYE No."))),
        physical_address=_line_value(stripped_text, ("Physical Address", "Postal Address", "Address")),
        contact_number=_extract_contact_number(stripped_text),
        campus=_line_value(stripped_text, ("Campus",)),
        contract_start_date=start_date,
        contract_end_date=end_date,
        course_codes=course_codes,
        course_names=course_names,
        faculty=_extract_faculty(stripped_text),
        department=_extract_department(stripped_text),
        tariff_per_hour=_extract_tariff(stripped_text),
        active="Yes",
        source_file=source_file,
        machine_readable_text_found=bool(_clean(text)),
        bank_details_detected=bank_detected,
    )


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def extract_contract_file(path: str | Path) -> tuple[ContractExtraction, Path]:
    source = Path(path)
    text = extract_pdf_text(source)
    extraction = parse_contract_text(text, source_file=str(source))
    if not _clean(text):
        extraction.machine_readable_text_found = False
    output_dir = EXTRACTED_CONTRACTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_filename_text(source.stem)}.json"
    output_path.write_text(json.dumps(asdict(extraction), indent=2), encoding="utf-8")
    return extraction, output_path


def mask_sensitive(value: str) -> str:
    value = str(value or "")
    if len(value) <= 5:
        return "*" * len(value)
    return f"{value[:6]}*****"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract draft lecturer data from a local agreement PDF.")
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    extraction, output_path = extract_contract_file(args.file)
    if not extraction.machine_readable_text_found:
        print("No machine-readable text found. Manual review required.")
    if extraction.bank_details_detected:
        print("Bank details detected and ignored.")
    print(f"Extraction JSON: {output_path}")
    print(f"Staff number: {extraction.staff_number}")
    print(f"Title: {extraction.title}")
    print(f"Full name: {extraction.full_name}")
    if extraction.id_or_passport_number:
        print(f"ID/passport: {mask_sensitive(extraction.id_or_passport_number)}")
    if extraction.paye_number:
        print(f"PAYE: {mask_sensitive(extraction.paye_number)}")


if __name__ == "__main__":
    main()
