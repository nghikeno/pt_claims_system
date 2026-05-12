from app.template_inspector import inspect_template


def test_template_inspector_can_inspect_claim_template():
    analysis = inspect_template("data/docx_templates/golden_claim_template.docx")

    assert analysis["table_count"] >= 1
    assert any(label in analysis["labels_found"] for label in ["PARTICULARS OF CLAIM", "Claimant's Signature"])


def test_template_inspector_can_inspect_attendance_template():
    analysis = inspect_template("data/docx_templates/golden_attendance_register_template.docx")

    assert analysis["table_count"] >= 1
    assert "CLASS ATTENDANCE SHEET" in analysis["labels_found"]
    assert "COURSE CODE" in analysis["labels_found"]
