from __future__ import annotations

import argparse
from pathlib import Path

from docxtpl import DocxTemplate

from app.session_generator import generate_monthly_sessions
from app_docxtpl.context_builders import build_claim_context, generated_v2_directory
from app_docxtpl.create_v2_templates import CLAIM_TEMPLATE_V2
from app_docxtpl.manual_templates import prepare_manual_templates_for_render


def render_claim_v2(
    lecturer_id: int,
    year: int,
    month: int,
    template_path: Path = CLAIM_TEMPLATE_V2,
    prepare_templates: bool = True,
) -> Path:
    template_path = Path(template_path)
    if prepare_templates and template_path == CLAIM_TEMPLATE_V2:
        prepare_manual_templates_for_render(validate=True, force=True)
    sessions_df = generate_monthly_sessions(lecturer_id, year, month)
    if sessions_df.empty:
        raise ValueError("No generated sessions found for claim v2 rendering")
    context = build_claim_context(sessions_df, year, month)
    staff_number = context["staff_number"]
    output_dir = generated_v2_directory(year, month, staff_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"claim_form_v2_{staff_number}_{year}_{month:02d}.docx"
    if output_path.exists():
        output_path.unlink()
    doc = DocxTemplate(template_path)
    doc.render(context, autoescape=True)
    doc.save(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render experimental docxtpl claim form.")
    parser.add_argument("--lecturer-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--template", type=Path, default=CLAIM_TEMPLATE_V2)
    args = parser.parse_args()
    sessions_df = generate_monthly_sessions(args.lecturer_id, args.year, args.month)
    context = build_claim_context(sessions_df, args.year, args.month)
    output = render_claim_v2(args.lecturer_id, args.year, args.month, template_path=args.template)
    print(f"Template path used: {args.template}")
    print(f"Claim v2 output path: {output}")
    print(f"Total sessions: {len(sessions_df)}")
    print(f"Total hours: {context['total_hours']}")
    print(f"Total amount: {float(sessions_df['amount'].sum()):.2f}")
    print(f"Number of claim rows: {len(context['claim_rows'])}")


if __name__ == "__main__":
    main()
