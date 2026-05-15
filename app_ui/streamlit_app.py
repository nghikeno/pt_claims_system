from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.auth_service import (
    authenticate_user,
    change_password,
    count_admin_accounts,
    lecturer_scoped_staff_number,
)
from app.account_admin_service import (
    create_lecturer_account_for_lecturer,
    list_lecturers_without_accounts,
    list_user_accounts,
    reset_user_password,
)
from app.academic_calendar_service import (
    CALENDAR_TYPES,
    SCOPE_TYPES,
    calendar_summary_counts,
    create_calendar_entry_result,
    get_calendar_entry,
    list_calendar_entries,
    reference_calendar_df,
    set_calendar_entry_active_result,
    update_calendar_entry_result,
)
from app.audit_service import list_audit_events, log_audit_event
from app.backup_database import backup_database
from app.config import (
    EXPORTS_DIR,
    enable_debug_stack_traces,
    enable_development_page,
    generated_file_mode_warning,
    get_app_env,
    is_production,
    is_training,
    session_timeout_minutes,
)
from app.claim_period_service import resolve_claim_period
from app.claim_completeness_service import audit_claim_completeness_from_data
from app.course_group_service import (
    course_exists,
    create_course,
    create_group,
    create_lecturer_group,
    find_duplicate_groups,
    find_duplicate_lecturer_groups,
    get_course_by_code,
    get_group,
    group_exists,
    lecturer_group_exists,
    list_courses,
    list_groups_for_lecturer,
    list_groups,
    list_lecturer_groups,
    update_course,
    update_group,
    update_lecturer_group,
    validate_course_data,
    validate_group_data,
    validate_lecturer_group_data,
)
from app.create_maria_pilot_workbook import (
    EXPECTED_AMOUNT,
    EXPECTED_HOURS,
    EXPECTED_SESSIONS,
    create_maria_pilot_workbook,
)
from app.db_provider import convert_placeholders, get_runtime_connection, init_runtime_db, row_to_dict
from app.dev_reset import dev_reset
from app.document_generator import generate_monthly_documents
from app.document_storage import document_storage_status, generate_download_url, save_generated_file, storage_key_for_generated_file
from app.export_excel import export_sessions_to_excel
from app.import_master_data import import_master_data, read_workbook
from app.data_validation import validate_workbook
from app.inspect_data import calendar_df, groups_df, lecturers_df, timetable_df
from app.lecturer_service import (
    create_lecturer,
    export_lecturers_to_csv,
    find_duplicate_lecturers,
    get_lecturer_by_staff_number,
    lecturer_exists,
    list_lecturers,
    update_lecturer,
    validate_lecturer_data,
)
from app.lecturer_staff_number_service import CONFIRMATION_PHRASE, correct_lecturer_staff_number
from app.master_data_template import generate_master_data_template
from app.performance_queries import lecturer_dashboard_counts
from app.preclaim_verification_service import (
    build_preclaim_verification,
    export_preclaim_verification_report,
)
from app.session_generator import generate_monthly_sessions
from app.student_service import (
    deactivate_enrolment,
    export_student_enrolments_to_csv,
    import_student_template_file,
    import_students_for_group,
    list_student_enrolments,
    reactivate_enrolment,
    validate_student_import,
)
from app.student_word_import import parse_attendance_docx
from app.timetable_service import (
    create_timetable_entry,
    deactivate_timetable_entry,
    delete_timetable_entry,
    hard_delete_confirmation_valid,
    list_groups_for_timetable,
    list_timetable_entries,
    reactivate_timetable_entry,
    timetable_group_ownership_message,
    update_timetable_entry,
    validate_timetable_entry,
)
from app.validators import detect_clashes
from app.verification_report import generate_verification_checklist, get_excluded_date_details
from app_docxtpl.context_builders import build_claim_context
from app_docxtpl.render_documents_v2 import render_documents_v2
from app_ui.ui_helpers import (
    can_import_workbook,
    build_group_name,
    course_option_label,
    create_registers_zip,
    dashboard_counts,
    database_status_text,
    export_status_payload,
    format_import_summary,
    format_hours_value,
    format_namibian_currency,
    get_file_metadata,
    grouped_sessions_summary_df,
    group_option_label,
    is_supported_upload_filename,
    lecturer_alias_from_full_name,
    lecturer_display_details,
    lecturer_option_label,
    lecturer_record_by_staff_number,
    lecturers_for_selector,
    mask_sensitive_columns,
    mask_sensitive_value,
    missing_v2_manual_templates,
    month_number,
    month_options,
    output_file_display_html,
    output_folder_for,
    file_path_display_html,
    read_file_bytes,
    remove_lecturer_group_stale_keys,
    safe_sessions_display_df,
    save_uploaded_workbook,
    table_df,
    timetable_time_options,
    v2_output_folder_for,
)
from app_ui.theme import apply_app_theme, render_app_header, render_login_header, render_sidebar_user, render_status_badge, render_training_banner
from app_ui.session_security import (
    clear_sensitive_session_state,
    effective_user,
    enter_view_as_lecturer,
    exit_view_as_lecturer,
    session_expired,
)
from app_ui.navigation import admin_navigation_options, lecturer_navigation_options


st.set_page_config(
    page_title="PT Claims System",
    page_icon="NUST",
    layout="wide",
)


def show_error(message: str, exc: Exception | None = None) -> None:
    st.error(message)
    if exc is not None and st.session_state.get("debug_errors", False):
        st.code("".join(traceback.format_exception(exc)), language="text")


def render_path_block(label: str, path: str | Path) -> None:
    st.markdown(file_path_display_html(path, label), unsafe_allow_html=True)


def render_output_file(label: str, path: str | Path) -> None:
    metadata = get_file_metadata(path)
    st.markdown(
        output_file_display_html(
            metadata["path"],
            label,
            str(metadata.get("size_display") or ""),
            str(metadata.get("modified_timestamp_display") or ""),
        ),
        unsafe_allow_html=True,
    )


def render_document_storage_summary(storage_rows: list[dict] | None) -> None:
    status = document_storage_status()
    if status.mode == "local":
        return
    st.subheader("Document storage")
    st.caption(f"Storage mode: {status.mode}. Durable storage: {'yes' if status.durable else 'no'}.")
    if storage_rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "file": Path(row.get("local_path", "")).name,
                        "mode": row.get("mode"),
                        "object_key": row.get("storage_key"),
                        "uploaded": row.get("uploaded"),
                    }
                    for row in storage_rows
                ]
            ),
            width="stretch",
        )
        if status.mode == "object_storage":
            st.caption("Object-storage download links expire after 15 minutes.")
            for row in storage_rows:
                key = str(row.get("storage_key") or "")
                name = Path(str(row.get("local_path") or key)).name
                if not key:
                    continue
                try:
                    url = generate_download_url(key, expires_in_seconds=900)
                except Exception as exc:
                    show_error(f"Could not prepare object-storage download link for {name}.", exc)
                    continue
                if url:
                    st.link_button(f"Download {name}", url, width="stretch")


def document_output_state_key(page_name: str, staff_number: str, year: int, month: int) -> str:
    user = current_user() or {}
    actual = actual_user() or {}
    view_state = "view-as" if is_viewing_as_lecturer() else "normal"
    username = str(actual.get("username") or user.get("username") or "anonymous")
    return f"document_output::{page_name}::{username}::{view_state}::{staff_number}::{int(year)}::{int(month):02d}"


def build_document_output_state(
    result: dict,
    staff_number: str,
    year: int,
    month: int,
    storage_rows: list[dict] | None = None,
    zip_path: str | Path | None = None,
    verification_path: str | Path | None = None,
    claim_audit: dict | None = None,
) -> dict:
    return {
        "staff_number": str(staff_number),
        "year": int(year),
        "month": int(month),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(result.get("output_dir") or ""),
        "claim_path": str(result.get("claim_path") or ""),
        "register_paths": [str(path) for path in result.get("register_paths", [])],
        "zip_path": str(zip_path or ""),
        "verification_path": str(verification_path or ""),
        "storage": list(storage_rows or result.get("storage", [])),
        "claim_audit": claim_audit or {},
    }


class DocumentGenerationComponentError(RuntimeError):
    def __init__(self, component: str, original: Exception) -> None:
        self.component = component
        self.original = original
        super().__init__(f"{component}: {type(original).__name__}: {original}")


def _safe_error_text(exc: Exception) -> str:
    text = str(exc)
    replacements = ["DATABASE_URL", "OBJECT_STORAGE_ACCESS_KEY_ID", "OBJECT_STORAGE_SECRET_ACCESS_KEY"]
    for item in replacements:
        text = text.replace(item, "[redacted]")
    if "://" in text and "s3://" not in text:
        return f"{type(exc).__name__}: connection/configuration detail redacted"
    return f"{type(exc).__name__}: {text}"


