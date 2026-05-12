import sqlite3

from app.anonymise_staging_data import (
    create_anonymised_staging_db,
    table_counts,
    validate_anonymised_db,
)
from app.auth_service import hash_password
from app.database import init_db


def _build_source_db(path):
    init_db(path)
    lecturer_hash, lecturer_salt = hash_password("RealChangedPassword2026")
    admin_hash, admin_salt = hash_password("RealAdminPassword2026")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES ('100718', 'Ms', 'Lonia Nghitotelwa', 'MSc', 'REAL-ID', 'REAL-PAYE',
                    'Real Address', '0810000000', 410, 'Windhoek Main Campus',
                    '2026-01-01', '2026-12-31', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO lecturers (
                staff_number, title, full_name, highest_qualification, id_or_passport_number,
                paye_number, physical_address, contact_number, tariff_per_hour, campus,
                contract_start_date, contract_end_date, active
            )
            VALUES ('1008977', 'Ms', 'Maria Matias', 'MSc', 'REAL-ID-2', 'REAL-PAYE-2',
                    'Real Address 2', '0810000001', 460, 'Windhoek Main Campus',
                    '2026-01-01', '2026-12-31', 1)
            """
        )
        conn.execute(
            "INSERT INTO courses (course_code, course_name, faculty, department, budget_allocation, active) VALUES ('CUS411S', 'Computer User Skills', 'Computing and Informatics', 'Informatics', '0183-0102', 1)"
        )
        conn.execute(
            "INSERT INTO student_groups (group_name, course_id, lecturer_id, campus, study_mode, active) VALUES ('LONIA_GROUP2_FT_SEM1_2026', 1, 1, 'Windhoek Main Campus', 'Full-time', 1)"
        )
        conn.execute(
            "INSERT INTO timetable_entries (lecturer_id, group_id, day_of_week, start_time, end_time, effective_start_date, effective_end_date, active) VALUES (1, 1, 'Monday', '08:00', '09:00', '2026-01-01', '2026-06-30', 1)"
        )
        conn.execute("INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('226173453', 'Haukongo', 'JL', 'Haukongo JL', 1)")
        conn.execute("INSERT INTO students (student_number, surname, initials, full_name, active) VALUES ('2261755170', 'Venasius', 'FPN', 'Venasius FPN', 1)")
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO group_enrolments (student_id, group_id, active) VALUES (2, 1, 1)")
        conn.execute(
            """
            INSERT INTO user_accounts (
                username, password_hash, password_salt, role, lecturer_id,
                must_change_password, active, created_at, updated_at
            )
            VALUES ('100718', ?, ?, 'lecturer', 1, 0, 1, '2026-05-12', '2026-05-12')
            """,
            (lecturer_hash, lecturer_salt),
        )
        conn.execute(
            """
            INSERT INTO user_accounts (
                username, password_hash, password_salt, role, lecturer_id,
                must_change_password, active, created_at, updated_at
            )
            VALUES ('admin', ?, ?, 'admin', NULL, 0, 1, '2026-05-12', '2026-05-12')
            """,
            (admin_hash, admin_salt),
        )
        conn.execute("INSERT INTO audit_logs (username, role, action, details_json, success, created_at) VALUES ('100718', 'lecturer', 'login_success', '{\"name\":\"Lonia\"}', 1, '2026-05-12')")


def test_anonymisation_dry_run_does_not_write_output(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "staging.db"
    _build_source_db(source)

    result = create_anonymised_staging_db(source=source, output=output, dry_run=True)

    assert result["dry_run"] is True
    assert not output.exists()
    assert result["source_modified"] is False


def test_anonymisation_creates_output_preserves_counts_and_source(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "staging.db"
    _build_source_db(source)
    before_counts = table_counts(source)

    result = create_anonymised_staging_db(source=source, output=output, overwrite=True)

    assert output.exists()
    assert result["source_modified"] is False
    assert table_counts(output) == before_counts
    assert table_counts(source) == before_counts


def test_anonymisation_replaces_people_accounts_and_audit_logs(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "staging.db"
    _build_source_db(source)

    create_anonymised_staging_db(source=source, output=output, overwrite=True)

    with sqlite3.connect(output) as conn:
        lecturer_text = "\n".join(row[0] for row in conn.execute("SELECT full_name FROM lecturers").fetchall())
        student_text = "\n".join(row[0] for row in conn.execute("SELECT surname FROM students").fetchall())
        group_text = "\n".join(row[0] for row in conn.execute("SELECT group_name FROM student_groups").fetchall())
        usernames = [row[0] for row in conn.execute("SELECT username FROM user_accounts ORDER BY username").fetchall()]
        password_text = "\n".join(" ".join(str(value) for value in row) for row in conn.execute("SELECT password_hash, password_salt FROM user_accounts").fetchall())
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

    assert "Lonia" not in lecturer_text
    assert "Maria" not in lecturer_text
    assert "Haukongo" not in student_text
    assert "Venasius" not in student_text
    assert "LONIA" not in group_text
    assert "DEMO_GROUP_001" in group_text
    assert "staging_admin" in usernames
    assert "100718" not in usernames
    assert "Staging@2026" not in password_text
    assert "StagingAdmin@2026" not in password_text
    assert audit_count == 0


def test_validate_anonymised_db_passes_for_clean_output(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "staging.db"
    _build_source_db(source)
    create_anonymised_staging_db(source=source, output=output, overwrite=True)

    validation = validate_anonymised_db(output)

    assert validation["valid"] is True
    assert validation["failures"] == []
