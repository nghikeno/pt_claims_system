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
    assert "v2 document engine is used automatically" in lecturer_docs
