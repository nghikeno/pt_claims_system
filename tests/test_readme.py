from pathlib import Path


def test_readme_contains_phase_4_3_wording():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Phase 1 to Phase 4.3 local prototype" in readme
    assert "Phase 4.3 adds lecturer-scoped group management" in readme
    assert "Phase 4.3 Lecturer-scoped group notes" in readme
    assert "Groups can be linked to a specific lecturer and course" in readme
    assert "`staff_number` plus `course_code` plus `group_name` must be unique" in readme
    assert "LECTURER_ALIAS_GROUP_LABEL_SEMESTER_YEAR" in readme
    assert "Manual group-name override is not shown in the normal workflow" in readme
    assert "Phase 6.1 UI cleanup notes" in readme
    assert "Maria Pilot Helper is no longer shown in normal Streamlit navigation" in readme
    assert "cleanup_generic_demo_groups.py --dry-run" in readme
    assert "Phase 7.0 Timetable Entry notes" in readme
    assert "Timetable Entry page was added" in readme
    assert "lecturer-scoped groups" in readme
    assert "pt_claims_before_timetable_save_YYYYMMDD_HHMMSS.db" in readme
    assert "Overlapping timetable entries" in readme
    assert "Phase 7.1 Timetable Entry notes" in readme
    assert "5-minute precision" in readme
    assert "17:15" in readme
    assert "21:25" in readme
    assert "Timetable entries can be updated after capture" in readme
    assert "Adjacent sessions" in readme
    assert "Phase 7.2 Timetable management notes" in readme
    assert "deactivate/reactivate rather than hard delete" in readme
    assert "DELETE TIMETABLE ENTRY" in readme
    assert "Inactive timetable entries do not block new active timetable entries" in readme
    assert "Phase 9.0 Student Upload notes" in readme
    assert "Word attendance sheets can be imported" in readme
    assert "selected target database group is the source of truth" in readme
    assert "mismatches are warnings only" in readme
    assert "pt_claims_before_student_import_YYYYMMDD_HHMMSS.db" in readme
    assert "Attendance registers use active group enrolments" in readme
    assert "Phase 10.0 Authentication and RBAC notes" in readme
    assert "requires login" in readme
    assert "PBKDF2-HMAC" in readme
    assert "auth_bootstrap_lecturers --dry-run" in readme
    assert "auth_create_admin" in readme
    assert "Phase 10.1 Authentication flow and duration notes" in readme
    assert "20:00` to `21:25` session is `1.41" in readme
    assert "truncated to two decimal places" in readme
    assert "Phase 10.2 Professional UI theme notes" in readme
    assert "central Streamlit theme helper" in readme
    assert "does not change database schema" in readme
    assert "navigation rules remain enforced by application logic" in readme
    assert "Phase 10.2.1 UI contrast notes" in readme
    assert "White text is scoped to the dark sidebar" in readme
    assert "Metric cards, tabs, labels, forms" in readme
    assert "Phase 11.0 Cloud readiness and production hardening notes" in readme
    assert "Cloud deployment is not approved for real data yet" in readme
    assert "Local SQLite remains the default" in readme
    assert "PostgreSQL configuration is detected through `DATABASE_URL`" in readme
    assert "Production mode hides development/debug controls" in readme
    assert "Session timeout is configurable" in readme
    assert "Admin password reset is available through Account Management" in readme
    assert "Audit logging records login success/failure" in readme
    assert "Generated document storage supports `local` and `ephemeral`" in readme
    assert "RBAC must be retested before any real-data deployment" in readme
    assert "Phase 11.1 PostgreSQL migration path and anonymised staging notes" in readme
    assert "PostgreSQL support is still partial/scaffolded" in readme
    assert "Real data must not be uploaded to free cloud hosting" in readme
    assert "pt_claims_staging_anonymised.db" in readme
    assert "Staging@2026" in readme
    assert "StagingAdmin@2026" in readme
    assert "python -m app.anonymise_staging_data --dry-run" in readme
    assert "python -m app.staging_export" in readme
    assert "Phase 11.3 Disposable PostgreSQL staging migration notes" in readme
    assert "refuses to use real `data/pt_claims.db`" in readme
    assert "PT_CLAIMS_TEST_DATABASE_URL" in readme
    assert "--confirm-disposable" in readme
    assert "PostgreSQL support remains staging-test tooling" in readme
    assert "Phase 11.3.1 PostgreSQL runtime authentication notes" in readme
    assert "Authentication, audit logging, and admin account-management runtime paths now use the database provider abstraction" in readme
    assert "PostgreSQL runtime paths use `%s` placeholders" in readme
    assert "PostgreSQL auth integration test" in readme
    assert "Phase 11.3.2 PostgreSQL runtime performance notes" in readme
    assert "optional psycopg connection pooling" in readme
    assert "DB_PERF_DEBUG=true" in readme
    assert "Neon Free can scale to zero" in readme
    assert "Dashboard count queries were consolidated" in readme
    assert "Phase 11.4 Deployment readiness checker and staging hardening notes" in readme
    assert "python -m app.deployment_readiness_check" in readme
    assert "--fail-on-block" in readme
    assert "never prints `DATABASE_URL`" in readme
    assert "obsolete DOCX/register draft-formatting warning" in readme
    assert "Theme contrast for form buttons" in readme
    assert "Phase 11.5 Academic Calendar management and login contrast notes" in readme
    assert "admin-only Academic Calendar page" in readme
    assert "time-bound exclusions exclude only sessions whose time range overlaps" in readme
    assert "NUST 2026 reference section" in readme
    assert "Login and password input contrast was fixed centrally" in readme
    assert "Phase 12.0 Pre-Claim Verification notes" in readme
    assert "admin-only Pre-Claim Verification page" in readme
    assert "PASS`, `WARN`, or `BLOCK" in readme
    assert "optional verification CSV export" in readme
    assert "does not generate claim/register documents automatically" in readme
    assert "Phase 13.0 Production usability and operational readiness notes" in readme
    assert "app.claim_period_service" in readme
    assert "May `2026-04-30` to `2026-05-29`" in readme
    assert "View as lecturer mode" in readme
    assert "python -m app.create_demo_workshop_account --dry-run" in readme
    assert "Local use is ready for controlled operational use" in readme
    assert "Real-data full online production is not complete" in readme
    assert "Phase 13.1 Document Generation UI polish notes" in readme
    assert "Generate documents" in readme
    assert "old draft/under-review warning was removed" in readme
    assert "Lecturer document generation does not expose the engine selector" in readme
    assert "Phase 14.0 Production deployment foundation notes" in readme
    assert "deployment readiness checker now separates local controlled use" in readme
    assert "app.document_storage" in readme
    assert "Production with local generated-file storage is blocked" in readme
    assert "docs/production_deployment.md" in readme
    assert "Phase 14.1 S3-compatible document storage and production migration dry-run notes" in readme
    assert "S3-compatible `object_storage` support" in readme
    assert "OBJECT_STORAGE_ACCESS_KEY_ID" in readme
    assert "OBJECT_STORAGE_SECRET_ACCESS_KEY" in readme
    assert "python -m app.production_migration_plan --dry-run" in readme
    assert "does not deploy, upload real data, migrate real data" in readme
    assert "Phase 14.2 live cloud infrastructure smoke-test notes" in readme
    assert "python -m app.cloud_smoke_test --config-only" in readme
    assert "python -m app.cloud_smoke_test --all-dry-run" in readme
    assert "python -m app.cloud_smoke_test --storage-upload-dummy --yes" in readme
    assert "uploads only a tiny dummy text smoke-test file" in readme
    assert "Phase 14.3 real PostgreSQL migration command and backup gate notes" in readme
    assert "python -m app.production_migrate_real_data --dry-run" in readme
    assert "I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES" in readme
    assert "--backup-acknowledged" in readme
    assert "resets PostgreSQL identity sequences" in readme
    assert "Phase 14.3.1 boto3 dependency pinning notes" in readme
    assert "boto3==1.34.162" in readme
    assert "botocore==1.34.162" in readme
    assert "s3transfer==0.10.4" in readme
    assert "Phase 14.4 production runtime download, storage, UI, and performance notes" in readme
    assert "short-lived signed download links" in readme
    assert "Register ZIP downloads remain visible" in readme
    assert "never renders `DATABASE_URL`" in readme
    assert "future lecturer login access" in readme
    assert "Authentication is not implemented yet" in readme
    assert "Phase 4.2 adds browser-based Course and Group Entry" in readme
    assert "Phase 4.2 Course and Group Entry notes" in readme
    assert "Course and Group Entry page was added" in readme
    assert "Courses can be added and updated through the web interface" in readme
    assert "Groups can be added and updated through the web interface" in readme
    assert "`course_code` is unique" in readme
    assert "`group_name` plus `course_code` is unique" in readme
    assert "Groups must be linked to valid courses" in readme
    assert "Students and timetables are still separate future steps" in readme
    assert "Phase 4.1 strengthens the Lecturer Entry page" in readme
    assert "Phase 4.1 Lecturer Entry notes" in readme
    assert "Lecturer Entry is the preferred way to manually capture lecturer details" in readme
    assert "`staff_number` is treated as the unique lecturer identifier" in readme
    assert "Duplicate staff numbers are blocked" in readme
    assert "searched, updated, deactivated, or reactivated" in readme
    assert "Excel import remains available for bulk workflows" in readme
    assert "Phase 4.0 adds a Lecturer Entry page" in readme
    assert "Phase 4.0 Lecturer Entry notes" in readme
    assert "adding and updating lecturer records through a web form" in readme
    assert "Bank details are explicitly rejected" in readme
    assert "ID/passport and PAYE values may be stored only because claim generation requires them" in readme
    assert "Excel import remains available for bulk import" in readme
    assert "No authentication yet" in readme
    assert "Phase 3.9 improves OCR contract parsing cleanup" in readme
    assert "strips noisy labels" in readme
    assert "--save-ocr-text" in readme
    assert "Raw OCR text is not saved by default" in readme
    assert "Saved OCR debug text has detected bank-detail lines removed" in readme
    assert "Phase 3.8 adds OCR-assisted scanned-contract review workbooks" in readme
    assert "Phase 3.8 adds OCR-assisted scanned-contract review workbooks" in readme
    assert "OCR-assisted contract review" in readme
    assert "OCR output is draft only" in readme
    assert "OCR results are not imported directly into the database" in readme
    assert "app.data_extraction.ocr_contract_extract" in readme
    assert "app.data_extraction.contract_review_workbook" in readme
    assert "ocr_contract_review.xlsx" in readme
    assert "real_master_data_from_review.xlsx" in readme
    assert "Phase 3.7 adds a local contract/agreement extraction helper" in readme
    assert "Phase 3.7 contract helper" in readme
    assert "only for preparing the `Lecturers` and known `Courses` sheets" in readme
    assert "Bank details are ignored and must never be stored" in readme
    assert "Groups, Students, Group_Enrolments, Timetable, or Academic_Calendar" in readme
    assert "app.data_extraction.contract_extract" in readme
    assert "app.data_extraction.populate_master_workbook" in readme
    assert "real_master_data_draft.xlsx" in readme
    assert "Phase 3.6 integrates the preferred v2 `docxtpl` document generator" in readme
    assert "v2 docxtpl, recommended" in readme
    assert "legacy generators for comparison" in readme
    assert "data/generated_v2/<year>/<month>/<staff_number>/" in readme
    assert "Attendance registers are generated as separate DOCX files" in readme
    assert "Phase 3.5 adds dynamic title marks" in readme
    assert "{{ title_prof_mark }}" in readme
    assert "{{ title_dr_mark }}" in readme
    assert "{{ title_mr_mark }}" in readme
    assert "{{ title_ms_mark }}" in readme
    assert "Phase 3.4 adds an experimental fixed-table claim template" in readme
    assert "manual_claim_template_v2_fixed_table.docx" in readme
    assert "template_layout_diagnostics" in readme
    assert "create_fixed_claim_template" in readme
    assert "Phase 3.3 hardens the separate `docxtpl` proof-of-concept path" in readme
    assert "Phase 3.2 uses manually placeholder-marked institutional templates" in readme
    assert "render_provenance.txt" in readme
    assert "manual_templates --diagnose" in readme
    assert "--debug-template-text" in readme
    assert "manual_claim_template_v2.docx" in readme
    assert "manual_register_template_v2.docx" in readme
    assert "manual files into the render template paths" in readme
    assert "Phase 3.0 docxtpl proof of concept" in readme
    assert "Phase 3.1 converts user-approved institutional Word files" in readme
    assert "user_claim_source.docx" in readme
    assert "user_register_source.docx" in readme
    assert "--from-user-sources --overwrite" in readme
    assert "explicit placeholders" in readme
    assert "app_docxtpl.render_documents_v2" in readme
    assert "Phase 2.6 export feedback bug-fix notes" in readme
    assert "rendered directly below the clicked buttons" in readme
    assert "Button clicked at" in readme
    assert "Real data protection" in readme
    assert "PT_CLAIMS_DB_PATH" in readme
    assert "temporary SQLite database" in readme
    assert "I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA" in readme
    assert "Lecturer Entry creates a timestamped database backup" in readme
    assert "lecturers_export_YYYYMMDD_HHMMSS.csv" in readme
    assert "Phase 2.5 persistent export feedback notes" in readme
    assert "persist success or error messages" in readme
    assert "Users no longer need to check Windows Explorer" in readme
    assert "Phase 2.4 export feedback notes" in readme
    assert "clear success or error feedback" in readme
    assert "direct browser download buttons" in readme
    assert "Phase 2.3 UI workflow notes" in readme
    assert "guided workflow" in readme
    assert "Dry-run validation should be completed and reviewed before import" in readme
    assert "backup should be created before importing real data" in readme
    assert "YYYY-MM-DD" in readme
    assert "Phase 2.2 Session Generation notes" in readme
    assert "cleaner administrative view" in readme
    assert "filters affect the visible table only" in readme
    assert "Grouped summaries by course and group" in readme
    assert "Phase 2.1 privacy notes" in readme
    assert "Session Generation UI hides sensitive lecturer fields" in readme
    assert "exports must be reviewed before sharing" in readme
    assert "Streamlit interface" in readme
    assert "streamlit run app_ui/streamlit_app.py" in readme
    assert "user-corrected golden DOCX templates" in readme
    assert "copying the golden template and replacing only dynamic" in readme
    assert "golden_claim_template.docx" in readme
    assert "golden_attendance_register_template.docx" in readme
    assert "must not redesign" in readme
    assert "registers/" in readme
    assert "dd-mm-yy" in readme
    assert "only enrolled student rows" in readme
    assert "python -m app.dev_reset" in readme
    assert "Do not run `dev_reset` on real data." in readme
    assert "Do not run `seed_data` on real data." in readme
    assert "Do not run `pytest` as part of real-use workflow" in readme
    assert "Safe real data entry workflow" in readme
    assert "Confirm a backup was created under `data/backups/`" in readme
    assert "Confirm the CSV exists under `data/exports/`" in readme
    assert "Safety check commands" in readme


def test_s3_dependencies_are_pinned_exactly():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "boto3==1.34.162" in requirements
    assert "botocore==1.34.162" in requirements
    assert "s3transfer==0.10.4" in requirements
    assert not any(line.startswith("boto3>=") or line.startswith("boto3<") for line in requirements)