def _generation_step(component: str, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        print(f"DOCUMENT_GENERATION_ERROR component={component} detail={_safe_error_text(exc)}")
        raise DocumentGenerationComponentError(component, exc) from exc


def generate_v2_document_output_state(
    lecturer_identifier: int | str,
    year: int,
    month: int,
    *,
    current_user_for_render: dict | None = None,
    audit_user: dict | None = None,
    include_verification_checklist: bool = False,
) -> dict:
    result = _generation_step(
        "v2 document render",
        render_documents_v2,
        int(lecturer_identifier),
        int(year),
        int(month),
        current_user=current_user_for_render,
    )
    sessions_df = _generation_step("session reload", generate_monthly_sessions, int(lecturer_identifier), int(year), int(month))
    if sessions_df.empty:
        raise DocumentGenerationComponentError("session reload", ValueError("No generated sessions found."))
    staff_number = str(sessions_df["staff_number"].iloc[0])
    claim_audit = _generation_step(
        "claim completeness audit",
        audit_claim_completeness_from_data,
        sessions_df,
        build_claim_context(sessions_df, int(year), int(month)),
    )
    output_folder = Path(result["output_dir"])
    zip_path = _generation_step(
        "register ZIP creation",
        create_registers_zip,
        result["register_paths"],
        output_folder / f"registers_{staff_number}_{int(year)}_{int(month):02d}.zip",
    )
    storage_rows = list(result.get("storage", []))
    zip_storage = _generation_step(
        "storage upload",
        save_generated_file,
        zip_path,
        f"generated_v2/{int(year)}/{int(month):02d}/{staff_number}/{storage_key_for_generated_file(zip_path, output_folder)}",
    ).as_dict()
    storage_rows.append(zip_storage)
    verification_path = None
    if include_verification_checklist:
        clashes_df = _generation_step("clash detection", detect_clashes, sessions_df)
        verification_path = output_folder / f"verification_checklist_{staff_number}_{int(year)}_{int(month):02d}.xlsx"
        _generation_step(
            "verification checklist",
            generate_verification_checklist,
            sessions_df,
            clashes_df,
            verification_path,
            int(year),
            int(month),
            True,
            "Generated with v2 docxtpl",
            "Verification checklist generated from Streamlit v2 docxtpl workflow.",
        )
        checklist_storage = _generation_step(
            "storage upload",
            save_generated_file,
            verification_path,
            f"generated_v2/{int(year)}/{int(month):02d}/{staff_number}/{storage_key_for_generated_file(verification_path, output_folder)}",
        ).as_dict()
        storage_rows.append(checklist_storage)
    log_audit_event(
        "document_generation",
        user=audit_user,
        entity_type="lecturer",
        entity_id=staff_number,
        details={"year": int(year), "month": int(month), "engine": "v2"},
    )
    return build_document_output_state(
        result,
        staff_number,
        int(year),
        int(month),
        storage_rows=storage_rows,
        zip_path=zip_path,
        verification_path=verification_path,
        claim_audit=claim_audit,
    )


def show_document_generation_error(prefix: str, exc: Exception) -> None:
    if isinstance(exc, DocumentGenerationComponentError):
        st.error(f"{prefix} failed during {exc.component}.")
        if st.session_state.get("debug_errors", False):
            st.code(_safe_error_text(exc.original), language="text")
        return
    show_error(prefix + " failed.", exc)


def render_claim_completeness_audit(audit: dict | None) -> None:
    if not audit:
        return
    st.subheader("Claim completeness")
    status = audit.get("status", "PASS")
    if status == "PASS":
        st.success("All generated-session course/group pairs are represented in the claim context.")
    else:
        st.warning("Review claim completeness before submission.")
    missing = audit.get("missing_pairs") or []
    extra = audit.get("extra_pairs") or []
    if missing:
        st.error("Missing course/group pairs in claim context.")
        st.dataframe(pd.DataFrame(missing), width="stretch")
    if extra:
        st.warning("Extra course/group pairs found in claim context.")
        st.dataframe(pd.DataFrame(extra), width="stretch")
    with st.expander("Claim completeness details"):
        st.write("Expected course/group pairs")
        st.dataframe(pd.DataFrame(audit.get("expected_pairs") or []), width="stretch")
        st.write("Totals by course")
        st.dataframe(pd.DataFrame(audit.get("totals_by_course") or []), width="stretch")
        st.write("Totals by course and group")
        st.dataframe(pd.DataFrame(audit.get("totals_by_group") or []), width="stretch")


def render_document_output_state(state: dict, owner_label: str = "") -> None:
    storage_status = document_storage_status()
    if owner_label:
        st.caption(owner_label)
    created_at = state.get("created_at")
    if created_at:
        st.caption(f"Generated at: {created_at}")
    if storage_status.mode == "local":
        render_path_block("Output folder", state.get("output_dir", ""))
    else:
        st.caption("Generated files are stored through the configured document-storage mode; local server paths are not the durable reference.")

    claim_value = str(state.get("claim_path") or "")
    claim_path = Path(claim_value)
    st.subheader("Claim DOCX")
    if storage_status.mode == "local":
        render_file_metadata(claim_path)
        render_download_button("Download claim DOCX", claim_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    else:
        st.write(Path(str(state.get("claim_path") or "claim.docx")).name)

    register_paths = [Path(str(path)) for path in state.get("register_paths", [])]
    st.subheader("Attendance registers")
    st.write(f"Number of register files: {len(register_paths)}")
    if register_paths:
        st.dataframe(pd.DataFrame([{"register_file": path.name} for path in register_paths]), width="stretch")

    zip_value = str(state.get("zip_path") or "")
    zip_path = Path(zip_value)
    if zip_value:
        st.subheader("Registers ZIP")
        if storage_status.mode == "local":
            render_file_metadata(zip_path)
            render_download_button("Download all registers ZIP", zip_path, "application/zip")
        else:
            st.write(zip_path.name)

    verification_value = str(state.get("verification_path") or "")
    verification_path = Path(verification_value)
    if verification_value:
        st.subheader("Verification checklist")
        if storage_status.mode == "local":
            render_file_metadata(verification_path)
            render_download_button(
                "Download verification checklist Excel",
                verification_path,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.write(verification_path.name)

    render_document_storage_summary(state.get("storage") or [])
    render_claim_completeness_audit(state.get("claim_audit"))


@st.cache_data(ttl=60, show_spinner=False)
def cached_admin_dashboard_counts() -> dict[str, int]:
    return dashboard_counts()


@st.cache_data(ttl=60, show_spinner=False)
def cached_lecturer_dashboard_counts(staff_number: str) -> dict[str, int]:
    return lecturer_dashboard_counts(staff_number)


def current_user() -> dict | None:
    return effective_user(st.session_state)


def actual_user() -> dict | None:
    return st.session_state.get("auth_user")


def is_viewing_as_lecturer() -> bool:
    return "view_as_lecturer_user" in st.session_state


def _lecturer_view_user_from_identifier(identifier: str | int) -> dict | None:
    cleaned_identifier = str(identifier).strip()
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("""
            SELECT l.id AS lecturer_id, l.staff_number, l.full_name
            FROM lecturers AS l
            WHERE (l.staff_number = ? OR CAST(l.id AS TEXT) = ?) AND l.active = 1
            """),
            (cleaned_identifier, cleaned_identifier),
        ).fetchone()
    row = row_to_dict(row)
    if row is None:
        return None
    return {
        "id": None,
        "username": f"view-as:{row['staff_number']}",
        "role": "lecturer",
        "lecturer_id": int(row["lecturer_id"]),
        "staff_number": str(row["staff_number"]),
        "lecturer_name": str(row["full_name"]),
        "must_change_password": False,
        "active": True,
        "view_as": True,
    }


def _lecturer_view_user_from_staff_number(staff_number: str) -> dict | None:
    return _lecturer_view_user_from_identifier(staff_number)


def _staff_number_for_lecturer_id(lecturer_id: int) -> str | None:
    with get_runtime_connection() as conn:
        row = conn.execute(
            convert_placeholders("SELECT staff_number FROM lecturers WHERE id = ?"),
            (int(lecturer_id),),
        ).fetchone()
    row = row_to_dict(row)
    return str(row["staff_number"]) if row else None


def page_login() -> None:
    render_login_header()
    render_app_header("Login", "Enter your staff number or admin username to continue.")
    if count_admin_accounts() == 0:
        st.info('No admin account exists yet. Create one with: python -m app.auth_create_admin --username admin --password "<chosen_password>" --yes')
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        user = authenticate_user(username, password)
        if user is None:
            st.error("Invalid username or password.")
            return
        st.session_state["auth_user"] = user
        st.session_state["last_activity_at"] = datetime.now()
        st.rerun()


def page_change_password() -> None:
    user = current_user()
    if not user:
        page_login()
        return
    render_app_header("Change Password", "Choose a secure password before continuing.")
    if user.get("must_change_password"):
        st.warning("You must change your password before accessing the system.")
    with st.form("change_password_form"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Change password")
    if submitted:
        try:
            forced_change = bool(user.get("must_change_password"))
            st.session_state["auth_user"] = change_password(user["username"], current, new, confirm)
            st.session_state["post_password_change_notice"] = "Password successfully changed."
            if forced_change:
                st.session_state["lecturer_navigation"] = "My Dashboard"
                st.session_state["force_my_dashboard_after_password_change"] = True
                st.rerun()
            st.success("Password successfully changed.")
        except Exception as exc:
            show_error("Password change failed.", exc)


def page_my_dashboard() -> None:
    user = current_user()
    staff_number = lecturer_scoped_staff_number(user)
    render_app_header("My Dashboard", "Your lecturer profile, timetable, and enrolment overview.", badge="Lecturer")
    notice = st.session_state.pop("post_password_change_notice", None)
    if notice:
        st.success(notice)
    st.write(f"Logged in as: `{user['username']}`")
    st.write(f"Lecturer: `{user.get('lecturer_name', '')}`")
    if "Demo/Training" in str(user.get("lecturer_name", "")):
        st.info("Demo/Training lecturer account.")
    counts = cached_lecturer_dashboard_counts(staff_number)
    col1, col2, col3 = st.columns(3)
    col1.metric("Groups", counts.get("groups", 0))
    col2.metric("Timetable entries", counts.get("timetable entries", 0))
    col3.metric("Active enrolments", counts.get("active enrolments", 0))


def page_my_timetable_sessions() -> None:
    user = current_user()
    staff_number = lecturer_scoped_staff_number(user)
    render_app_header("My Timetable/Sessions", "Read-only view of your groups, timetable, and generated sessions.", badge="Lecturer")
    st.subheader("My groups")
    st.dataframe(list_groups_for_timetable(staff_number), width="stretch")
    st.subheader("My timetable")
    st.dataframe(list_timetable_entries(staff_number=staff_number), width="stretch")
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", min_value=2020, max_value=2100, value=2026, step=1, key="my_sessions_year")
    month_label = col2.selectbox("Month", [name for _, name in month_options()], index=1, key="my_sessions_month")
    claim_period = resolve_claim_period(int(year), month_number(month_label))
    st.caption(f"Claim/register period for {claim_period.label}: {claim_period.display}")
    if st.button("Generate my claimable teaching sessions"):
        sessions_df = generate_monthly_sessions(int(staff_number), int(year), month_number(month_label))
        st.dataframe(safe_sessions_display_df(sessions_df), width="stretch")
        st.write(f"Total sessions: {len(sessions_df)}")
        st.write(f"Total hours: {format_hours_value(float(sessions_df['hours'].sum()) if not sessions_df.empty else 0)}")
        st.write(f"Total amount: {format_namibian_currency(float(sessions_df['amount'].sum()) if not sessions_df.empty else 0)}")


def page_my_documents() -> None:
    user = current_user()
    staff_number = lecturer_scoped_staff_number(user)
    render_app_header("My Documents", "Generate and download your own claim and attendance registers.", badge="Lecturer")
    warning = generated_file_mode_warning()
    if warning:
        st.warning(warning)
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", min_value=2020, max_value=2100, value=2026, step=1, key="my_docs_year")
    month_label = col2.selectbox("Month", [name for _, name in month_options()], index=1, key="my_docs_month")
    claim_period = resolve_claim_period(int(year), month_number(month_label))
    st.caption(f"Claim/register period for {claim_period.label}: {claim_period.display}")
    st.caption("The recommended document engine is used automatically.")
    month = month_number(month_label)
    state_key = document_output_state_key("my_documents", staff_number, int(year), month)
    if st.button("Generate documents"):
        try:
            st.session_state[state_key] = generate_v2_document_output_state(
                staff_number,
                int(year),
                month,
                current_user_for_render=user,
                audit_user=user,
                include_verification_checklist=False,
            )
            st.success("Documents generated.")
        except Exception as exc:
            show_document_generation_error("My document generation", exc)
    if st.session_state.get(state_key):
        render_document_output_state(st.session_state[state_key], owner_label="Latest generated document set for this lecturer/month.")


def render_persistent_export_status(
    success_key: str,
    error_key: str,
    clicked_key: str,
    success_message: str,
    download_text: str,
    placeholder,
) -> None:
    with placeholder.container():
        clicked_at = st.session_state.get(clicked_key)
        if clicked_at:
            st.caption(f"Button clicked at: {clicked_at}")
        error = st.session_state.get(error_key)
        if error:
            st.error(error)
            return
        payload = st.session_state.get(success_key)
        if not payload:
            return
        path = Path(str(payload["path"]))
        st.success(success_message)
        st.markdown(
            output_file_display_html(payload["path"], "Saved to", str(payload["size_display"]), str(payload["modified_timestamp_display"])),
            unsafe_allow_html=True,
        )
        try:
            st.download_button(
                download_text,
                data=read_file_bytes(path),
                file_name=path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        except Exception as exc:
            show_error("Download file could not be opened.", exc)


def render_file_metadata(path: Path) -> None:
    metadata = get_file_metadata(path)
    if not metadata["exists"]:
        st.error(f"Output file was not found: {path}")
        return
    st.markdown(
        output_file_display_html(metadata["path"], "Path", str(metadata["size_display"]), str(metadata["modified_timestamp_display"])),
        unsafe_allow_html=True,
    )


def render_download_button(label: str, path: Path, mime: str) -> None:
    try:
        st.download_button(
            label,
            data=read_file_bytes(path),
            file_name=path.name,
            mime=mime,
            width="stretch",
        )
    except Exception as exc:
        show_error(f"Could not prepare download for {path.name}.", exc)


def lecturer_selector(key: str) -> int | None:
    lecturers = lecturers_for_selector()
    if lecturers.empty:
        st.warning("No active lecturers found.")
        return None
    labels = {
        f"{row.staff_number} - {row.full_name}": int(row.id)
        for row in lecturers.itertuples(index=False)
    }
    selected = st.selectbox("Lecturer", list(labels.keys()), key=key)
    return labels[selected]


def page_dashboard() -> None:
    render_app_header(
        "Part-Time Lecturer Claims and Attendance Register Management System",
        "Administrative dashboard for claims, attendance registers, timetable data, and enrolments.",
        badge="Admin",
    )
    st.write(database_status_text())

    counts = cached_admin_dashboard_counts()
    cols = st.columns(3)
    for index, (label, value) in enumerate(counts.items()):
        cols[index % 3].metric(label.title(), value)


def page_master_data_import() -> None:
    render_app_header("Master Data Import", "Validate and import approved institutional workbook data.", badge="Admin")
    st.warning(
        "Do not upload bank details. Do not run dev_reset after importing real data. "
        "Use dummy data when testing. Sensitive lecturer fields are stored because the claim form requires them."
    )

    st.subheader("Step 1: Download or create template")
    if st.button("Generate master data template"):
        try:
            template_path = generate_master_data_template()
            st.success(f"Master data template generated: `{template_path}`")
        except Exception as exc:
            show_error("Template generation failed.", exc)
    st.info(
        "Copy this template, fill the copy with real data, save it under a new filename, "
        "then upload the completed workbook."
    )

    st.subheader("Step 2: Upload completed workbook")
    uploaded = st.file_uploader("Upload completed master data Excel workbook", type=["xlsx"])
    if not uploaded:
        st.info("Upload a completed real master data workbook to validate or import.")
        return

    if not is_supported_upload_filename(uploaded.name):
        st.error("Unsupported file type. Please upload a .xlsx workbook.")
        return

    workbook_path = save_uploaded_workbook(uploaded)
    uploaded_size = getattr(uploaded, "size", len(uploaded.getbuffer()))
    st.success("Uploaded workbook saved.")
    st.write(f"Filename: `{uploaded.name}`")
    st.write(f"Size: `{uploaded_size:,}` bytes")
    st.write(f"Saved path: `{workbook_path}`")

    st.subheader("Step 3: Dry-run validation")
    if st.button("Run dry-run validation"):
        try:
            workbook = read_workbook(workbook_path)
            errors = validate_workbook(workbook)
            if errors:
                st.session_state["dry_run_passed"] = False
                st.error(f"FAILED: validation found {len(errors)} error(s).")
                st.dataframe(pd.DataFrame([{"error": error.format()} for error in errors]), width="stretch")
            else:
                summary = import_master_data(workbook_path, dry_run=True)
                st.session_state["dry_run_passed"] = True
                st.success("PASSED: DRY RUN PASSED. No database changes were made.")
                st.dataframe(format_import_summary(summary), width="stretch")
                st.session_state["last_valid_workbook"] = str(workbook_path)
        except Exception as exc:
            st.session_state["dry_run_passed"] = False
            show_error("Dry-run validation failed.", exc)

    st.subheader("Step 4: Backup")
    st.warning("Back up the database before importing real data.")
    if st.button("Back up database"):
        try:
            backup_path = backup_database()
            st.session_state["backup_created_for_import"] = True
            st.success(f"Backup created: `{backup_path}`")
        except Exception as exc:
            st.session_state["backup_created_for_import"] = False
            show_error("Database backup failed.", exc)

    st.subheader("Step 5: Import")
    st.warning("Only import after reviewing the dry-run result.")
    dry_run_ready = (
        st.session_state.get("last_valid_workbook") == str(workbook_path)
        and st.session_state.get("dry_run_passed") is True
    )
    confirmed = st.checkbox("I confirm that I reviewed the dry-run result and created a backup.")
    can_import = can_import_workbook(dry_run_ready, confirmed)
    if not dry_run_ready:
        st.info("Import is disabled until dry-run validation passes for this uploaded workbook.")
    if st.button("Import workbook", disabled=not can_import):
        try:
            summary = import_master_data(workbook_path, dry_run=False)
            st.success("Import completed.")
            st.dataframe(format_import_summary(summary), width="stretch")
        except Exception as exc:
            show_error("Import failed.", exc)


def _active_yes_no(value=True) -> str:
    return "Yes" if bool(value) else "No"


def _lecturer_form_fields(
    prefix: str,
    defaults: dict | None = None,
    staff_number_disabled: bool = False,
    staff_number_value: str | None = None,
) -> dict:
    defaults = defaults or {}
    campus_options = ["Windhoek Main Campus", "Eenhana Satellite Campus", "Distance / Online", "Other"]
    default_campus = str(defaults.get("campus") or "Windhoek Main Campus")
    campus_choice_default = default_campus if default_campus in campus_options else "Other"
    start_default = pd.to_datetime(defaults.get("contract_start_date") or "2026-01-01").date()
    end_default = pd.to_datetime(defaults.get("contract_end_date") or "2026-12-31").date()
    title_default = defaults.get("title") if defaults.get("title") in ("Prof", "Dr", "Mr", "Ms") else "Ms"
    active_default = bool(defaults.get("active", 1))
    st.subheader("Basic details")
    basic_col1, basic_col2 = st.columns(2)
    with basic_col1:
        staff_number = st.text_input(
            "Staff number",
            value=str(staff_number_value if staff_number_value is not None else defaults.get("staff_number") or ""),
            disabled=staff_number_disabled,
            key=f"{prefix}_staff_number",
        )
        full_name = st.text_input("Full name", value=str(defaults.get("full_name") or ""), key=f"{prefix}_full_name")
        active = st.checkbox("Active", value=active_default, key=f"{prefix}_active")
    with basic_col2:
        title = st.selectbox(
            "Title",
            ["Prof", "Dr", "Mr", "Ms"],
            index=["Prof", "Dr", "Mr", "Ms"].index(title_default),
            key=f"{prefix}_title",
        )
        campus_choice = st.selectbox(
            "Campus suggestion",
            campus_options,
            index=campus_options.index(campus_choice_default),
            key=f"{prefix}_campus_choice",
        )
        campus_value = default_campus if campus_choice == "Other" else campus_choice
        campus = st.text_input("Campus", value=campus_value, key=f"{prefix}_campus")

    st.subheader("Claim details")
    claim_col1, claim_col2 = st.columns(2)
    with claim_col1:
        highest_qualification = st.text_input(
            "Highest qualification",
            value=str(defaults.get("highest_qualification") or ""),
            key=f"{prefix}_highest_qualification",
        )
        id_or_passport_number = st.text_input(
            "ID or passport number",
            value=str(defaults.get("id_or_passport_number") or ""),
            key=f"{prefix}_id_or_passport_number",
        )
        physical_address = st.text_area(
            "Physical address",
            value=str(defaults.get("physical_address") or ""),
            key=f"{prefix}_physical_address",
        )
    with claim_col2:
        tariff_per_hour = st.number_input(
            "Tariff per hour",
            min_value=0.0,
            value=float(defaults.get("tariff_per_hour") or 0.0),
            step=10.0,
            key=f"{prefix}_tariff_per_hour",
        )
        paye_number = st.text_input("PAYE number", value=str(defaults.get("paye_number") or ""), key=f"{prefix}_paye_number")
        contact_number = st.text_input(
            "Contact number",
            value=str(defaults.get("contact_number") or ""),
            key=f"{prefix}_contact_number",
        )

    st.subheader("Contract period")
    period_col1, period_col2 = st.columns(2)
    with period_col1:
        contract_start_date = st.date_input("Contract start date", value=start_default, key=f"{prefix}_contract_start_date")
    with period_col2:
        contract_end_date = st.date_input("Contract end date", value=end_default, key=f"{prefix}_contract_end_date")

    return {
        "staff_number": staff_number,
        "title": title,
        "full_name": full_name,
        "highest_qualification": highest_qualification,
        "id_or_passport_number": id_or_passport_number,
        "paye_number": paye_number,
        "physical_address": physical_address,
        "contact_number": contact_number,
        "tariff_per_hour": tariff_per_hour,
        "campus": campus,
        "contract_start_date": contract_start_date,
        "contract_end_date": contract_end_date,
        "active": active,
    }


def _show_lecturer_confirmation(record: dict) -> None:
    backup_result = record.get("_backup_result") if isinstance(record, dict) else None
    if backup_result:
        message = str(backup_result.get("safe_message") or "")
        if backup_result.get("performed") and backup_result.get("path"):
            st.info(f"{message} Saved backup: {backup_result.get('path')}")
        elif message:
            st.info(message)
    st.write("Saved lecturer summary:")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Staff number": record.get("staff_number", ""),
                    "Name": record.get("full_name", ""),
                    "Title": record.get("title", ""),
                    "Campus": record.get("campus", ""),
                    "Tariff": record.get("tariff_per_hour", ""),
                    "Contract period": f"{record.get('contract_start_date', '')} to {record.get('contract_end_date', '')}",
                    "Active": _active_yes_no(record.get("active", 0)),
                    "ID/passport": mask_sensitive_value(record.get("id_or_passport_number", "")),
                    "PAYE": mask_sensitive_value(record.get("paye_number", "")),
                }
            ]
        ),
        width="stretch",
    )


