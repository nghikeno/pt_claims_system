from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from app.auth_service import authorize_lecturer_access
from app.document_storage import store_generated_document_set
from app.session_generator import generate_monthly_sessions
from app_docxtpl.context_builders import build_claim_context, generated_v2_directory
from app_docxtpl.create_v2_templates import CLAIM_TEMPLATE_V2
from app_docxtpl.manual_templates import extract_docx_text, prepare_manual_templates_for_render
from app_docxtpl.render_claim_v2 import render_claim_v2
from app_docxtpl.render_register_v2 import render_register_v2


def _write_provenance(
    output_dir,
    lecturer_id: int,
    year: int,
    month: int,
    template_info: dict,
    claim_path,
    register_paths: list,
    claim_template_path,
) -> str:
    provenance_path = output_dir / "render_provenance.txt"
    lines = [
        f"render timestamp: {datetime.now().isoformat(sep=' ', timespec='seconds')}",
        f"lecturer id/staff number: {lecturer_id}",
        f"year/month: {year}/{month:02d}",
        f"manual claim template path: {template_info['manual_claim_path']}",
        f"manual claim template SHA256: {template_info['manual_claim_hash']}",
        f"manual claim template modified time: {template_info['manual_claim_modified_time']}",
        f"render claim template path: {template_info['render_claim_path']}",
        f"render claim template SHA256: {template_info['render_claim_hash']}",
        f"manual register template path: {template_info['manual_register_path']}",
        f"manual register template SHA256: {template_info['manual_register_hash']}",
        f"manual register template modified time: {template_info['manual_register_modified_time']}",
        f"render register template path: {template_info['render_register_path']}",
        f"render register template SHA256: {template_info['render_register_hash']}",
        f"generated claim output path: {claim_path}",
        f"actual claim template used: {claim_template_path}",
        f"generated register folder path: {claim_path.parent / 'registers'}",
        f"number of register files: {len(register_paths)}",
    ]
    provenance_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(provenance_path)


def _print_debug_template_text(template_info: dict, claim_path, register_paths: list) -> None:
    print("DEBUG TEMPLATE TEXT: manual claim first 1000 chars")
    print(extract_docx_text(template_info["manual_claim_path"], limit=1000))
    print("DEBUG TEMPLATE TEXT: render claim copy first 1000 chars")
    print(extract_docx_text(template_info["render_claim_path"], limit=1000))
    print("DEBUG TEMPLATE TEXT: generated claim first 1000 chars")
    print(extract_docx_text(claim_path, limit=1000))
    print("DEBUG TEMPLATE TEXT: manual register first 1000 chars")
    print(extract_docx_text(template_info["manual_register_path"], limit=1000))
    print("DEBUG TEMPLATE TEXT: render register copy first 1000 chars")
    print(extract_docx_text(template_info["render_register_path"], limit=1000))
    if register_paths:
        print("DEBUG TEMPLATE TEXT: first generated register first 1000 chars")
        print(extract_docx_text(register_paths[0], limit=1000))


def render_documents_v2(
    lecturer_id: int,
    year: int,
    month: int,
    use_manual_templates: bool = True,
    debug_template_text: bool = False,
    claim_template: Path | None = None,
    current_user: dict | None = None,
) -> dict:
    if current_user is not None:
        lecturer_id = authorize_lecturer_access(current_user, lecturer_id)
    sessions_df = generate_monthly_sessions(lecturer_id, year, month)
    claim_context = build_claim_context(sessions_df, year, month)
    staff_number = claim_context["staff_number"]
    output_dir = generated_v2_directory(year, month, staff_number)
    if output_dir.exists():
        shutil.rmtree(output_dir)
        print(f"Deleted old output folder: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created output folder: {output_dir}")

    template_info = None
    if use_manual_templates:
        template_info = prepare_manual_templates_for_render(validate=True, force=True)
    claim_template_path = claim_template or (template_info["render_claim_path"] if template_info else CLAIM_TEMPLATE_V2)
    claim_path = render_claim_v2(
        lecturer_id, year, month, template_path=claim_template_path, prepare_templates=False
    )
    register_paths = render_register_v2(lecturer_id, year, month, prepare_templates=False)
    provenance_path = None
    if template_info:
        provenance_path = _write_provenance(
            output_dir, lecturer_id, year, month, template_info, claim_path, register_paths, claim_template_path
        )
        if debug_template_text:
            _print_debug_template_text(template_info, claim_path, register_paths)
    storage_results = store_generated_document_set(
        [claim_path, *register_paths],
        output_dir=output_dir,
        prefix=f"generated_v2/{year}/{month:02d}/{staff_number}",
    )
    return {
        "claim_path": claim_path,
        "register_paths": register_paths,
        "storage": storage_results,
        "total_sessions": len(sessions_df),
        "total_hours": claim_context["total_hours"],
        "total_amount": float(sessions_df["amount"].sum()),
        "template_info": template_info,
        "output_dir": output_dir,
        "provenance_path": provenance_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render experimental docxtpl claim and registers.")
    parser.add_argument("--lecturer-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--debug-template-text", action="store_true")
    parser.add_argument("--claim-template", type=Path)
    args = parser.parse_args()
    result = render_documents_v2(
        args.lecturer_id,
        args.year,
        args.month,
        debug_template_text=args.debug_template_text,
        claim_template=args.claim_template,
    )
    print("DOCX template v2 rendering completed.")
    if result.get("template_info"):
        info = result["template_info"]
        print("Manual template sources:")
        print(f"- Claim: {info['manual_paths']['claim']}")
        print(f"- Register: {info['manual_paths']['register']}")
        print("Manual template SHA256 before:")
        print(f"- Claim: {info['before']['claim']}")
        print(f"- Register: {info['before']['register']}")
        print("Manual template SHA256 after:")
        print(f"- Claim: {info['after']['claim']}")
        print(f"- Register: {info['after']['register']}")
        print("Render template SHA256:")
        print(f"- Claim: {info['render_claim_hash']}")
        print(f"- Register: {info['render_register_hash']}")
        print("Actual template paths used:")
        print(f"- Claim: {info['render_claim_path']}")
        print(f"- Register: {info['render_register_path']}")
    if result.get("provenance_path"):
        print(f"Render provenance: {result['provenance_path']}")
    print(f"Claim v2: {result['claim_path']}")
    print(f"Register v2 files: {len(result['register_paths'])}")
    for path in result["register_paths"]:
        print(f"- {path}")
    print(f"Total sessions: {result['total_sessions']}")
    print(f"Total hours: {result['total_hours']}")
    print(f"Total amount: {result['total_amount']:.2f}")


if __name__ == "__main__":
    main()
