from app.auth_service import AccessDeniedError, authorize_lecturer_access, create_or_update_user_account, authenticate_user, lecturer_id_for_staff_number
from app.database import get_connection, init_db
from app.dev_reset import dev_reset
from app_ui.navigation import admin_navigation_options, lecturer_navigation_options
from app_ui.session_security import can_start_view_as, effective_user, enter_view_as_lecturer, exit_view_as_lecturer


def insert_two_lecturers():
    init_db()
    with get_connection() as conn:
        for staff, name in [("100718", "Lonia Nghitotelwa"), ("1001259", "Mervin Mokhatu")]:
            conn.execute(
                """
                INSERT OR IGNORE INTO lecturers (
                    staff_number, title, full_name, highest_qualification, id_or_passport_number,
                    paye_number, physical_address, contact_number, tariff_per_hour, campus,
                    contract_start_date, contract_end_date, active
                )
                VALUES (?, 'Ms', ?, 'MSc', 'ID', 'PAYE', 'Address', '0810000000', 410,
                        'Windhoek Main Campus', '2026-01-01', '2026-12-31', 1)
                """,
                (staff, name),
            )


def test_lecturer_navigation_excludes_admin_pages():
    nav = lecturer_navigation_options()

    for page in [
        "Data Inspection",
        "Student Upload",
        "Lecturer Entry",
        "Course and Group Entry",
        "Timetable Entry",
        "Academic Calendar",
        "Pre-Claim Verification",
    ]:
        assert page not in nav


def test_lecturer_cannot_authorize_other_lecturer_documents():
    dev_reset()
    insert_two_lecturers()
    lonia_id = lecturer_id_for_staff_number("100718")
    mervin_id = lecturer_id_for_staff_number("1001259")
    create_or_update_user_account("100718", "Nust@2026", "lecturer", lonia_id)
    user = authenticate_user("100718", "Nust@2026")

    assert authorize_lecturer_access(user, lonia_id) == lonia_id
    try:
        authorize_lecturer_access(user, mervin_id)
        assert False, "Expected AccessDeniedError"
    except AccessDeniedError:
        pass


def test_admin_navigation_can_include_admin_pages():
    nav = admin_navigation_options()

    assert "Data Inspection" in nav
    assert "Student Upload" in nav
    assert "Lecturer Entry" in nav
    assert "Pre-Claim Verification" in nav


def test_production_admin_navigation_excludes_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_DEVELOPMENT_PAGE", "true")

    assert "Development" not in admin_navigation_options()


def test_development_admin_navigation_can_include_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_DEVELOPMENT_PAGE", "true")

    assert "Development" in admin_navigation_options()


def test_admin_can_enter_and_return_from_view_as_mode():
    state = {}
    admin = {"id": 1, "username": "admin", "role": "admin"}
    lecturer = {"username": "view-as:900001", "role": "lecturer", "staff_number": "900001", "lecturer_id": 9}

    enter_view_as_lecturer(state, admin, lecturer)

    assert state["view_as_admin_user"] == admin
    assert effective_user(state)["role"] == "lecturer"
    assert effective_user(state)["staff_number"] == "900001"

    exit_view_as_lecturer(state)
    assert "view_as_lecturer_user" not in state
    assert "view_as_admin_user" not in state


def test_lecturer_cannot_enter_view_as_mode():
    state = {}
    lecturer = {"username": "100718", "role": "lecturer", "staff_number": "100718", "lecturer_id": 1}

    assert can_start_view_as(lecturer) is False
    try:
        enter_view_as_lecturer(state, lecturer, lecturer)
        assert False, "Expected PermissionError"
    except PermissionError:
        pass