def _display_validation_errors(errors: list[str]) -> None:
    for error in errors:
        st.error(error)


def _lecturer_update_identity(existing: dict) -> str:
    return f"{int(existing.get('id'))}_{str(existing.get('staff_number') or '').strip()}"


def _lecturer_selection_matches_record(selected_staff_number: str, existing: dict) -> bool:
    return str(selected_staff_number).strip() == str(existing.get("staff_number") or "").strip()


def _render_selected_lecturer_summary(existing: dict) -> None:
    st.info(f"Selected record: {existing.get('staff_number', '')} - {existing.get('full_name', '')}")


def _render_staff_number_correction_panel(existing: dict, selected_staff_number: str) -> None:
    staff_number = str(existing.get("staff_number") or "")
    lecturer_id = int(existing.get("id"))
    identity = _lecturer_update_identity(existing)
    st.divider()
    st.subheader("Correct staff number")
    st.warning(
        "Use this only to correct a staff-number data-entry error for the same lecturer. "
        "Do not use it to replace one lecturer with another person."
    )
    st.caption(
        "The linked lecturer login username is updated when a matching lecturer account exists. "
        "Previously generated files are not renamed; regenerate official documents if the old staff number appears in them."
    )
    mismatch = not _lecturer_selection_matches_record(selected_staff_number, existing)
    if mismatch:
        st.error("Selected lecturer and loaded form record do not match. Please reselect the lecturer.")
    with st.form(f"correct_staff_number_form_{identity}"):
        st.text_input("Current staff number", value=staff_number, disabled=True, key=f"correct_current_staff_{identity}")
        new_staff_number = st.text_input("New staff number", key=f"correct_new_staff_{identity}").strip().replace(" ", "")
        confirmation = st.text_input(
            f'Type "{CONFIRMATION_PHRASE}" to confirm',
            key=f"correct_staff_confirmation_{identity}",
        )
        submitted = st.form_submit_button("Correct staff number", disabled=mismatch)
    if submitted:
        if mismatch:
            st.error("Selected lecturer and loaded form record do not match. Please reselect the lecturer.")
            return
        result = correct_lecturer_staff_number(
            current_user(),
            lecturer_id,
            staff_number,
            new_staff_number,
            confirmation,
        )
        if result.get("success"):
            st.success(result.get("safe_message"))
            for warning in result.get("warnings") or []:
                st.warning(warning)
            st.info("Refresh or reselect the lecturer to continue editing with the corrected staff number.")
        else:
            st.error(result.get("safe_message"))


def page_lecturer_entry() -> None:
    render_app_header("Lecturer Entry", "Capture and maintain lecturer claim details.", badge="Admin")
    st.info("Use this form to add or update lecturer details directly. Do not enter bank details.")
    st.warning("Sensitive lecturer fields are stored only because they are required for claim generation.")
    st.info("Real lecturer records are protected. A database backup is created before every lecturer save/update.")
    duplicates = find_duplicate_lecturers()
    if not duplicates.empty:
        st.warning("Duplicate lecturer staff numbers exist in the database. Review these before real use.")
        st.dataframe(duplicates, width="stretch")
    add_tab, update_tab, existing_tab = st.tabs(["Add Lecturer", "Update Lecturer", "Existing Lecturers"])

    with add_tab:
        staff_number_to_add = st.text_input("Staff number", key="add_staff_number_lookup").strip().replace(" ", "")
        duplicate_exists = lecturer_exists(staff_number_to_add)
        if duplicate_exists:
            st.warning("Lecturer with this staff number already exists. Use Update Existing Lecturer.")
        with st.form("add_lecturer_form"):
            data = _lecturer_form_fields("add", {"staff_number": staff_number_to_add}, staff_number_disabled=True)
            submitted = st.form_submit_button("Save lecturer", disabled=duplicate_exists)
        if submitted:
            data["staff_number"] = staff_number_to_add
            is_valid, errors = validate_lecturer_data(data)
            if not is_valid:
                _display_validation_errors(errors)
            elif lecturer_exists(data["staff_number"]):
                st.warning("Lecturer with this staff number already exists. Use Update Existing Lecturer.")
            else:
                try:
                    record = create_lecturer(data)
                    st.success("Lecturer saved successfully.")
                    _show_lecturer_confirmation(record)
                except Exception as exc:
                    show_error(str(exc), exc)

    with update_tab:
        lecturers_df_all = list_lecturers()
        if lecturers_df_all.empty:
            st.info("No lecturers found.")
        else:
            search_text = st.text_input("Search by staff number or name", key="update_lecturer_search").strip().lower()
            if search_text:
                lecturers_df_all = lecturers_df_all[
                    lecturers_df_all["staff_number"].astype(str).str.lower().str.contains(search_text, regex=False)
                    | lecturers_df_all["full_name"].astype(str).str.lower().str.contains(search_text, regex=False)
                ]
            if lecturers_df_all.empty:
                st.info("No matching lecturers found.")
            else:
                records = lecturers_df_all.to_dict("records")
                labels = {lecturer_option_label(record): record["staff_number"] for record in records}
                selected_label = st.selectbox("Select lecturer", list(labels.keys()), key="update_lecturer_select")
                staff_number = labels[selected_label]
                existing = get_lecturer_by_staff_number(staff_number)
                if not existing:
                    st.error("Selected lecturer could not be loaded.")
                    return
                mismatch = not _lecturer_selection_matches_record(staff_number, existing)
                _render_selected_lecturer_summary(existing)
                if mismatch:
                    st.error("Selected lecturer and loaded form record do not match. Please reselect the lecturer.")
                st.info("Staff number cannot be changed in update mode. Use the Active checkbox to deactivate or reactivate lecturers.")
                update_identity = _lecturer_update_identity(existing)
                with st.form(f"update_lecturer_form_{update_identity}"):
                    data = _lecturer_form_fields(f"update_{update_identity}", existing, staff_number_disabled=True)
                    submitted = st.form_submit_button("Update lecturer", disabled=mismatch)
                if submitted:
                    if mismatch or str(data.get("staff_number") or "").strip() != str(existing.get("staff_number") or "").strip():
                        st.error("Selected lecturer and loaded form record do not match. Please reselect the lecturer.")
                        return
                    try:
                        record = update_lecturer(staff_number, data)
                        st.success("Lecturer saved successfully.")
                        _show_lecturer_confirmation(record)
                    except Exception as exc:
                        show_error(str(exc), exc)
                _render_staff_number_correction_panel(existing, staff_number)

    with existing_tab:
        lecturers_df_all = list_lecturers()
        if lecturers_df_all.empty:
            st.info("No lecturers found.")
        else:
            search_text = st.text_input("Search existing lecturers", key="existing_lecturer_search").strip().lower()
            display_df = lecturers_df_all.copy()
            if search_text:
                display_df = display_df[
                    display_df["staff_number"].astype(str).str.lower().str.contains(search_text, regex=False)
                    | display_df["full_name"].astype(str).str.lower().str.contains(search_text, regex=False)
                ]
            st.dataframe(
                display_df[
                    [
                        "staff_number",
                        "title",
                        "full_name",
                        "campus",
                        "tariff_per_hour",
                        "contract_start_date",
                        "contract_end_date",
                        "active",
                    ]
                ],
                width="stretch",
            )

        st.subheader("Export lecturers")
        st.caption("Exports include lecturer fields needed for recovery and administrative review. Review before sharing.")
        if st.button("Export lecturers to CSV"):
            try:
                export_path = Path(export_lecturers_to_csv())
                payload = export_status_payload(export_path)
                st.success("Lecturers exported successfully.")
                st.markdown(
                    output_file_display_html(payload["path"], "Saved to", str(payload["size_display"]), str(payload["modified_timestamp_display"])),
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "Download lecturers CSV",
                    data=read_file_bytes(export_path),
                    file_name=export_path.name,
                    mime="text/csv",
                    width="stretch",
                )
            except Exception as exc:
                show_error("Lecturer export failed.", exc)


def _course_form_fields(prefix: str, defaults: dict | None = None, course_code_disabled: bool = False) -> dict:
    defaults = defaults or {}
    col1, col2 = st.columns(2)
    with col1:
        course_code = st.text_input(
            "Course code",
            value=str(defaults.get("course_code") or ""),
            disabled=course_code_disabled,
            key=f"{prefix}_course_code",
        )
        faculty = st.text_input(
            "Faculty",
            value=str(defaults.get("faculty") or "Computing and Informatics"),
            key=f"{prefix}_faculty",
        )
        active = st.checkbox("Active", value=bool(defaults.get("active", 1)), key=f"{prefix}_active")
    with col2:
        course_name = st.text_input("Course name", value=str(defaults.get("course_name") or ""), key=f"{prefix}_course_name")
        department = st.text_input("Department", value=str(defaults.get("department") or "Informatics"), key=f"{prefix}_department")
        budget_allocation = st.text_input(
            "Budget allocation",
            value=str(defaults.get("budget_allocation") or "0183-0102"),
            key=f"{prefix}_budget_allocation",
        )
    return {
        "course_code": course_code,
        "course_name": course_name,
        "faculty": faculty,
        "department": department,
        "budget_allocation": budget_allocation,
        "active": active,
    }


def _campus_input(prefix: str, default_campus: str = "Windhoek Main Campus") -> str:
    campus_options = ["Windhoek Main Campus", "Eenhana Satellite Campus", "Distance / Online", "Other"]
    campus_choice_default = default_campus if default_campus in campus_options else "Other"
    campus_choice = st.selectbox(
        "Campus suggestion",
        campus_options,
        index=campus_options.index(campus_choice_default),
        key=f"{prefix}_campus_choice",
    )
    campus_value = default_campus if campus_choice == "Other" else campus_choice
    return st.text_input("Campus", value=campus_value, key=f"{prefix}_campus")


def _group_form_fields(
    prefix: str,
    courses_df: pd.DataFrame,
    defaults: dict | None = None,
    locked_identity: bool = False,
) -> dict:
    defaults = defaults or {}
    course_records = courses_df.to_dict("records")
    course_labels = {course_option_label(record): record["course_code"] for record in course_records}
    default_course_code = str(defaults.get("course_code") or "")
    default_label = next(
        (label for label, code in course_labels.items() if code == default_course_code),
        next(iter(course_labels), ""),
    )
    study_modes = ["Full-time", "Part-time", "Extra-curricular", "Distance / Online"]
    default_study_mode = defaults.get("study_mode") if defaults.get("study_mode") in study_modes else "Full-time"
    col1, col2 = st.columns(2)
    with col1:
        if locked_identity:
            course_code = st.text_input("Course", value=default_course_code, disabled=True, key=f"{prefix}_course_code")
        else:
            selected_label = st.selectbox(
                "Course",
                list(course_labels.keys()),
                index=list(course_labels.keys()).index(default_label),
                key=f"{prefix}_course_select",
            )
            course_code = course_labels[selected_label]
        group_name = st.text_input(
            "Group name",
            value=str(defaults.get("group_name") or ""),
            disabled=locked_identity,
            key=f"{prefix}_group_name",
        )
        active = st.checkbox("Active", value=bool(defaults.get("active", 1)), key=f"{prefix}_active")
    with col2:
        campus = _campus_input(prefix, str(defaults.get("campus") or "Windhoek Main Campus"))
        study_mode = st.selectbox(
            "Study mode",
            study_modes,
            index=study_modes.index(default_study_mode),
            key=f"{prefix}_study_mode",
        )
    return {
        "group_name": group_name,
        "course_code": course_code,
        "campus": campus,
        "study_mode": study_mode,
        "active": active,
    }


def _lecturer_group_summary(record: dict) -> None:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Lecturer": f"{record.get('staff_number', '')} - {record.get('lecturer_name', '')}",
                    "Course": f"{record.get('course_code', '')} - {record.get('course_name', '')}",
                    "Group name": record.get("group_name", ""),
                    "Campus": record.get("campus", ""),
                    "Study mode": record.get("study_mode", ""),
                    "Active": _active_yes_no(record.get("active", 0)),
                }
            ]
        ),
        width="stretch",
    )


