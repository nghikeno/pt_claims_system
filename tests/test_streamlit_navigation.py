from pathlib import Path
import re


def test_maria_pilot_helper_not_in_normal_streamlit_navigation():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "Maria Pilot Helper" not in source
    assert "Timetable Entry" in source
    assert "Student Upload" in source


def test_timetable_update_tab_exists():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "Update timetable entry" in source
    assert "Manage timetable entries" in source
    assert "DELETE TIMETABLE ENTRY" in source


def test_timetable_add_group_selection_is_scoped_to_selected_lecturer():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    timetable_page = source.split("def page_timetable_entry", 1)[1].split("def page_student_upload", 1)[0]

    assert "Selected lecturer:" in timetable_page
    assert "Selected group:" in timetable_page
    assert "Group lecturer:" in timetable_page
    assert 'key=f"phase_7_1_timetable_group_id_{selected_staff_number}"' in timetable_page
    assert "timetable_group_ownership_message" in timetable_page


def test_lecturer_navigation_hides_admin_pages():
    source = Path("app_ui/navigation.py").read_text(encoding="utf-8")

    assert "My Dashboard" in source
    assert "My Timetable/Sessions" in source
    assert "My Documents" in source
    assert "Change Password" in source
    lecturer_function = source.split("def lecturer_navigation_options", 1)[1]
    assert "Lecturer Entry" not in lecturer_function
    assert "Course and Group Entry" not in lecturer_function
    assert "Academic Calendar" not in lecturer_function
    assert "Pre-Claim Verification" not in lecturer_function
    assert "Student Upload" not in lecturer_function
    assert "Master Data Import" not in lecturer_function


def test_admin_navigation_includes_academic_calendar():
    source = Path("app_ui/navigation.py").read_text(encoding="utf-8")

    admin_function = source.split("def admin_navigation_options", 1)[1].split("def lecturer_navigation_options", 1)[0]
    assert "Academic Calendar" in admin_function
    assert "Pre-Claim Verification" in admin_function


def test_login_and_logout_are_present():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "def page_login" in source
    assert "Logout" in source
    assert "must_change_password" in source


def test_forced_password_change_sets_dashboard_notice_and_navigation_state():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "post_password_change_notice" in source
    assert "force_my_dashboard_after_password_change" in source
    assert 'st.session_state["lecturer_navigation"] = "My Dashboard"' in source
    assert "st.rerun()" in source
    assert "st.session_state.pop(\"post_password_change_notice\", None)" in source


def test_obsolete_dashboard_docx_warning_removed():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "DOCX claim/register formatting is still draft and under review." not in source


def test_academic_calendar_page_is_routed():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "def page_academic_calendar" in source
    assert 'section == "Academic Calendar"' in source
    assert "NUST 2026 reference" in source


def test_document_generation_wording_is_operational():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "Generate documents" in source
    assert "Generate draft documents" not in source
    assert "DOCX formatting is draft and under review" not in source
    assert "Generated documents should be reviewed before submission." in source
    assert "Advanced options" in source


def test_lecturer_documents_do_not_expose_engine_selector():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    lecturer_docs = source.split("def page_my_documents", 1)[1].split("def render_persistent_export_status", 1)[0]

    assert "Document engine" not in lecturer_docs
    assert "Generate my v2 documents" not in lecturer_docs
    assert "Generate documents" in lecturer_docs
    assert "recommended document engine is used automatically" in lecturer_docs


def test_document_generation_output_is_kept_in_session_state():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "document_output_state_key" in source
    assert "st.session_state[state_key]" in source
    assert "render_document_output_state" in source
    assert "generate_download_url" in source


def test_admin_and_lecturer_documents_use_shared_v2_generation_helper():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    lecturer_docs = source.split("def page_my_documents", 1)[1].split("def render_persistent_export_status", 1)[0]
    admin_docs = source.split("def page_document_generation", 1)[1].split("def page_maria_pilot", 1)[0]

    assert "def generate_v2_document_output_state" in source
    assert "generate_v2_document_output_state(" in lecturer_docs
    assert "generate_v2_document_output_state(" in admin_docs
    assert "include_verification_checklist=True" in admin_docs
    assert "include_verification_checklist=False" in lecturer_docs
    assert "render_documents_v2(" not in admin_docs


def test_admin_document_generation_has_component_safe_error_reporting():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    admin_docs = source.split("def page_document_generation", 1)[1].split("def page_maria_pilot", 1)[0]

    assert "DocumentGenerationComponentError" in source
    assert "failed during" in source
    assert "show_document_generation_error" in admin_docs


def test_account_management_reset_does_not_use_old_generic_failure_message():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    account_page = source.split("def page_account_management", 1)[1].split("def page_audit_log", 1)[0]

    assert '"Password reset failed."' not in account_page
    assert "safe_message" in account_page
    assert "reset_user_password" in account_page


def test_lecturer_staff_number_correction_is_separate_admin_panel():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    lecturer_entry = source.split("def page_lecturer_entry", 1)[1].split("def _course_form_fields", 1)[0]

    assert "Staff number cannot be changed in update mode" in lecturer_entry
    assert "Correct staff number" in source
    assert "CONFIRMATION_PHRASE" in source
    assert "correct_lecturer_staff_number" in source
    assert "Do not use it to replace one lecturer with another person." in source


def test_lecturer_update_form_keys_are_scoped_to_selected_record():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    lecturer_entry = source.split("def page_lecturer_entry", 1)[1].split("def _course_form_fields", 1)[0]

    assert "def _lecturer_update_identity" in source
    assert "Selected record:" in source
    assert 'with st.form(f"update_lecturer_form_{update_identity}")' in lecturer_entry
    assert '_lecturer_form_fields(f"update_{update_identity}", existing, staff_number_disabled=True)' in lecturer_entry
    assert 'key=f"correct_new_staff_{identity}"' in source
    assert 'key=f"correct_staff_confirmation_{identity}"' in source


def test_lecturer_update_mismatch_blocks_save_and_correction():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    lecturer_entry = source.split("def page_lecturer_entry", 1)[1].split("def _course_form_fields", 1)[0]
    correction_panel = source.split("def _render_staff_number_correction_panel", 1)[1].split("def page_lecturer_entry", 1)[0]

    assert "Selected lecturer and loaded form record do not match. Please reselect the lecturer." in source
    assert "submitted = st.form_submit_button(\"Update lecturer\", disabled=mismatch)" in lecturer_entry
    assert "submitted = st.form_submit_button(\"Correct staff number\", disabled=mismatch)" in correction_panel
    assert 'str(data.get("staff_number") or "").strip() != str(existing.get("staff_number") or "").strip()' in lecturer_entry


def test_view_as_lecturer_lookup_is_provider_aware():
    source = Path("app_ui/streamlit_app.py").read_text(encoding="utf-8")
    helper = source.split("def _lecturer_view_user_from_identifier", 1)[1].split("def _lecturer_view_user_from_staff_number", 1)[0]

    assert "get_runtime_connection" in helper
    assert "convert_placeholders" in helper
    assert "CAST(l.id AS TEXT)" in helper
