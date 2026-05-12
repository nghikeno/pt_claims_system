import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path
import shutil

from app.attendance_register_generator import generate_attendance_register_pack as generate_layout_attendance_register_pack
from app.claim_form_generator import generate_claim_form as generate_layout_claim_form
from app.config import GENERATED_DIR
from app.database import get_connection
from app.docx_utils import format_currency, format_hours, format_month_year
from app.session_generator import generate_monthly_sessions
from app.template_claim_generator import CLAIM_TEMPLATE_PATH, generate_template_claim_form
from app.template_register_generator import ATTENDANCE_TEMPLATE_PATH, generate_template_attendance_register_pack
from app.validators import detect_clashes
from app.verification_report import generate_verification_checklist


def output_directory(year: int, month: int, staff_number: str) -> Path:
    return GENERATED_DIR / str(year) / f"{month:02d}" / str(staff_number)


def _delete_stale_docx(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
    except PermissionError as exc:
        raise PermissionError(
            f"Could not delete stale output file because it is open or locked: {path}. "
            "Close the DOCX file and rerun document generation."
        ) from exc


def _delete_stale_attendance_registers(out_dir: Path, staff_number: str, year: int, month: int) -> None:
    patterns = [
        f"attendance_registers_{staff_number}_{year}_{month:02d}.docx",
        f"attendance_register_{staff_number}_{year}_{month:02d}_*.docx",
    ]
    for pattern in patterns:
        for path in out_dir.glob(pattern):
            _delete_stale_docx(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def resolve_lecturer_id(lecturer_identifier: int) -> int:
    with get_connection() as conn:
        by_id = conn.execute(
            "SELECT id FROM lecturers WHERE id = ? AND active = 1",
            (lecturer_identifier,),
        ).fetchone()
        if by_id is not None:
            return int(by_id["id"])
        by_staff = conn.execute(
            "SELECT id FROM lecturers WHERE staff_number = ? AND active = 1",
            (str(lecturer_identifier),),
        ).fetchone()
        if by_staff is not None:
            return int(by_staff["id"])
    raise ValueError(f"No active lecturer found for id or staff number {lecturer_identifier}")


def generate_monthly_documents(
    lecturer_id: int,
    year: int,
    month: int,
    allow_clashes: bool = False,
    layout_mode: str = "template",
    strict_template: bool = True,
) -> dict[str, Path | bool]:
    if layout_mode not in {"template", "generated"}:
        raise ValueError("layout_mode must be 'template' or 'generated'")

    resolved_lecturer_id = resolve_lecturer_id(lecturer_id)
    sessions_df = generate_monthly_sessions(resolved_lecturer_id, year, month)
    clashes_df = detect_clashes(sessions_df)
    if sessions_df.empty:
        raise ValueError("No generated sessions found for the selected lecturer and month")

    staff_number = str(sessions_df["staff_number"].iloc[0])
    lecturer_name = str(sessions_df["lecturer_name"].iloc[0])
    out_dir = output_directory(year, month, staff_number)

    attendance_path = out_dir / f"attendance_registers_{staff_number}_{year}_{month:02d}.docx"
    claim_path = out_dir / f"claim_form_{staff_number}_{year}_{month:02d}.docx"
    verification_path = out_dir / f"verification_checklist_{staff_number}_{year}_{month:02d}.xlsx"

    has_clashes = not clashes_df.empty
    documents_generated = not has_clashes or allow_clashes
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = ""
    if has_clashes and not allow_clashes:
        notes = "Clashes detected. Attendance register and claim form were not generated."
        generate_verification_checklist(
            sessions_df,
            clashes_df,
            verification_path,
            year,
            month,
            documents_generated=False,
            generation_status="Blocked due to clashes",
            notes=notes,
        )
        return {
            "documents_generated": False,
            "clashes_detected": True,
            "lecturer_name": lecturer_name,
            "staff_number": staff_number,
            "month_year": format_month_year(year, month),
            "sessions_generated": len(sessions_df),
            "total_hours": float(sessions_df["hours"].sum()),
            "total_amount": float(sessions_df["amount"].sum()),
            "clashes_count": len(clashes_df),
            "output_folder": out_dir,
            "verification_path": verification_path,
            "attendance_path": attendance_path,
            "attendance_paths": [],
            "claim_path": claim_path,
            "layout_mode": layout_mode,
        }

    warning = has_clashes and allow_clashes
    if warning:
        notes = "Documents generated as draft only because clashes were detected."
        generation_status = "Draft generated with clashes"
    else:
        generation_status = "Generated"
    if layout_mode == "template":
        golden_hashes_before = {
            "claim": _sha256(Path(CLAIM_TEMPLATE_PATH)),
            "attendance": _sha256(Path(ATTENDANCE_TEMPLATE_PATH)),
        }
        attendance_paths = generate_template_attendance_register_pack(
            sessions_df,
            attendance_path,
            year,
            month,
            warning=warning,
            strict=strict_template,
        )
        generate_template_claim_form(
            sessions_df,
            claim_path,
            year,
            month,
            warning=warning,
            strict=strict_template,
        )
        golden_hashes_after = {
            "claim": _sha256(Path(CLAIM_TEMPLATE_PATH)),
            "attendance": _sha256(Path(ATTENDANCE_TEMPLATE_PATH)),
        }
        if golden_hashes_before != golden_hashes_after:
            raise RuntimeError("Golden template hash changed during document generation. Generation failed.")
    else:
        golden_hashes_before = {}
        golden_hashes_after = {}
        attendance_paths = [attendance_path]
        generate_layout_attendance_register_pack(sessions_df, attendance_path, year, month, warning=warning)
        generate_layout_claim_form(sessions_df, claim_path, year, month, warning=warning)
    generate_verification_checklist(
        sessions_df,
        clashes_df,
        verification_path,
        year,
        month,
        documents_generated=True,
        generation_status=generation_status,
        notes=notes,
    )
    return {
        "documents_generated": True,
        "clashes_detected": has_clashes,
        "lecturer_name": lecturer_name,
        "staff_number": staff_number,
        "month_year": format_month_year(year, month),
        "sessions_generated": len(sessions_df),
        "total_hours": float(sessions_df["hours"].sum()),
        "total_amount": float(sessions_df["amount"].sum()),
        "clashes_count": len(clashes_df),
        "output_folder": out_dir,
        "verification_path": verification_path,
        "attendance_path": attendance_path,
        "attendance_paths": attendance_paths,
        "claim_path": claim_path,
        "layout_mode": layout_mode,
        "golden_template_hashes_before": golden_hashes_before,
        "golden_template_hashes_after": golden_hashes_after,
    }


def print_generation_summary(result: dict[str, Path | bool | str | float | int]) -> None:
    print(f"Lecturer name: {result['lecturer_name']}")
    print(f"Staff number: {result['staff_number']}")
    print(f"Month/year: {result['month_year']}")
    print(f"Sessions generated: {result['sessions_generated']}")
    print(f"Total hours: {format_hours(result['total_hours'])}")
    print(f"Total amount: {format_currency(result['total_amount'])}")
    print(f"Clashes detected: {result['clashes_count']}")
    print(f"Output folder: {result['output_folder']}")
    if "layout_mode" in result:
        print(f"Layout mode: {result['layout_mode']}")
    if result.get("golden_template_hashes_before"):
        print("Golden template SHA256 before generation:")
        print(f"- Claim: {result['golden_template_hashes_before']['claim']}")
        print(f"- Attendance: {result['golden_template_hashes_before']['attendance']}")
        print("Golden template SHA256 after generation:")
        print(f"- Claim: {result['golden_template_hashes_after']['claim']}")
        print(f"- Attendance: {result['golden_template_hashes_after']['attendance']}")


def _print_file_details(path: Path) -> None:
    stat = path.stat()
    print(f"  Path: {path}")
    print(f"  Modified: {datetime.fromtimestamp(stat.st_mtime).isoformat(sep=' ', timespec='seconds')}")
    print(f"  Size: {stat.st_size} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly DOCX documents and verification checklist.")
    parser.add_argument("--lecturer-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--allow-clashes", action="store_true")
    parser.add_argument("--layout-mode", choices=["template", "generated"], default="template")
    parser.add_argument("--strict-template", action="store_true", help="Use strict in-place DOCX template filling.")
    args = parser.parse_args()

    try:
        result = generate_monthly_documents(
            args.lecturer_id,
            args.year,
            args.month,
            args.allow_clashes,
            layout_mode=args.layout_mode,
            strict_template=True if args.layout_mode == "template" else args.strict_template,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print_generation_summary(result)
    print("Generated files:")
    print(f"- Verification checklist: {result['verification_path']}")
    if Path(result["verification_path"]).exists():
        _print_file_details(Path(result["verification_path"]))
    if result["documents_generated"]:
        attendance_paths = result.get("attendance_paths") or [result["attendance_path"]]
        print("- Attendance registers:")
        for attendance_path in attendance_paths:
            _print_file_details(Path(attendance_path))
        print(f"- Claim form: {result['claim_path']}")
        _print_file_details(Path(result["claim_path"]))
        if result["clashes_detected"]:
            print("Clashes detected. Documents generated with draft warning because --allow-clashes was provided.")
        sys.exit(0)

    print("Documents blocked: attendance register pack and claim form were not generated.")
    print("Reason: timetable clashes were detected for the selected lecturer and month.")
    print("Fix timetable clashes, or rerun with --allow-clashes for draft review only.")
    sys.exit(1)


if __name__ == "__main__":
    main()