def _lecturer_group_form(
    prefix: str,
    lecturers_df_all: pd.DataFrame,
    courses_df_all: pd.DataFrame,
) -> dict:
    remove_lecturer_group_stale_keys(st.session_state)
    lecturer_records = lecturers_df_all.to_dict("records")
    staff_numbers = [str(record["staff_number"]) for record in lecturer_records]
    selected_staff_number = st.selectbox(
        "Lecturer",
        staff_numbers,
        format_func=lambda value: lecturer_option_label(lecturer_record_by_staff_number(lecturer_records, value)),
        key=f"{prefix}_staff_number",
    )
    selected_lecturer = lecturer_record_by_staff_number(lecturer_records, selected_staff_number)

    course_records = courses_df_all.to_dict("records")
    course_codes = [str(record["course_code"]) for record in course_records]
    course_lookup = {str(record["course_code"]): record for record in course_records}
    course_code = st.selectbox(
        "Course",
        course_codes,
        format_func=lambda value: course_option_label(course_lookup.get(str(value), {})),
        key=f"{prefix}_course_code",
    )

    default_alias = lecturer_alias_from_full_name(selected_lecturer.get("full_name", ""))
    customise_alias = st.checkbox("Customise lecturer alias", value=False, key=f"{prefix}_customise_alias")
    if customise_alias:
        lecturer_alias = st.text_input(
            "Lecturer alias",
            value=default_alias,
            key=f"{prefix}_lecturer_alias_custom_{selected_staff_number}",
        )
    else:
        lecturer_alias = default_alias
        st.text_input(
            "Lecturer alias",
            value=lecturer_alias,
            disabled=True,
            key=f"{prefix}_lecturer_alias_readonly_{selected_staff_number}",
        )

    col1, col2 = st.columns(2)
    with col1:
        semester = st.text_input("Semester", value="SEM1", key=f"{prefix}_semester")
        campus = _campus_input(prefix, str(selected_lecturer.get("campus") or "Windhoek Main Campus"))
    with col2:
        group_label = st.text_input("Group label", value="GREEN_FT", key=f"{prefix}_group_label")
        year = st.text_input("Year", value="2026", key=f"{prefix}_year")
        study_modes = ["Full-time", "Part-time", "Extra-curricular", "Distance / Online"]
        study_mode = st.selectbox("Study mode", study_modes, index=0, key=f"{prefix}_study_mode")

    generated_group_name = build_group_name(lecturer_alias, group_label, semester, year)
    st.write("Generated group name")
    st.code(generated_group_name or "(blank)", language="text")
    active = st.checkbox("Active", value=True, key=f"{prefix}_active")
    return {
        "staff_number": selected_lecturer["staff_number"],
        "course_code": course_code,
        "group_name": generated_group_name,
        "group_label": group_label,
        "semester": semester,
        "year": year,
        "campus": campus,
        "study_mode": study_mode,
        "active": active,
    }


def _show_existing_groups_for_selected_lecturer(staff_number: str) -> None:
    st.subheader("Existing groups for selected lecturer")
    groups = list_groups_for_lecturer(staff_number)
    if groups.empty:
        st.info("No groups found for this lecturer.")
        return
    st.dataframe(groups, width="stretch")


def _regenerated_group_name_for_selected_update_group(selected: dict) -> str:
    alias = lecturer_alias_from_full_name(selected.get("lecturer_name", ""))
    current_name = str(selected.get("group_name") or "")
    parts = current_name.split("_")
    label = "_".join(parts[1:-2]) if len(parts) >= 4 else ""
    semester = parts[-2] if len(parts) >= 2 else "SEM1"
    year = parts[-1] if parts and parts[-1].isdigit() else "2026"
    return build_group_name(alias, label, semester, year)


def _filter_df_by_search(df: pd.DataFrame, columns: list[str], search_text: str) -> pd.DataFrame:
    if df.empty or not search_text:
        return df
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask = mask | df[column].astype(str).str.lower().str.contains(search_text.lower(), regex=False)
    return df[mask]


def page_course_group_entry() -> None:
    render_app_header("Course and Group Entry", "Manage courses, generic groups, and lecturer-scoped groups.", badge="Admin")
    st.info("Use this page to capture courses and teaching groups. Groups must be linked to an existing course.")
    st.warning("Do not enter bank details. Student, enrolment, and timetable data are not captured on this page.")
    duplicate_groups = find_duplicate_groups()
    if not duplicate_groups.empty:
        st.warning("Duplicate group/course combinations exist in the database. Review these before real use.")
        st.dataframe(duplicate_groups, width="stretch")
    duplicate_lecturer_groups = find_duplicate_lecturer_groups()
    if not duplicate_lecturer_groups.empty:
        st.warning("Duplicate lecturer/course/group combinations exist in the database. Review these before real use.")
        st.dataframe(duplicate_lecturer_groups, width="stretch")

    courses_tab, groups_tab, lecturer_groups_tab, existing_tab = st.tabs(
        ["Courses", "Generic Groups", "Lecturer Groups", "Existing Courses and Groups"]
    )

    with courses_tab:
        st.caption("Examples: CUS411S, Computer User Skills; ICT521S, Information Competence; Faculty: Computing and Informatics; Department: Informatics; Budget allocation: 0183-0102.")
        add_course_tab, update_course_tab = st.tabs(["Add course", "Update course"])
        with add_course_tab:
            course_code_lookup = st.text_input("Course code", key="add_course_code_lookup").strip().upper().replace(" ", "")
            duplicate_course = course_exists(course_code_lookup)
            if duplicate_course:
                st.warning("Course with this course code already exists. Use Update Course.")
            with st.form("add_course_form"):
                data = _course_form_fields("add_course", {"course_code": course_code_lookup}, course_code_disabled=True)
                submitted = st.form_submit_button("Save course", disabled=duplicate_course)
            if submitted:
                data["course_code"] = course_code_lookup
                is_valid, errors = validate_course_data(data)
                if not is_valid:
                    _display_validation_errors(errors)
                elif course_exists(data["course_code"]):
                    st.warning("Course with this course code already exists. Use Update Course.")
                else:
                    try:
                        record = create_course(data)
                        st.success("Course saved successfully.")
                        st.dataframe(pd.DataFrame([record])[["course_code", "course_name", "faculty", "department", "budget_allocation", "active"]], width="stretch")
                    except Exception as exc:
                        show_error(str(exc), exc)

        with update_course_tab:
            courses_df_all = list_courses()
            if courses_df_all.empty:
                st.info("No courses found.")
            else:
                search_text = st.text_input("Search by course code or name", key="update_course_search").strip()
                courses_df_all = _filter_df_by_search(courses_df_all, ["course_code", "course_name"], search_text)
                if courses_df_all.empty:
                    st.info("No matching courses found.")
                else:
                    records = courses_df_all.to_dict("records")
                    labels = {course_option_label(record): record["course_code"] for record in records}
                    selected_label = st.selectbox("Select course", list(labels.keys()), key="update_course_select")
                    course_code = labels[selected_label]
                    existing = get_course_by_code(course_code)
                    with st.form("update_course_form"):
                        data = _course_form_fields("update_course", existing, course_code_disabled=True)
                        submitted = st.form_submit_button("Update course")
                    if submitted:
                        try:
                            record = update_course(course_code, data)
                            st.success("Course saved successfully.")
                            st.dataframe(pd.DataFrame([record])[["course_code", "course_name", "faculty", "department", "budget_allocation", "active"]], width="stretch")
                        except Exception as exc:
                            show_error(str(exc), exc)

    with groups_tab:
        courses_df_all = list_courses()
        if courses_df_all.empty:
            st.warning("Add at least one course before creating groups.")
        else:
            add_group_tab, update_group_tab = st.tabs(["Add group", "Update group"])
            with add_group_tab:
                with st.form("add_group_form"):
                    data = _group_form_fields("add_group", courses_df_all)
                    duplicate_group = group_exists(data["group_name"], data["course_code"])
                    if duplicate_group:
                        st.warning("Group with this name already exists for the selected course. Use Update Group.")
                    submitted = st.form_submit_button("Save group", disabled=duplicate_group)
                if submitted:
                    is_valid, errors = validate_group_data(data)
                    if not is_valid:
                        _display_validation_errors(errors)
                    elif group_exists(data["group_name"], data["course_code"]):
                        st.warning("Group with this name already exists for the selected course. Use Update Group.")
                    else:
                        try:
                            record = create_group(data)
                            st.success("Group saved successfully.")
                            st.dataframe(pd.DataFrame([record])[["course_code", "course_name", "group_name", "campus", "study_mode", "active"]], width="stretch")
                        except Exception as exc:
                            show_error(str(exc), exc)

            with update_group_tab:
                groups_df_all = list_groups()
                if groups_df_all.empty:
                    st.info("No groups found.")
                else:
                    search_text = st.text_input("Search by course code, course name, or group", key="update_group_search").strip()
                    groups_df_all = _filter_df_by_search(groups_df_all, ["course_code", "course_name", "group_name"], search_text)
                    if groups_df_all.empty:
                        st.info("No matching groups found.")
                    else:
                        records = groups_df_all.to_dict("records")
                        labels = {group_option_label(record): (record["group_name"], record["course_code"]) for record in records}
                        selected_label = st.selectbox("Select group", list(labels.keys()), key="update_group_select")
                        group_name, course_code = labels[selected_label]
                        existing = get_group(group_name, course_code)
                        with st.form("update_group_form"):
                            data = _group_form_fields("update_group", courses_df_all, existing, locked_identity=True)
                            submitted = st.form_submit_button("Update group")
                        if submitted:
                            try:
                                record = update_group(group_name, course_code, data)
                                st.success("Group saved successfully.")
                                st.dataframe(pd.DataFrame([record])[["course_code", "course_name", "group_name", "campus", "study_mode", "active"]], width="stretch")
                            except Exception as exc:
                                show_error(str(exc), exc)

    with lecturer_groups_tab:
        st.caption("Lecturer-scoped groups prepare future lecturer login filtering. Authentication is not implemented yet.")
        lecturers_df_all = list_lecturers()
        courses_df_all = list_courses()
        if lecturers_df_all.empty:
            st.warning("Add at least one lecturer before creating lecturer groups.")
        elif courses_df_all.empty:
            st.warning("Add at least one course before creating lecturer groups.")
        else:
            add_lg_tab, update_lg_tab, existing_lg_tab = st.tabs(["Add lecturer group", "Update lecturer group", "Existing lecturer groups"])
            with add_lg_tab:
                data = _lecturer_group_form("phase_6_3_add_lecturer_group", lecturers_df_all, courses_df_all)
                duplicate_group = lecturer_group_exists(data["staff_number"], data["course_code"], data["group_name"])
                if duplicate_group:
                    st.warning("Group with this name already exists for the selected lecturer and course.")
                submitted = st.button("Save lecturer group", disabled=duplicate_group, key="phase_6_3_save_lecturer_group")
                _show_existing_groups_for_selected_lecturer(data["staff_number"])
                with st.expander("Debug, selected lecturer state"):
                    selected_groups = list_groups_for_lecturer(data["staff_number"])
                    st.write(f"selected lecturer staff_number: {data['staff_number']}")
                    selected_record = get_lecturer_by_staff_number(data["staff_number"])
                    st.write(f"selected lecturer internal id: {selected_record.get('id', '') if selected_record else ''}")
                    st.write(f"selected lecturer full_name: {selected_record.get('full_name', '') if selected_record else ''}")
                    st.write(f"derived alias: {lecturer_alias_from_full_name(selected_record.get('full_name', '') if selected_record else '')}")
                    st.write(f"generated group name: {data['group_name']}")
                    st.write(f"number of groups found for selected lecturer: {len(selected_groups)}")
                if submitted:
                    is_valid, errors = validate_lecturer_group_data(data)
                    if not is_valid:
                        _display_validation_errors(errors)
                    elif lecturer_group_exists(data["staff_number"], data["course_code"], data["group_name"]):
                        st.warning("Group with this name already exists for the selected lecturer and course.")
                    else:
                        try:
                            record = create_lecturer_group(data)
                            st.success("Lecturer group saved successfully.")
                            _lecturer_group_summary(record)
                        except Exception as exc:
                            show_error(str(exc), exc)

            lecturer_groups_df = list_lecturer_groups()
            with update_lg_tab:
                if lecturer_groups_df.empty:
                    st.info("No lecturer groups found.")
                else:
                    search_text = st.text_input("Search lecturer groups", key="update_lecturer_group_search").strip()
                    filtered = _filter_df_by_search(
                        lecturer_groups_df,
                        ["staff_number", "lecturer_name", "course_code", "course_name", "group_name"],
                        search_text,
                    )
                    if filtered.empty:
                        st.info("No matching lecturer groups found.")
                    else:
                        records = filtered.to_dict("records")
                        labels = {
                            f"{record['staff_number']} - {record['course_code']} - {record['group_name']}": record
                            for record in records
                        }
                        selected_label = st.selectbox("Select lecturer group", list(labels.keys()), key="phase_6_4_update_lecturer_group_select")
                        selected = labels[selected_label]
                        selected_identity = f"{selected['staff_number']}|{selected['course_code']}|{selected['group_name']}"
                        st.text_input("Lecturer", value=f"{selected['staff_number']} - {selected['lecturer_name']}", disabled=True, key=f"phase_6_4_update_lg_lecturer_{selected_identity}")
                        st.text_input("Course", value=f"{selected['course_code']} - {selected['course_name']}", disabled=True, key=f"phase_6_4_update_lg_course_{selected_identity}")
                        regenerate = st.checkbox("Regenerate group name from lecturer alias", value=False, key=f"phase_6_4_update_lg_regenerate_{selected_identity}")
                        group_name_value = _regenerated_group_name_for_selected_update_group(selected) if regenerate else selected["group_name"]
                        with st.form(f"phase_6_4_update_lecturer_group_form_{selected_identity}"):
                            new_group_name = st.text_input("Group name", value=group_name_value, key=f"phase_6_4_update_lg_group_name_{selected_identity}")
                            campus = _campus_input(f"phase_6_4_update_lg_{selected_identity}", str(selected.get("campus") or "Windhoek Main Campus"))
                            study_modes = ["Full-time", "Part-time", "Extra-curricular", "Distance / Online"]
                            study_mode = st.selectbox(
                                "Study mode",
                                study_modes,
                                index=study_modes.index(selected["study_mode"]) if selected["study_mode"] in study_modes else 0,
                                key=f"phase_6_4_update_lg_study_mode_{selected_identity}",
                            )
                            active = st.checkbox("Active", value=bool(selected.get("active", 1)), key=f"phase_6_4_update_lg_active_{selected_identity}")
                            submitted = st.form_submit_button("Update lecturer group")
                        if submitted:
                            try:
                                record = update_lecturer_group(
                                    selected["staff_number"],
                                    selected["course_code"],
                                    selected["group_name"],
                                    {
                                        "group_name": new_group_name,
                                        "campus": campus,
                                        "study_mode": study_mode,
                                        "active": active,
                                    },
                                )
                                st.success("Lecturer group saved successfully.")
                                _lecturer_group_summary(record)
                            except Exception as exc:
                                show_error(str(exc), exc)

            with existing_lg_tab:
                st.subheader("Existing Lecturer Groups")
                lecturer_filter_options = ["All"] + [
                    lecturer_option_label(record) for record in lecturers_df_all.to_dict("records")
                ]
                course_filter_options = ["All"] + [
                    course_option_label(record) for record in courses_df_all.to_dict("records")
                ]
                filter_col1, filter_col2, filter_col3 = st.columns(3)
                lecturer_filter = filter_col1.selectbox("Lecturer filter", lecturer_filter_options, key="lg_lecturer_filter")
                course_filter = filter_col2.selectbox("Course filter", course_filter_options, key="lg_course_filter")
                active_filter = filter_col3.selectbox("Active status", ["All", "Active", "Inactive"], key="lg_active_filter")
                filtered = lecturer_groups_df.copy()
                if lecturer_filter != "All":
                    staff_number = lecturer_filter.split(" - ", 1)[0]
                    filtered = filtered[filtered["staff_number"] == staff_number]
                if course_filter != "All":
                    course_code = course_filter.split(" - ", 1)[0]
                    filtered = filtered[filtered["course_code"] == course_code]
                if active_filter == "Active":
                    filtered = filtered[filtered["active"].astype(int) == 1]
                elif active_filter == "Inactive":
                    filtered = filtered[filtered["active"].astype(int) == 0]
                st.dataframe(
                    filtered[
                        [
                            "staff_number",
                            "lecturer_name",
                            "course_code",
                            "course_name",
                            "group_name",
                            "campus",
                            "study_mode",
                            "active",
                        ]
                    ]
                    if not filtered.empty
                    else filtered,
                    width="stretch",
                )

    with existing_tab:
        courses_df_all = list_courses()
        groups_df_all = list_groups()
        st.subheader("Existing Courses")
        course_search = st.text_input("Search courses", key="existing_course_search").strip()
        course_display = _filter_df_by_search(courses_df_all, ["course_code", "course_name", "faculty", "department"], course_search)
        st.dataframe(course_display[["course_code", "course_name", "faculty", "department", "budget_allocation", "active"]] if not course_display.empty else course_display, width="stretch")

        st.subheader("Existing Groups")
        group_search = st.text_input("Search groups", key="existing_group_search").strip()
        group_display = _filter_df_by_search(groups_df_all, ["course_code", "course_name", "group_name", "campus", "study_mode"], group_search)
        st.dataframe(group_display[["course_code", "course_name", "group_name", "campus", "study_mode", "active"]] if not group_display.empty else group_display, width="stretch")


