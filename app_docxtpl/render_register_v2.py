from __future__ import annotations

import argparse
from pathlib import Path

from docxtpl import DocxTemplate

from app.docx_utils import safe_filename_text
from app.session_generator import generate_monthly_sessions
from app_docxtpl.context_builders import build_register_page_contexts, generated_v2_directory
from app_docxtpl.create_v2_templates import REGISTER_TEMPLATE_V2
from app_docxtpl.manual_templates import prepare_manual_templates_for_render


def register_output_path(context: dict, output_dir: Path, year: int, month: int) -> Path:
    return output_dir / (
        f"register_v2_{context['staff_number']}_{safe_filename_text(context['course_code'])}_"
        f"{safe_filename_text(context['group_name'])}_{year}_{month:02d}_p{context['page_number']}.docx"
    )


def render_register_v2(
    lecturer_id: int,
    year: int,
    month: int,
    template_path: Path = REGISTER_TEMPLATE_V2,
    prepare_templates: bool = True,
) -> list[Path]:
    if prepare_templates:
        prepare_manual_templates_for_render(validate=True, force=True)
    sessions_df = generate_monthly_sessions(lecturer_id, year, month)
    if sessions_df.empty:
        raise ValueError("No generated sessions found for register v2 rendering")
    contexts = build_register_page_contexts(sessions_df, year, month)
    staff_number = str(sessions_df["staff_number"].iloc[0])
    output_dir = generated_v2_directory(year, month, staff_number) / "registers"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for context in contexts:
        output_path = register_output_path(context, output_dir, year, month)
        doc = DocxTemplate(template_path)
        doc.render(context, autoescape=True)
        doc.save(output_path)
        outputs.append(output_path)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Render experimental docxtpl attendance registers.")
    parser.add_argument("--lecturer-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()
    outputs = render_register_v2(args.lecturer_id, args.year, args.month)
    output_folder = outputs[0].parent if outputs else ""
    print(f"Template path used: {REGISTER_TEMPLATE_V2}")
    print(f"Register files generated: {len(outputs)}")
    print(f"Output folder: {output_folder}")
    for path in outputs:
        print(f"- {path}")


if __name__ == "__main__":
    main()