def page_data_inspection() -> None:
    render_app_header("Data Inspection", "Review current database records with sensitive fields masked by default.", badge="Admin")
    counts = cached_admin_dashboard_counts()
    count_cols = st.columns(3)
    for index, (label, value) in enumerate(counts.items()):
        count_cols[index % 3].metric(label.title(), value)

    show_sensitive = st.checkbox("Show sensitive fields")
    if show_sensitive:
        st.warning("WARNING: Sensitive lecturer fields are visible. Use this only with authorised data.")
    tabs = st.tabs(["Lecturers", "Courses", "Groups", "Students", "Timetable", "Academic Calendar"])

    with tabs[0]:
        st.dataframe(mask_sensitive_columns(lecturers_df(show_sensitive=True), show_sensitive), width="stretch")
    with tabs[1]:
        st.dataframe(table_df("courses"), width="stretch")
    with tabs[2]:
        st.dataframe(groups_df(), width="stretch")
    with tabs[3]:
        st.dataframe(table_df("students"), width="stretch")
    with tabs[4]:
        st.dataframe(timetable_df(), width="stretch")
    with tabs[5]:
        st.dataframe(calendar_df(), width="stretch")


def _calendar_scope_fields(prefix: str, scope_type: str, current: dict | None = None) -> dict:
    current = current or {}
    payload = {"lecturer_id": None, "course_id": None, "group_id": None}
    if scope_type == "lecturer":
        lecturers = list_lecturers()
        if lecturers.empty:
            st.warning("No lecturers found.")
            return payload
        records = lecturers.to_dict("records")
        options = [int(row["id"]) for row in records]
        lookup = {int(row["id"]): row for row in records}
        current_id = int(current.get("lecturer_id") or 0)
        index = options.index(current_id) if current_id in options else 0
        selected = st.selectbox(
            "Lecturer",
            options,
            index=index,
            format_func=lambda value: f"{lookup[int(value)]['staff_number']} - {lookup[int(value)]['full_name']}",
            key=f"{prefix}_scope_lecturer",
        )
        payload["lecturer_id"] = int(selected)
    elif scope_type == "course":
        courses = list_courses()
        if courses.empty:
            st.warning("No courses found.")
            return payload
        records = courses.to_dict("records")
        options = [str(row["course_code"]) for row in records]
        lookup = {str(row["course_code"]): row for row in records}
        current_id = int(current.get("course_id") or 0)
        current_code = next((str(row["course_code"]) for row in records if int(row.get("id") or 0) == current_id), None)
        index = options.index(current_code) if current_code in options else 0
        selected = st.selectbox(
            "Course",
            options,
            index=index,
            format_func=lambda value: f"{value} - {lookup[str(value)]['course_name']}",
            key=f"{prefix}_scope_course",
        )
        payload["course_id"] = int(lookup[str(selected)]["id"])
    elif scope_type == "group":
        groups = list_lecturer_groups()
        if groups.empty:
            st.warning("No lecturer-scoped groups found.")
            return payload
        records = groups.to_dict("records")
        options = [int(row["group_id"]) for row in records]
        lookup = {int(row["group_id"]): row for row in records}
        current_id = int(current.get("group_id") or 0)
        index = options.index(current_id) if current_id in options else 0
        selected = st.selectbox(
            "Group",
            options,
            index=index,
            format_func=lambda value: f"{lookup[int(value)]['staff_number']} - {lookup[int(value)]['course_code']} - {lookup[int(value)]['group_name']}",
            key=f"{prefix}_scope_group",
        )
        payload["group_id"] = int(selected)
    return payload


def _show_calendar_write_result(result: dict, success_message: str) -> None:
    if result.get("success"):
        st.success(success_message)
        backup_result = result.get("backup_result") or {}
        backup_message = backup_result.get("safe_message")
        if backup_message:
            st.info(str(backup_message))
        for warning in result.get("warnings", []):
            st.warning(warning)
    else:
        st.error(result.get("safe_message") or "Calendar operation failed.")


def page_academic_calendar() -> None:
    render_app_header("Academic Calendar", "Manage class exclusions for claims and attendance registers.", badge="Admin")
    st.info("Calendar entries affect generated sessions. Verify institutional calendar entries before relying on them for claims.")
    view_tab, add_tab, update_tab, reference_tab = st.tabs([
        "Existing exclusions",
        "Add exclusion",
        "Update / deactivate",
        "NUST 2026 reference",
    ])

    with view_tab:
        summary = calendar_summary_counts()
        if summary.empty:
            st.info("No academic calendar records found.")
        else:
            st.subheader("Summary by type")
            st.dataframe(summary, width="stretch")
        active_filter = st.selectbox("Active filter", ["Active", "Inactive", "All"], key="calendar_view_active")
        type_filter = st.selectbox("Type filter", ["All"] + CALENDAR_TYPES, key="calendar_view_type")
        active_value = None if active_filter == "All" else active_filter == "Active"
        type_value = None if type_filter == "All" else type_filter
        entries = list_calendar_entries(active=active_value, calendar_type=type_value)
        st.subheader("Calendar exclusions")
        if entries.empty:
            st.info("No matching calendar records found.")
        else:
            st.dataframe(entries, width="stretch")

    with add_tab:
        with st.form("calendar_add_form"):
            title = st.text_input("Title or description")
            col1, col2, col3 = st.columns(3)
            calendar_type = col1.selectbox("Category/type", CALENDAR_TYPES)
            start_date = col2.date_input("Start date")
            end_date = col3.date_input("End date")
            time_cols = st.columns(2)
            start_time = time_cols[0].text_input("Optional start time", placeholder="HH:MM")
            end_time = time_cols[1].text_input("Optional end time", placeholder="HH:MM")
            scope_type = st.selectbox(
                "Scope",
                SCOPE_TYPES,
                format_func=lambda value: {
                    "all": "All lecturers/all groups",
                    "lecturer": "Specific lecturer",
                    "course": "Specific course",
                    "group": "Specific group",
                }[value],
                key="calendar_add_scope",
            )
            scope_payload = _calendar_scope_fields("calendar_add", scope_type)
            exclude = st.checkbox("Exclude from claims and registers", value=True)
            notes = st.text_area("Notes/source")
            submitted = st.form_submit_button("Save calendar exclusion")
        if submitted:
            try:
                data = {
                    "title": title,
                    "calendar_type": calendar_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "scope_type": scope_type,
                    "exclude_from_claims_and_registers": exclude,
                    "notes": notes,
                    **scope_payload,
                }
                result = create_calendar_entry_result(data, user=current_user())
                message = "Calendar exclusion saved."
                if result.get("entry_id"):
                    message = f"Calendar exclusion saved. ID: {result['entry_id']}"
                _show_calendar_write_result(result, message)
            except Exception as exc:
                show_error("Calendar exclusion save failed unexpectedly.", exc)

    with update_tab:
        all_entries = list_calendar_entries()
        if all_entries.empty:
            st.info("No calendar records available to update.")
        else:
            records = all_entries.to_dict("records")
            ids = [int(row["id"]) for row in records]
            lookup = {int(row["id"]): row for row in records}
            selected_id = st.selectbox(
                "Calendar record",
                ids,
                format_func=lambda value: f"{value} - {lookup[int(value)]['title']} ({lookup[int(value)]['start_date']} to {lookup[int(value)]['end_date']})",
                key="calendar_update_id",
            )
            selected = get_calendar_entry(int(selected_id)) or {}
            with st.form("calendar_update_form"):
                title = st.text_input("Title or description", value=str(selected.get("title") or ""))
                col1, col2, col3 = st.columns(3)
                current_type = str(selected.get("calendar_type") or "").replace("_", " ").title()
                type_index = CALENDAR_TYPES.index(current_type) if current_type in CALENDAR_TYPES else len(CALENDAR_TYPES) - 1
                calendar_type = col1.selectbox("Category/type", CALENDAR_TYPES, index=type_index, key="calendar_update_type")
                start_date = col2.date_input("Start date", value=pd.to_datetime(selected.get("start_date")).date(), key="calendar_update_start")
                end_date = col3.date_input("End date", value=pd.to_datetime(selected.get("end_date")).date(), key="calendar_update_end")
                time_cols = st.columns(2)
                start_time = time_cols[0].text_input("Optional start time", value=str(selected.get("start_time") or ""), key="calendar_update_start_time")
                end_time = time_cols[1].text_input("Optional end time", value=str(selected.get("end_time") or ""), key="calendar_update_end_time")
                scope_type = str(selected.get("scope_type") or "all")
                if scope_type not in SCOPE_TYPES:
                    scope_type = "all"
                scope_type = st.selectbox("Scope", SCOPE_TYPES, index=SCOPE_TYPES.index(scope_type), key="calendar_update_scope")
                scope_payload = _calendar_scope_fields("calendar_update", scope_type, selected)
                exclude = st.checkbox("Exclude from claims and registers", value=bool(selected.get("exclude_from_claims_and_registers", 1)), key="calendar_update_exclude")
                active = st.checkbox("Active", value=bool(selected.get("active", 1)), key="calendar_update_active")
                notes = st.text_area("Notes/source", value=str(selected.get("notes") or ""), key="calendar_update_notes")
                submitted = st.form_submit_button("Update calendar exclusion")
            if submitted:
                try:
                    data = {
                        "title": title,
                        "calendar_type": calendar_type,
                        "start_date": start_date,
                        "end_date": end_date,
                        "start_time": start_time,
                        "end_time": end_time,
                        "scope_type": scope_type,
                        "exclude_from_claims_and_registers": exclude,
                        "active": active,
                        "notes": notes,
                        **scope_payload,
                    }
                    result = update_calendar_entry_result(int(selected_id), data, user=current_user())
                    _show_calendar_write_result(result, "Calendar exclusion updated.")
                except Exception as exc:
                    show_error("Calendar exclusion update failed unexpectedly.", exc)
            action_cols = st.columns(2)
            if action_cols[0].button("Deactivate selected entry", disabled=not bool(selected.get("active", 1))):
                try:
                    result = set_calendar_entry_active_result(int(selected_id), False, user=current_user())
                    _show_calendar_write_result(result, "Calendar exclusion deactivated.")
                except Exception as exc:
                    show_error("Calendar exclusion deactivation failed unexpectedly.", exc)
            if action_cols[1].button("Reactivate selected entry", disabled=bool(selected.get("active", 1))):
                try:
                    result = set_calendar_entry_active_result(int(selected_id), True, user=current_user())
                    _show_calendar_write_result(result, "Calendar exclusion reactivated.")
                except Exception as exc:
                    show_error("Calendar exclusion reactivation failed unexpectedly.", exc)

    with reference_tab:
        st.info("Reference list from the 2026 NUST Institutional Calendar. Compare manually before relying on entries for claims.")
        st.dataframe(reference_calendar_df(), width="stretch")


def page_timetable_entry() -> None:
    render_app_header("Timetable Entry", "Capture and manage timetable records for lecturer-scoped groups.", badge="Admin")
    st.info("Capture timetable entries for lecturer-scoped groups only. Generic groups are not used.")
    add_tab, update_tab, existing_tab, manage_tab = st.tabs([
        "Add timetable entry",
        "Update timetable entry",
        "Existing timetable entries",
        "Manage timetable entries",
    ])
    lecturers_df_all = list_lecturers()
    if lecturers_df_all.empty:
        st.warning("Add lecturers before capturing timetable entries.")
        return
    entries = list_timetable_entries()
    time_options = timetable_time_options()
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    lecturer_records = lecturers_df_all.to_dict("records")

    with add_tab:
        staff_numbers = [str(record["staff_number"]) for record in lecturer_records]
        selected_staff_number = st.selectbox(
            "Lecturer",
            staff_numbers,
            format_func=lambda value: lecturer_option_label(lecturer_record_by_staff_number(lecturer_records, value)),
            key="phase_7_1_timetable_staff_number",
        )
        selected_lecturer_record = lecturer_record_by_staff_number(lecturer_records, selected_staff_number) or {}
        st.info(
            f"Selected lecturer: {selected_lecturer_record.get('staff_number', selected_staff_number)} - "
            f"{selected_lecturer_record.get('full_name', '')}"
        )
        lecturer_groups = list_groups_for_timetable(selected_staff_number)
        if lecturer_groups.empty:
            st.warning("No lecturer-scoped groups found for this lecturer.")
        else:
            group_ids = [int(row["group_id"]) for row in lecturer_groups.to_dict("records")]
            group_lookup = {int(row["group_id"]): row for row in lecturer_groups.to_dict("records")}
            selected_group_id = st.selectbox(
                "Group",
                group_ids,
                format_func=lambda value: f"{group_lookup[int(value)]['course_code']} - {group_lookup[int(value)]['group_name']}",
                key=f"phase_7_1_timetable_group_id_{selected_staff_number}",
            )
            selected_group = group_lookup[int(selected_group_id)]
            st.info(
                f"Selected group: {selected_group['course_code']} - {selected_group['group_name']}\n\n"
                f"Group lecturer: {selected_group.get('staff_number', '')} - {selected_group.get('lecturer_name', '')}"
            )
            st.text_input(
                "Course",
                value=f"{selected_group['course_code']} - {selected_group['course_name']}",
                disabled=True,
                key=f"phase_7_1_timetable_course_{selected_staff_number}_{selected_group_id}",
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                day_of_week = st.selectbox("Day of week", weekdays, key="phase_7_1_timetable_day")
                active = st.checkbox("Active", value=True, key="phase_7_1_timetable_active")
            with col2:
                start_time = st.selectbox("Start time", time_options, index=time_options.index("08:00"), key="phase_7_1_timetable_start")
                effective_start_date = st.date_input("Effective start date", value=date(2026, 1, 1), key="phase_7_1_timetable_effective_start")
            with col3:
                end_time = st.selectbox("End time", time_options, index=time_options.index("09:00"), key="phase_7_1_timetable_end")
                effective_end_date = st.date_input("Effective end date", value=date(2026, 6, 30), key="phase_7_1_timetable_effective_end")

            data = {
                "staff_number": selected_staff_number,
                "group_id": selected_group_id,
                "day_of_week": day_of_week,
                "start_time": start_time,
                "end_time": end_time,
                "effective_start_date": effective_start_date,
                "effective_end_date": effective_end_date,
                "active": active,
            }
            is_valid, errors = validate_timetable_entry(data)
            ownership_message = timetable_group_ownership_message(selected_staff_number, selected_group_id)
            if ownership_message and "Group must belong to the selected lecturer." in errors:
                errors = [ownership_message if error == "Group must belong to the selected lecturer." else error for error in errors]
            if errors:
                for error in errors:
                    st.warning(error)
            if st.button("Save timetable entry", disabled=not is_valid, key="phase_7_1_save_timetable"):
                try:
                    record = create_timetable_entry(data)
                    st.success("Timetable entry saved successfully.")
                    st.dataframe(pd.DataFrame([record]), width="stretch")
                except Exception as exc:
                    show_error("Timetable entry save failed.", exc)

    with update_tab:
        if entries.empty:
            st.info("No timetable entries found.")
        else:
            entry_records = entries.to_dict("records")
            labels = {
                f"{row['id']} - {row['staff_number']} - {row['course_code']} - {row['group_name']} - {row['day_of_week']} {row['start_time']}-{row['end_time']}": row
                for row in entry_records
            }
            selected_label = st.selectbox("Select timetable entry", list(labels.keys()), key="phase_7_1_update_timetable_entry")
            selected = labels[selected_label]
            st.text_input("Lecturer", value=f"{selected['staff_number']} - {selected['lecturer_name']}", disabled=True, key=f"phase_7_1_update_lecturer_{selected['id']}")
            st.text_input("Course", value=f"{selected['course_code']} - {selected['course_name']}", disabled=True, key=f"phase_7_1_update_course_{selected['id']}")
            st.text_input("Group", value=selected["group_name"], disabled=True, key=f"phase_7_1_update_group_{selected['id']}")
            col1, col2, col3 = st.columns(3)
            with col1:
                day_of_week = st.selectbox("Day of week", weekdays, index=weekdays.index(selected["day_of_week"]), key=f"phase_7_1_update_day_{selected['id']}")
                active = st.checkbox("Active", value=bool(selected["active"]), key=f"phase_7_1_update_active_{selected['id']}")
            with col2:
                start_index = time_options.index(selected["start_time"]) if selected["start_time"] in time_options else 0
                start_time = st.selectbox("Start time", time_options, index=start_index, key=f"phase_7_1_update_start_{selected['id']}")
                effective_start_date = st.date_input("Effective start date", value=pd.to_datetime(selected["effective_start_date"]).date(), key=f"phase_7_1_update_effective_start_{selected['id']}")
            with col3:
                end_index = time_options.index(selected["end_time"]) if selected["end_time"] in time_options else 0
                end_time = st.selectbox("End time", time_options, index=end_index, key=f"phase_7_1_update_end_{selected['id']}")
                effective_end_date = st.date_input("Effective end date", value=pd.to_datetime(selected["effective_end_date"]).date(), key=f"phase_7_1_update_effective_end_{selected['id']}")
            data = {
                "staff_number": selected["staff_number"],
                "group_id": selected["group_id"],
                "day_of_week": day_of_week,
                "start_time": start_time,
                "end_time": end_time,
                "effective_start_date": effective_start_date,
                "effective_end_date": effective_end_date,
                "active": active,
            }
            is_valid, errors = validate_timetable_entry(data, exclude_id=int(selected["id"]))
            if errors:
                for error in errors:
                    st.warning(error)
            if st.button("Update timetable entry", disabled=not is_valid, key=f"phase_7_1_update_timetable_button_{selected['id']}"):
                try:
                    record = update_timetable_entry(int(selected["id"]), data)
                    st.success("Timetable entry updated successfully.")
                    st.dataframe(pd.DataFrame([record]), width="stretch")
                except Exception as exc:
                    show_error("Timetable entry update failed.", exc)

    with existing_tab:
        st.subheader("Existing timetable entries")
        if entries.empty:
            st.info("No timetable entries found.")
            return
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        lecturer_options = ["All"] + sorted(entries["staff_number"].astype(str).unique().tolist())
        course_options = ["All"] + sorted(entries["course_code"].astype(str).unique().tolist())
        group_options = ["All"] + sorted(entries["group_name"].astype(str).unique().tolist())
        active_options = ["All", "Active", "Inactive"]
        lecturer_filter = filter_col1.selectbox("Lecturer filter", lecturer_options, key="phase_7_1_filter_lecturer")
        course_filter = filter_col2.selectbox("Course filter", course_options, key="phase_7_1_filter_course")
        group_filter = filter_col3.selectbox("Group filter", group_options, key="phase_7_1_filter_group")
        active_filter = filter_col4.selectbox("Active filter", active_options, key="phase_7_1_filter_active")
        display = entries.copy()
        if lecturer_filter != "All":
            display = display[display["staff_number"].astype(str) == lecturer_filter]
        if course_filter != "All":
            display = display[display["course_code"].astype(str) == course_filter]
        if group_filter != "All":
            display = display[display["group_name"].astype(str) == group_filter]
        if active_filter != "All":
            display = display[display["active"] == (1 if active_filter == "Active" else 0)]
        st.dataframe(
            display[["id", "staff_number", "lecturer_name", "course_code", "group_name", "day_of_week", "start_time", "end_time", "effective_start_date", "effective_end_date", "active"]],
            width="stretch",
        )

    with manage_tab:
        st.subheader("Manage timetable entries")
        st.warning("Deactivate/reactivate is recommended. Hard delete is only for clear data-entry mistakes.")
        if entries.empty:
            st.info("No timetable entries found.")
            return
        filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)
        lecturer_options = ["All"] + sorted(entries["staff_number"].astype(str).unique().tolist())
        course_options = ["All"] + sorted(entries["course_code"].astype(str).unique().tolist())
        group_options = ["All"] + sorted(entries["group_name"].astype(str).unique().tolist())
        day_options = ["All"] + ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        active_options = ["All", "Active", "Inactive"]
        lecturer_filter = filter_col1.selectbox("Lecturer filter", lecturer_options, key="phase_7_2_manage_filter_lecturer")
        course_filter = filter_col2.selectbox("Course filter", course_options, key="phase_7_2_manage_filter_course")
        group_filter = filter_col3.selectbox("Group filter", group_options, key="phase_7_2_manage_filter_group")
        day_filter = filter_col4.selectbox("Day filter", day_options, key="phase_7_2_manage_filter_day")
        active_filter = filter_col5.selectbox("Active filter", active_options, key="phase_7_2_manage_filter_active")
        manage_df = entries.copy()
        if lecturer_filter != "All":
            manage_df = manage_df[manage_df["staff_number"].astype(str) == lecturer_filter]
        if course_filter != "All":
            manage_df = manage_df[manage_df["course_code"].astype(str) == course_filter]
        if group_filter != "All":
            manage_df = manage_df[manage_df["group_name"].astype(str) == group_filter]
        if day_filter != "All":
            manage_df = manage_df[manage_df["day_of_week"] == day_filter]
        if active_filter != "All":
            manage_df = manage_df[manage_df["active"] == (1 if active_filter == "Active" else 0)]
        if manage_df.empty:
            st.info("No matching timetable entries found.")
            return
        st.dataframe(
            manage_df[["id", "staff_number", "lecturer_name", "course_code", "group_name", "day_of_week", "start_time", "end_time", "effective_start_date", "effective_end_date", "active"]],
            width="stretch",
        )
        records = manage_df.to_dict("records")
        labels = {
            (
                f"{row['id']} - {row['staff_number']} - {row['lecturer_name']} - {row['group_name']} - "
                f"{row['day_of_week']} {row['start_time']}-{row['end_time']} - "
                f"{row['effective_start_date']} to {row['effective_end_date']} - "
                f"{'Active' if row['active'] else 'Inactive'}"
            ): row
            for row in records
        }
        selected_label = st.selectbox("Select timetable entry", list(labels.keys()), key="phase_7_2_manage_select")
        selected = labels[selected_label]
        st.write("Selected entry details")
        st.dataframe(pd.DataFrame([selected]), width="stretch")
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            if st.button("Deactivate selected entry", disabled=not bool(selected["active"]), key="phase_7_2_deactivate_timetable"):
                try:
                    record = deactivate_timetable_entry(int(selected["id"]))
                    st.success("Timetable entry deactivated.")
                    st.dataframe(pd.DataFrame([record]), width="stretch")
                except Exception as exc:
                    show_error("Timetable entry deactivation failed.", exc)
        with action_col2:
            if st.button("Reactivate selected entry", disabled=bool(selected["active"]), key="phase_7_2_reactivate_timetable"):
                try:
                    record = reactivate_timetable_entry(int(selected["id"]))
                    st.success("Timetable entry reactivated.")
                    st.dataframe(pd.DataFrame([record]), width="stretch")
                except Exception as exc:
                    show_error("Timetable entry reactivation failed.", exc)

        st.divider()
        st.error("Hard delete permanently removes the selected timetable row. Use only for mistaken entries.")
        confirmed = st.checkbox(
            "I understand this will permanently delete this timetable entry",
            key=f"phase_7_2_delete_confirm_{selected['id']}",
        )
        phrase = st.text_input("Type DELETE TIMETABLE ENTRY to enable hard delete", key=f"phase_7_2_delete_phrase_{selected['id']}")
        delete_enabled = hard_delete_confirmation_valid(confirmed, phrase)
        if st.button("Delete selected entry permanently", disabled=not delete_enabled, key=f"phase_7_2_delete_timetable_{selected['id']}"):
            try:
                delete_timetable_entry(int(selected["id"]))
                st.success("Timetable entry permanently deleted.")
            except Exception as exc:
                show_error("Timetable entry delete failed.", exc)


def _filtered_enrolments_table(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    if df.empty:
        return df
    col1, col2, col3, col4 = st.columns(4)
    lecturer_options = ["All"] + sorted(df["staff_number"].astype(str).unique().tolist())
    course_options = ["All"] + sorted(df["course_code"].astype(str).unique().tolist())
    group_options = ["All"] + sorted(df["group_name"].astype(str).unique().tolist())
    active_options = ["All", "Active", "Inactive"]
    lecturer_filter = col1.selectbox("Lecturer filter", lecturer_options, key=f"{key_prefix}_lecturer")
    course_filter = col2.selectbox("Course filter", course_options, key=f"{key_prefix}_course")
    group_filter = col3.selectbox("Group filter", group_options, key=f"{key_prefix}_group")
    active_filter = col4.selectbox("Active filter", active_options, key=f"{key_prefix}_active")
    display = df.copy()
    if lecturer_filter != "All":
        display = display[display["staff_number"].astype(str) == lecturer_filter]
    if course_filter != "All":
        display = display[display["course_code"].astype(str) == course_filter]
    if group_filter != "All":
        display = display[display["group_name"].astype(str) == group_filter]
    if active_filter != "All":
        display = display[display["active"] == (1 if active_filter == "Active" else 0)]
    return display


def page_student_upload() -> None:
    render_app_header("Student Upload", "Import students from Word attendance sheets and manage group enrolments.", badge="Admin")
    st.info("Import students after lecturer-scoped groups are created. The selected database group is the source of truth.")
    word_tab, file_tab, existing_tab, export_tab = st.tabs([
        "Upload from Word attendance sheet",
        "Upload from Excel or CSV template",
        "Existing student enrolments",
        "Export enrolments",
    ])

    lecturers_df_all = list_lecturers()
    if lecturers_df_all.empty:
        st.warning("Add lecturers before importing student enrolments.")
        return

    with word_tab:
        st.warning("Do not upload files containing bank details. Word header fields are used for validation only.")
        lecturer_records = lecturers_df_all.to_dict("records")
        staff_numbers = [str(record["staff_number"]) for record in lecturer_records]
        selected_staff = st.selectbox(
            "Lecturer",
            staff_numbers,
            format_func=lambda value: lecturer_option_label(lecturer_record_by_staff_number(lecturer_records, value)),
            key="phase_9_student_upload_staff",
        )
        groups = list_groups_for_timetable(selected_staff)
        if groups.empty:
            st.warning("No lecturer-scoped groups found for this lecturer.")
        else:
            course_codes = sorted(groups["course_code"].astype(str).unique().tolist())
            selected_course = st.selectbox("Course", course_codes, key="phase_9_student_upload_course")
            course_groups = groups[groups["course_code"].astype(str) == selected_course]
            group_lookup = {int(row["group_id"]): row for row in course_groups.to_dict("records")}
            selected_group_id = st.selectbox(
                "Target database group",
                list(group_lookup.keys()),
                format_func=lambda value: f"{group_lookup[int(value)]['course_code']} - {group_lookup[int(value)]['group_name']}",
                key="phase_9_student_upload_group",
            )
            selected_group = group_lookup[int(selected_group_id)]
            uploads = st.file_uploader(
                "Upload Word attendance sheet(s)",
                type=["docx"],
                accept_multiple_files=True,
                key="phase_9_word_uploads",
            )
            confirm_mapping = st.checkbox(
                "I confirm the Word GROUP value maps to the selected database group",
                key="phase_9_confirm_group_mapping",
            )
            allow_updates = st.checkbox(
                "Allow updating existing student surname/initials if student number already exists",
                key="phase_9_allow_student_updates",
            )
            if uploads:
                for upload_index, uploaded in enumerate(uploads):
                    st.subheader(uploaded.name)
                    if not uploaded.name.lower().endswith(".docx"):
                        st.error("Uploaded file must be .docx.")
                        continue
                    try:
                        uploaded.seek(0)
                        parsed = parse_attendance_docx(uploaded, source_name=uploaded.name)
                    except Exception as exc:
                        show_error("Could not parse Word attendance sheet.", exc)
                        continue
                    header = parsed.header
                    st.write("Extracted header information")
                    st.dataframe(pd.DataFrame([{
                        "course_name": header.get("course_name", ""),
                        "course_code": header.get("course_code", ""),
                        "group_label": header.get("group_label", ""),
                        "lecturer_name": header.get("lecturer_name", ""),
                        "staff_number": header.get("lecturer_staff_number", ""),
                    }]), width="stretch")
                    st.write("Target mapping")
                    st.code(
                        f"Word GROUP: {header.get('group_label', '') or '(not found)'}\n"
                        f"Target database group: {selected_group['group_name']}",
                        language="text",
                    )
                    students_df = pd.DataFrame(parsed.students)
                    if students_df.empty:
                        st.warning("No student rows were extracted.")
                    else:
                        preview_columns = ["student_number", "surname", "initials", "full_name"]
                        st.dataframe(students_df[[column for column in preview_columns if column in students_df.columns]], width="stretch")
                    is_valid, errors, warnings, skipped = validate_student_import(
                        parsed,
                        selected_staff,
                        selected_course,
                        int(selected_group_id),
                        confirm_group_mapping=confirm_mapping,
                        allow_student_updates=allow_updates,
                    )
                    for warning in warnings:
                        st.warning(warning)
                    for error in errors:
                        st.error(error)
                    if skipped:
                        st.write("Skipped rows")
                        st.dataframe(pd.DataFrame(skipped), width="stretch")
                    import_confirm = st.checkbox(
                        f"Import students from {uploaded.name} into {selected_group['group_name']}",
                        key=f"phase_9_import_confirm_{upload_index}_{uploaded.name}",
                    )
                    if st.button(
                        f"Import {uploaded.name}",
                        disabled=not (is_valid and import_confirm),
                        key=f"phase_9_import_button_{upload_index}_{uploaded.name}",
                    ):
                        try:
                            summary = import_students_for_group(
                                parsed,
                                selected_staff,
                                selected_course,
                                int(selected_group_id),
                                confirm_group_mapping=confirm_mapping,
                                allow_student_updates=allow_updates,
                            )
                            st.success("Students imported successfully.")
                            st.dataframe(pd.DataFrame([summary]), width="stretch")
                        except Exception as exc:
                            show_error("Student import failed.", exc)

    with file_tab:
        st.info(
            "Template columns: staff_number, course_code, group_name, student_number, surname, initials, full_name, active. "
            "Word upload is the recommended Phase 9.0 path."
        )
        template_upload = st.file_uploader("Upload student enrolment CSV/XLSX", type=["csv", "xlsx"], key="phase_9_template_upload")
        template_allow_updates = st.checkbox(
            "Allow updating existing student surname/initials from template",
            key="phase_9_template_allow_updates",
        )
        template_confirm = st.checkbox(
            "I reviewed this template and confirm it contains no bank details",
            key="phase_9_template_confirm",
        )
        if template_upload is not None and st.button("Import student template", disabled=not template_confirm, key="phase_9_template_import"):
            try:
                EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
                upload_path = EXPORTS_DIR / f"student_template_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{template_upload.name}"
                upload_path.write_bytes(template_upload.getvalue())
                summaries = import_student_template_file(upload_path, allow_student_updates=template_allow_updates)
                st.success("Student template imported successfully.")
                st.dataframe(pd.DataFrame(summaries), width="stretch")
            except Exception as exc:
                show_error("Student template import failed.", exc)

    with existing_tab:
        st.subheader("Existing student enrolments")
        enrolments = list_student_enrolments()
        if enrolments.empty:
            st.info("No student enrolments found.")
        else:
            display = _filtered_enrolments_table(enrolments, "phase_9_enrolment_filter")
            columns = [
                "enrolment_id",
                "staff_number",
                "lecturer_name",
                "course_code",
                "group_name",
                "student_number",
                "surname",
                "initials",
                "full_name",
                "active",
            ]
            st.dataframe(display[columns], width="stretch")
            if not display.empty:
                labels = {
                    (
                        f"{row['enrolment_id']} - {row['staff_number']} - {row['group_name']} - "
                        f"{row['student_number']} - {row['surname']} {row['initials']} - "
                        f"{'Active' if row['active'] else 'Inactive'}"
                    ): row
                    for row in display.to_dict("records")
                }
                selected_label = st.selectbox("Select enrolment", list(labels.keys()), key="phase_9_manage_enrolment")
                selected = labels[selected_label]
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Deactivate enrolment", disabled=not bool(selected["active"]), key="phase_9_deactivate_enrolment"):
                        try:
                            record = deactivate_enrolment(int(selected["enrolment_id"]))
                            st.success("Student enrolment deactivated.")
                            st.dataframe(pd.DataFrame([record]), width="stretch")
                        except Exception as exc:
                            show_error("Could not deactivate enrolment.", exc)
                with col2:
                    if st.button("Reactivate enrolment", disabled=bool(selected["active"]), key="phase_9_reactivate_enrolment"):
                        try:
                            record = reactivate_enrolment(int(selected["enrolment_id"]))
                            st.success("Student enrolment reactivated.")
                            st.dataframe(pd.DataFrame([record]), width="stretch")
                        except Exception as exc:
                            show_error("Could not reactivate enrolment.", exc)

    with export_tab:
        st.subheader("Export enrolments")
        if st.button("Export student enrolments to CSV", key="phase_9_export_enrolments"):
            try:
                output = export_student_enrolments_to_csv()
                metadata = get_file_metadata(output)
                st.success("Student enrolments exported successfully.")
                st.markdown(
                    output_file_display_html(output, "Saved to", str(metadata["size_display"]), str(metadata["modified_timestamp_display"])),
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "Download student enrolments CSV",
                    data=read_file_bytes(output),
                    file_name=Path(output).name,
                    mime="text/csv",
                )
            except Exception as exc:
                show_error("Student enrolment export failed.", exc)


def _render_preclaim_table(title: str, table: pd.DataFrame, empty_message: str) -> None:
    st.subheader(title)
    if table is None or table.empty:
        st.info(empty_message)
    else:
        st.dataframe(table, width="stretch")


def page_preclaim_verification() -> None:
    render_app_header("Pre-Claim Verification", "Review claim/register readiness before generating official documents.", badge="Admin")
    st.info("This page is read-only except for optional verification report export. It does not generate claim or register documents.")
    lecturer_id = lecturer_selector("preclaim_lecturer")
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", min_value=2020, max_value=2100, value=2026, step=1, key="preclaim_year")
    month_label = col2.selectbox("Month", [name for _, name in month_options()], index=1, key="preclaim_month")
    month = month_number(month_label)
    selected_period = resolve_claim_period(int(year), month)
    st.caption(f"Claim/register period for {selected_period.label}: {selected_period.display}")
    if lecturer_id is None:
        return

    with get_runtime_connection() as conn:
        lecturer_row = conn.execute(
            convert_placeholders("SELECT staff_number FROM lecturers WHERE id = ?"),
            (int(lecturer_id),),
        ).fetchone()
    lecturer_row = row_to_dict(lecturer_row)
    if lecturer_row is None:
        st.error("Selected lecturer was not found.")
        return
    staff_number = str(lecturer_row["staff_number"])

    if st.button("Run pre-claim verification", key="run_preclaim_verification"):
        try:
            st.session_state["preclaim_result"] = build_preclaim_verification(staff_number, int(year), month)
        except Exception as exc:
            show_error("Pre-claim verification failed.", exc)
            return

    result = st.session_state.get("preclaim_result")
    if not result:
        st.caption("Select a lecturer, year, and month, then run verification.")
        return

    status = result["status"]
    if status == "PASS":
        st.success("PASS: No blockers found.")
    elif status == "WARN":
        st.warning("WARN: Review warnings before generating documents.")
    else:
        st.error("BLOCK: Resolve blockers before generating official claim/register documents.")
    st.info("Only generate documents after resolving blockers and reviewing warnings.")

    summary = result["summary"]
    cols = st.columns(4)
    cols[0].metric("Lecturer", summary.get("lecturer_name", ""))
    cols[1].metric("Staff number", summary.get("staff_number", ""))
    cols[2].metric("Month", summary.get("year_month", ""))
    cols[3].metric("Status", status)
    cols = st.columns(4)
    cols[0].metric("Sessions", int(summary.get("total_claimable_sessions", 0)))
    cols[1].metric("Hours", format_hours_value(float(summary.get("total_claimable_hours", 0))))
    cols[2].metric("Estimated amount", format_namibian_currency(float(summary.get("estimated_claim_amount", 0))))
    cols[3].metric("Clashes", len(result["tables"].get("clashes", pd.DataFrame())))

    st.subheader("Lecturer and contract")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "lecturer_name": summary.get("lecturer_name"),
                    "staff_number": summary.get("staff_number"),
                    "campus": summary.get("campus"),
                    "tariff_per_hour": summary.get("tariff_per_hour"),
                    "contract_start_date": summary.get("contract_start_date"),
                    "contract_end_date": summary.get("contract_end_date"),
                    "month_overlaps_contract": summary.get("month_overlaps_contract"),
                    "month_fully_within_contract": summary.get("month_fully_within_contract"),
                    "claim_period": summary.get("claim_period"),
                }
            ]
        ),
        width="stretch",
    )

    if result["blockers"]:
        st.subheader("Blockers")
        for blocker in result["blockers"]:
            st.error(blocker)
    if result["warnings"]:
        st.subheader("Warnings")
        for warning in result["warnings"]:
            st.warning(warning)

    tables = result["tables"]
    _render_preclaim_table("Active lecturer-scoped groups", tables["groups"], "No active groups found.")
    _render_preclaim_table("Active timetable entries", tables["timetable"], "No active timetable entries found.")
    _render_preclaim_table("Active enrolments by zero-enrolment group", tables["zero_enrolment_groups"], "No zero-enrolment active groups found.")
    _render_preclaim_table("Academic calendar exclusions affecting month", tables["calendar_exclusions"], "No active academic calendar exclusions found.")
    _render_preclaim_table("Applied calendar exclusions", tables.get("applied_calendar_exclusions", pd.DataFrame()), "No calendar exclusions were applied to generated sessions.")
    _render_preclaim_table("Excluded session details", tables.get("excluded_session_details", pd.DataFrame()), "No sessions were removed by calendar exclusions.")
    _render_preclaim_table("Expected NUST reference items for month", tables["expected_calendar_items"], "No NUST reference items expected for this month.")
    _render_preclaim_table("Suspicious enrolments", tables.get("suspicious_enrolments", pd.DataFrame()), "No suspicious header-row enrolments found.")
    _render_preclaim_table("Generated claimable sessions", safe_sessions_display_df(tables["generated_sessions"]) if not tables["generated_sessions"].empty else tables["generated_sessions"], "No generated claimable sessions found.")
    _render_preclaim_table("Totals by course", tables["totals_by_course"], "No course totals found.")
    _render_preclaim_table("Totals by group", tables["totals_by_group"], "No group totals found.")
    _render_preclaim_table("Clashes", tables["clashes"], "No clashes detected.")

    if st.button("Export pre-claim verification report", key="export_preclaim_verification"):
        try:
            output = export_preclaim_verification_report(result)
            st.success("Pre-claim verification report exported.")
            render_output_file("Saved to", output)
            st.download_button(
                "Download pre-claim verification CSV",
                data=read_file_bytes(output),
                file_name=Path(output).name,
                mime="text/csv",
            )
        except Exception as exc:
            show_error("Pre-claim verification export failed.", exc)


def page_session_generation() -> None:
    render_app_header("Session Generation", "Generate claimable teaching sessions from approved timetable data.", badge="Admin")
    lecturer_id = lecturer_selector("sessions_lecturer")
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", min_value=2020, max_value=2100, value=2026, step=1)
    month_label = col2.selectbox("Month", [name for _, name in month_options()], index=1)
    month = month_number(month_label)
    claim_period = resolve_claim_period(int(year), month)
    st.caption(f"Claim/register period for {claim_period.label}: {claim_period.display}")

    if lecturer_id is None:
        return

    if st.button("Generate sessions"):
        try:
            sessions_df = generate_monthly_sessions(lecturer_id, int(year), month)
            clashes_df = detect_clashes(sessions_df)
            st.session_state["sessions_df"] = sessions_df
            st.session_state["clashes_df"] = clashes_df
            st.session_state["sessions_year"] = int(year)
            st.session_state["sessions_month"] = month
            for key in (
                "last_sessions_export",
                "last_checklist_export",
                "last_sessions_export_error",
                "last_checklist_export_error",
                "last_sessions_export_clicked_at",
                "last_checklist_export_clicked_at",
            ):
                st.session_state.pop(key, None)
        except Exception as exc:
            show_error("Session generation failed.", exc)
            return

    sessions_df = st.session_state.get("sessions_df")
    clashes_df = st.session_state.get("clashes_df")
    if sessions_df is None or sessions_df.empty:
        st.info("Generate sessions to view claimable teaching sessions and export options.")
        return

    active_year = int(st.session_state.get("sessions_year", int(year)))
    active_month = int(st.session_state.get("sessions_month", month))
    active_month_label = dict(month_options()).get(active_month, str(active_month))

    st.subheader("Generated claimable teaching sessions")
    lecturer_details = lecturer_display_details(sessions_df)
    lecturer_name = lecturer_details["lecturer"]
    staff_number = lecturer_details["staff_number"]
    total_sessions = len(sessions_df)
    total_hours = float(sessions_df["hours"].sum()) if not sessions_df.empty else 0
    total_amount = float(sessions_df["amount"].sum()) if not sessions_df.empty else 0
    st.markdown(f"**Lecturer:** {lecturer_name}")
    st.markdown(f"**Staff number:** {staff_number}")
    summary_cols = st.columns(3)
    summary_cols[0].metric("Month", f"{active_month_label} {active_year}")
    summary_cols[1].metric("Total sessions", f"{total_sessions:d}")
    summary_cols[2].metric("Total hours", format_hours_value(total_hours))
    summary_cols = st.columns(3)
    summary_cols[0].metric("Total amount", format_namibian_currency(total_amount))
    summary_cols[1].metric("Clashes", f"{len(clashes_df):d}")

    st.info(
        "Visible table hides sensitive lecturer fields. Backend exports may include fields required for "
        "document generation; review exports before sharing externally."
    )

    display_df = safe_sessions_display_df(sessions_df)
    filter_cols = st.columns(2)
    course_options = ["All"] + sorted(display_df["course_code"].dropna().astype(str).unique().tolist()) if "course_code" in display_df else ["All"]
    selected_course = filter_cols[0].selectbox("Course filter", course_options)
    filtered_df = display_df.copy()
    if selected_course != "All":
        filtered_df = filtered_df[filtered_df["course_code"].astype(str) == selected_course]
    group_options = ["All"] + sorted(filtered_df["group_name"].dropna().astype(str).unique().tolist()) if "group_name" in filtered_df else ["All"]
    selected_group = filter_cols[1].selectbox("Group filter", group_options)
    if selected_group != "All":
        filtered_df = filtered_df[filtered_df["group_name"].astype(str) == selected_group]

    st.dataframe(filtered_df, width="stretch")
    st.caption("Filters affect only the visible table. Totals above remain based on all generated sessions.")

    st.subheader("Grouped summary by group")
    st.dataframe(grouped_sessions_summary_df(sessions_df), width="stretch")

    with st.expander("Excluded dates for selected month"):
        excluded_df = get_excluded_date_details(active_year, active_month)
        if excluded_df.empty:
            st.info("No excluded dates found.")
        else:
            st.dataframe(excluded_df, width="stretch")
    if clashes_df.empty:
        st.success("No clashes detected.")
    else:
        st.error("Clashes detected. Review before generating claim/register documents.")
        st.dataframe(clashes_df, width="stretch")

    st.caption(
        "Exports use backend data for document generation and may include fields hidden from the visible table. "
        "Do not share exports externally without review."
    )
    out_dir = output_folder_for(staff_number, active_year, active_month)
    if st.button("Export generated sessions to Excel"):
        st.session_state["last_sessions_export_clicked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.pop("last_sessions_export", None)
        st.session_state.pop("last_sessions_export_error", None)
        try:
            EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
            path = EXPORTS_DIR / f"sessions_lecturer_{staff_number}_{active_year}_{active_month:02d}.xlsx"
            if path.exists():
                path.unlink()
            export_sessions_to_excel(sessions_df, clashes_df, path)
            st.session_state["last_sessions_export"] = export_status_payload(path)
        except Exception as exc:
            st.session_state["last_sessions_export_error"] = str(exc)
            show_error("Session export failed.", exc)
    sessions_export_placeholder = st.empty()
    render_persistent_export_status(
        "last_sessions_export",
        "last_sessions_export_error",
        "last_sessions_export_clicked_at",
        "Generated sessions exported successfully.",
        "Download generated sessions Excel",
        sessions_export_placeholder,
    )

    if st.button("Export verification checklist"):
        st.session_state["last_checklist_export_clicked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.pop("last_checklist_export", None)
        st.session_state.pop("last_checklist_export_error", None)
        try:
            path = out_dir / f"verification_checklist_{staff_number}_{active_year}_{active_month:02d}.xlsx"
            if path.exists():
                path.unlink()
            generate_verification_checklist(
                sessions_df,
                clashes_df,
                path,
                active_year,
                active_month,
                documents_generated=False,
                generation_status="Generated from UI",
                notes="Verification checklist generated without DOCX documents.",
            )
            st.session_state["last_checklist_export"] = export_status_payload(path)
        except Exception as exc:
            st.session_state["last_checklist_export_error"] = str(exc)
            show_error("Verification checklist generation failed.", exc)
    checklist_export_placeholder = st.empty()
    render_persistent_export_status(
        "last_checklist_export",
        "last_checklist_export_error",
        "last_checklist_export_clicked_at",
        "Verification checklist exported successfully.",
        "Download verification checklist",
        checklist_export_placeholder,
    )


def page_document_generation() -> None:
    render_app_header("Document Generation", "Generate claim and attendance register documents.", badge="Admin")
    st.info("Run Pre-Claim Verification before generating official documents.")
    st.caption("Generated documents should be reviewed before submission.")
    warning = generated_file_mode_warning()
    if warning:
        st.warning(warning)
    lecturer_id = lecturer_selector("docs_lecturer")
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", min_value=2020, max_value=2100, value=2026, step=1, key="docs_year")
    month_label = col2.selectbox("Month", [name for _, name in month_options()], index=1, key="docs_month")
    engine = "v2 docxtpl, recommended"
    with st.expander("Advanced options"):
        engine = st.selectbox(
            "Document engine",
            ["v2 docxtpl, recommended", "legacy template generator", "legacy generated layout"],
            index=0,
        )
    if engine != "v2 docxtpl, recommended":
        st.warning("Legacy engines are for troubleshooting only and may not preserve institutional formatting.")
    month = month_number(month_label)
    claim_period = resolve_claim_period(int(year), month)
    st.caption(f"Claim/register period for {claim_period.label}: {claim_period.display}")

    if lecturer_id is None:
        return
    selected_staff_number = _staff_number_for_lecturer_id(int(lecturer_id))
    if selected_staff_number is None:
        st.error("Selected lecturer was not found.")
        return
    state_key = document_output_state_key("admin_documents", selected_staff_number, int(year), month)
    generate_clicked = st.button("Generate documents")
    if not generate_clicked:
        if st.session_state.get(state_key):
            render_document_output_state(st.session_state[state_key], owner_label="Latest generated document set for this lecturer/month.")
        return
    try:
        if engine == "v2 docxtpl, recommended":
            missing_templates = missing_v2_manual_templates()
            if missing_templates:
                missing_text = "\n".join(str(path) for path in missing_templates)
                st.error(
                    "Missing v2 manual template:\n"
                    f"{missing_text}\n\n"
                    "Please copy the manually edited institutional template into data/docx_templates_v2/."
                )
                return

            st.session_state[state_key] = generate_v2_document_output_state(
                selected_staff_number,
                int(year),
                month,
                audit_user=current_user(),
                include_verification_checklist=True,
            )
            st.success("Documents generated successfully.")
            render_document_output_state(st.session_state[state_key], owner_label="Latest generated document set for this lecturer/month.")
        else:
            layout_mode = "template" if engine == "legacy template generator" else "generated"
            result = generate_monthly_documents(
                lecturer_id,
                int(year),
                month,
                allow_clashes=False,
                layout_mode=layout_mode,
                strict_template=True,
            )
            st.success("Legacy document workflow completed.")
            render_path_block("Output folder", result["output_folder"])
            render_output_file("Verification checklist", result["verification_path"])
            if result["documents_generated"]:
                render_output_file("Claim form", result["claim_path"])
                for path in result.get("attendance_paths", []):
                    render_output_file("Register", path)
            else:
                st.error("Documents blocked because clashes were detected.")
    except Exception as exc:
        text = str(exc)
        if engine == "v2 docxtpl, recommended" and "missing manual template" in text.lower():
            show_error(
                "Missing v2 manual template. Copy the manually edited institutional templates to data/docx_templates_v2/.",
                exc,
            )
        elif "template" in text.lower() and "missing" in text.lower():
            show_error("Missing DOCX template. Copy the approved templates to data/docx_templates/.", exc)
        else:
            show_document_generation_error("Document generation", exc)


def page_maria_pilot() -> None:
    st.header("Maria Matias April 2026 Pilot")
    st.warning("This pilot is reconstructed from a submitted claim, not an approved timetable.")
    st.info('After running the pilot, use Document Generation with engine "v2 docxtpl, recommended" to generate the preferred draft claim and registers.')
    st.dataframe(
        pd.DataFrame(
            [
                {"Metric": "Sessions", "Expected": EXPECTED_SESSIONS, "Actual": "", "Status": ""},
                {"Metric": "Hours", "Expected": format_hours_value(EXPECTED_HOURS), "Actual": "", "Status": ""},
                {"Metric": "Amount", "Expected": format_namibian_currency(EXPECTED_AMOUNT), "Actual": "", "Status": ""},
                {"Metric": "Clashes", "Expected": 0, "Actual": "", "Status": ""},
            ]
        ),
        width="stretch",
    )
    if st.button("Create Maria pilot workbook"):
        try:
            st.success(f"Created workbook: `{create_maria_pilot_workbook()}`")
        except Exception as exc:
            show_error("Maria pilot workbook creation failed.", exc)

    if st.button("Run Maria pilot workflow"):
        try:
            workbook_path = create_maria_pilot_workbook()
            import_master_data(workbook_path, dry_run=False)
            sessions_df = generate_monthly_sessions(1008977, 2026, 4)
            clashes_df = detect_clashes(sessions_df)
            result = generate_monthly_documents(1008977, 2026, 4, layout_mode="template", strict_template=True)
            actual_sessions = len(sessions_df)
            actual_hours = round(float(sessions_df["hours"].sum()), 2)
            actual_amount = round(float(sessions_df["amount"].sum()), 2)
            actual_clashes = len(clashes_df)
            comparison = pd.DataFrame(
                [
                    {
                        "Metric": "Sessions",
                        "Expected": EXPECTED_SESSIONS,
                        "Actual": actual_sessions,
                        "Status": "PASS" if EXPECTED_SESSIONS == actual_sessions else "FAIL",
                    },
                    {
                        "Metric": "Hours",
                        "Expected": format_hours_value(EXPECTED_HOURS),
                        "Actual": format_hours_value(actual_hours),
                        "Status": "PASS" if EXPECTED_HOURS == actual_hours else "FAIL",
                    },
                    {
                        "Metric": "Amount",
                        "Expected": format_namibian_currency(EXPECTED_AMOUNT),
                        "Actual": format_namibian_currency(actual_amount),
                        "Status": "PASS" if EXPECTED_AMOUNT == actual_amount else "FAIL",
                    },
                    {
                        "Metric": "Clashes",
                        "Expected": 0,
                        "Actual": actual_clashes,
                        "Status": "PASS" if actual_clashes == 0 else "FAIL",
                    },
                ]
            )
            st.dataframe(comparison, width="stretch")
            render_path_block("Output folder", result["output_folder"])
        except Exception as exc:
            show_error("Maria pilot workflow failed.", exc)


def page_development() -> None:
    with st.expander("Development only"):
        st.error("This will delete local data. Do not use on real data.")
        confirmation = st.text_input("Type DELETE LOCAL DATA to enable dev reset")
        if st.button("Run dev_reset", disabled=confirmation != "DELETE LOCAL DATA"):
            try:
                dev_reset()
                st.success("Development database reset completed.")
            except Exception as exc:
                show_error("dev_reset failed.", exc)


def page_account_management() -> None:
    render_app_header("Account Management", "Admin-only account review, lecturer account creation, and password reset.", badge="Admin")
    st.subheader("Create lecturer account")
    missing_accounts = list_lecturers_without_accounts()
    if missing_accounts.empty:
        st.info("All lecturers already have lecturer login accounts.")
    else:
        display_missing = missing_accounts[["staff_number", "full_name", "active", "account_exists"]].copy()
        st.dataframe(display_missing, width="stretch")
        missing_records = missing_accounts.to_dict("records")
        create_labels = {
            f"{record['staff_number']} - {record['full_name']}": int(record["lecturer_id"])
            for record in missing_records
        }
        selected_create_label = st.selectbox(
            "Lecturer without account",
            list(create_labels.keys()),
            key="account_create_lecturer",
        )
        create_temp_password = st.text_input("Temporary password", type="password", key="account_create_temp")
        create_confirm_password = st.text_input("Confirm temporary password", type="password", key="account_create_confirm")
        st.info("The lecturer must change this temporary password at next login. Communicate it outside the system.")
        if st.button("Create lecturer account"):
            result = create_lecturer_account_for_lecturer(
                current_user(),
                create_labels[selected_create_label],
                create_temp_password,
                create_confirm_password,
            )
            if result.get("success"):
                st.success(result["safe_message"])
                for warning in result.get("warnings", []):
                    st.warning(warning)
            else:
                st.error(result["safe_message"])

    st.subheader("Existing accounts")
    users = list_user_accounts()
    if users.empty:
        st.info("No user accounts found.")
        return
    st.dataframe(users, width="stretch")
    lecturer_users = users[users["role"] == "lecturer"]
    if lecturer_users.empty:
        st.info("No lecturer accounts found.")
        return
    labels = {f"{row.username} - {row.lecturer_name or ''}": row.username for row in lecturer_users.itertuples(index=False)}
    selected_label = st.selectbox("Lecturer account", list(labels.keys()), key="account_reset_user")
    temp_password = st.text_input("Temporary password", type="password", key="account_reset_temp")
    confirm_password = st.text_input("Confirm temporary password", type="password", key="account_reset_confirm")
    st.info("The lecturer must change this temporary password at next login. Communicate it outside the system.")
    if st.button("Reset lecturer password"):
        result = reset_user_password(current_user(), labels[selected_label], temp_password, confirm_password)
        if result.get("success"):
            st.success(result["safe_message"])
            if result.get("audit_warning"):
                st.warning(result["audit_warning"])
        else:
            st.error(result["safe_message"])


def page_audit_log() -> None:
    render_app_header("Audit Log", "Latest 100 security and operational events.", badge="Admin")
    events = list_audit_events(limit=100)
    if events.empty:
        st.info("No audit events found.")
    else:
        st.dataframe(events, width="stretch")


def render_view_as_controls(user: dict) -> None:
    admin_user = actual_user()
    if is_viewing_as_lecturer():
        st.warning(f"Viewing as lecturer: {user.get('lecturer_name', user.get('username'))}. Return to admin when finished.")
        if st.sidebar.button("Return to admin"):
            log_audit_event("admin_view_as_return", user=admin_user, entity_type="lecturer", entity_id=user.get("staff_number"))
            exit_view_as_lecturer(st.session_state)
            st.rerun()
        return
    if not admin_user or admin_user.get("role") != "admin":
        return
    with st.sidebar.expander("View as lecturer"):
        lecturers = list_lecturers()
        if lecturers.empty:
            st.caption("No lecturers available.")
            return
        records = lecturers.to_dict("records")
        staff_numbers = [str(record["staff_number"]) for record in records]
        selected_staff = st.selectbox(
            "Lecturer",
            staff_numbers,
            format_func=lambda value: lecturer_option_label(lecturer_record_by_staff_number(records, value)),
            key="admin_view_as_staff_number",
        )
        if st.button("Start lecturer view", key="admin_start_view_as"):
            lecturer_user = _lecturer_view_user_from_staff_number(selected_staff)
            if lecturer_user is None:
                st.error("Selected lecturer was not found.")
                return
            enter_view_as_lecturer(st.session_state, admin_user, lecturer_user)
            log_audit_event("admin_view_as_start", user=admin_user, entity_type="lecturer", entity_id=selected_staff)
            st.rerun()


def main() -> None:
    init_runtime_db()
    apply_app_theme()
    if is_training():
        render_training_banner()
    if enable_debug_stack_traces():
        st.sidebar.checkbox("Show debug stack traces", key="debug_errors")
    else:
        st.session_state["debug_errors"] = False
    user = current_user()
    now = datetime.now()
    if user and session_expired(st.session_state.get("last_activity_at"), now, session_timeout_minutes()):
        clear_sensitive_session_state(st.session_state)
        st.session_state["session_expired_notice"] = "Session expired. Please log in again."
        st.rerun()
    if not user:
        notice = st.session_state.pop("session_expired_notice", None)
        if notice:
            st.warning(notice)
        page_login()
        return
    st.session_state["last_activity_at"] = now
    render_sidebar_user(user["username"], user["role"], user.get("lecturer_name") or user["username"])
    render_view_as_controls(user)
    if st.sidebar.button("Logout"):
        log_audit_event("logout", user=user)
        st.session_state.pop("auth_user", None)
        exit_view_as_lecturer(st.session_state)
        st.rerun()
    if user.get("must_change_password"):
        page_change_password()
        return

    if user["role"] == "lecturer":
        if st.session_state.pop("force_my_dashboard_after_password_change", False):
            st.session_state["lecturer_navigation"] = "My Dashboard"
        nav_options = lecturer_navigation_options()
        if is_viewing_as_lecturer():
            nav_options = [option for option in nav_options if option != "Change Password"]
            if st.session_state.get("lecturer_navigation") not in nav_options:
                st.session_state["lecturer_navigation"] = "My Dashboard"
        section = st.sidebar.radio(
            "Navigation",
            nav_options,
            key="lecturer_navigation",
        )
        if section == "My Dashboard":
            page_my_dashboard()
        elif section == "My Timetable/Sessions":
            page_my_timetable_sessions()
        elif section == "My Documents":
            page_my_documents()
        else:
            page_change_password()
        return

    st.sidebar.caption(f"Environment: {get_app_env()}")
    if is_production():
        st.sidebar.caption("Production mode")
    section = st.sidebar.radio("Navigation", admin_navigation_options())
    if section == "Home / Dashboard":
        page_dashboard()
    elif section == "Master Data Import":
        page_master_data_import()
    elif section == "Lecturer Entry":
        page_lecturer_entry()
    elif section == "Course and Group Entry":
        page_course_group_entry()
    elif section == "Timetable Entry":
        page_timetable_entry()
    elif section == "Academic Calendar":
        page_academic_calendar()
    elif section == "Student Upload":
        page_student_upload()
    elif section == "Pre-Claim Verification":
        page_preclaim_verification()
    elif section == "Account Management":
        page_account_management()
    elif section == "Audit Log":
        page_audit_log()
    elif section == "Data Inspection":
        page_data_inspection()
    elif section == "Session Generation":
        page_session_generation()
    elif section == "Document Generation":
        page_document_generation()
    elif section == "Change Password":
        page_change_password()
    elif section == "Development" and enable_development_page():
        page_development()
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
