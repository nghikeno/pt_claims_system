# pt_claims_system

Phase 1 to Phase 4.3 local prototype for generating part-time lecturer attendance register and claim sessions.

This prototype includes SQLite storage, sample seed data, master data Excel intake, student lists, group enrolments, monthly session generation, academic-calendar exclusions, clash detection, hours and claim amount calculations, Excel export, template-driven DOCX generation, verification checklist export, and a simple local Streamlit interface. Phase 1.3.10 treats user-corrected golden DOCX templates as locked formatting source files: generation copies the golden template and replaces demo text only. Phase 2.6 fixes Streamlit Session Generation export feedback in the visible page flow without changing backend calculations. Phase 3.9 improves OCR contract parsing cleanup while keeping OCR output draft-only. Phase 4.3 adds lecturer-scoped group management while keeping authentication, students, and timetables as separate future steps. It does not import OCR results directly, change backend session generation, add authentication, generate PDFs, or add bank details.

## Setup

```powershell
cd pt_claims_system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Dangerous development commands

`dev_reset` and `seed_data` are destructive development commands. Do not run them on real data. They are documented here only so developers understand what they are and why they are dangerous.

Do not run:

- `python -m app.dev_reset`
- `python -m app.seed_data`

against `data/pt_claims.db` during real use.

`dev_reset` deletes/rebuilds the database. `seed_data` deletes existing master-data rows and writes demo rows. Both commands are blocked against the real database unless explicit confirmation flags and the exact phrase `I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA` are supplied.

For isolated development only, set `PT_CLAIMS_DB_PATH` to a disposable database path before using these commands:

```powershell
$env:PT_CLAIMS_DB_PATH="$env:TEMP\pt_claims_dev.db"
python -m app.dev_reset
```

The older seed command creates the original deliberate clash dataset used by tests. Use it only with a disposable `PT_CLAIMS_DB_PATH`:

```powershell
$env:PT_CLAIMS_DB_PATH="$env:TEMP\pt_claims_seed_demo.db"
python -m app.seed_data
```

The SQLite database is created at:

```text
data/pt_claims.db
```

## Generate the master data template

```powershell
python -m app.master_data_template
```

The workbook is created at:

```text
data/templates/master_data_template.xlsx
```

This file is a blank/sample starting workbook. For real use, copy it, complete the copy with approved real master data, save it under a new filename such as `path/to/real_master_data.xlsx`, and run dry-run validation against that completed workbook.

## Real-use import workflow

```powershell
python -m app.import_master_data --file path/to/real_master_data.xlsx --dry-run
```

The import validates all sheets before writing anything to the database. Running the same import repeatedly is idempotent and will update matching natural keys instead of creating duplicate records.

For real use, import master data from Excel instead of running `dev_reset` or `seed_data`.

Recommended real-use workflow:

```powershell
python -m app.master_data_template
python -m app.import_master_data --file path/to/real_master_data.xlsx --dry-run
python -m app.backup_database
python -m app.import_master_data --file path/to/real_master_data.xlsx --yes
python -m app.inspect_data --summary
python -m app.preflight --file path/to/real_master_data.xlsx --year 2026 --month 2
python -m app.session_generator --lecturer-id <staff_number> --year 2026 --month 2 --export
python -m app.document_generator --lecturer-id <staff_number> --year 2026 --month 2
```

Use `--dry-run` before importing real data. Use `python -m app.backup_database` before importing into a database that already contains records.

## Master data sheets

- `Lecturers`: lecturer claim/register details and internal contract period.
- `Courses`: course, faculty, department, and budget allocation records.
- `Groups`: teaching groups linked to courses.
- `Students`: student list using dummy-safe identifiers.
- `Group_Enrolments`: links students to one or more groups.
- `Timetable`: lecturer teaching times linked to groups and courses.
- `Academic_Calendar`: include/exclude calendar periods such as holidays, recess, closures, and special events.

## Generate February 2026 sessions

```powershell
python -m app.session_generator --lecturer-id 1 --year 2026 --month 2
```

To also create an Excel workbook:

```powershell
python -m app.session_generator --lecturer-id 1 --year 2026 --month 2 --export
```

Exports are written to:

```text
data/exports/
```

## Generate monthly documents

Phase 1.3.10 uses strict copy-and-replace DOCX template filling from user-corrected golden templates by default. Copy the manually corrected editable Word templates to:

```text
data/docx_templates/golden_claim_template.docx
data/docx_templates/golden_attendance_register_template.docx
```

The golden templates may be filled demo files. Generated outputs are made by copying the golden template and replacing only dynamic lecturer, claim, group, date, time, and student values in the copy. The golden templates are never edited directly. In template mode, the system must not redesign the claim or register layouts, resize tables, add Field/Value sections, add visible Register IDs, add extra metadata, or combine multiple registers.

Attendance registers are generated as separate DOCX files under `data/generated/<year>/<month>/<staff_number>/registers/`. Template mode does not generate a combined `attendance_registers_<staff>_<year>_<month>.docx` file.

Attendance registers now use only enrolled student rows, plus at most one optional blank row. If a department later wants fixed 37-row registers, that can be added as a setting; the current behaviour is compact so the lecturer signature area stays close to the table.

Attendance register date cells use `dd-mm-yy` to avoid clipping in the narrow signature columns.

Visual approval still depends on the user opening the generated DOCX files and confirming that the golden-template layout is preserved.

Inspect the templates:

```powershell
python -m app.template_inspector --file data/docx_templates/golden_claim_template.docx
python -m app.template_inspector --file data/docx_templates/golden_attendance_register_template.docx
python -m app.template_inspector --file data/docx_templates/golden_claim_template.docx --map-claim
python -m app.template_inspector --file data/docx_templates/golden_attendance_register_template.docx --map-register
python -m app.template_inspector --file data/docx_templates/golden_claim_template.docx --map-claim-cells
python -m app.template_inspector --file data/docx_templates/golden_attendance_register_template.docx --map-register-cells
```

If the template structure changes, rerun `template_inspector` with the mapping options before generating documents.

Clean no-clash demo for isolated development only:

```powershell
$env:PT_CLAIMS_DB_PATH="$env:TEMP\pt_claims_doc_demo.db"
python -m app.dev_reset
python -m app.document_generator --lecturer-id 200001 --year 2026 --month 2 --layout-mode template --strict-template
```

Clash demo:

```powershell
python -m app.document_generator --lecturer-id 1 --year 2026 --month 2
```

If timetable clashes are detected, the system blocks DOCX generation and still creates the verification checklist. To generate draft documents anyway:

```powershell
python -m app.document_generator --lecturer-id 1 --year 2026 --month 2 --allow-clashes --layout-mode template --strict-template
```

Generated files are written to:

```text
data/generated/<year>/<month>/<staff_number>/
```

The DOCX files are generated from approved timetable sessions and academic-calendar exclusions. The default generator now edits the official DOCX templates in `data/docx_templates` in place. Generated DOCX files are still drafts until official formatting is approved. Scanned PDF verification is still not part of this phase.

## Maria Matias April 2026 pilot

This pilot is reconstructed from a submitted claim, not the official approved timetable. It is included to test the real-use workflow against a claim-based April 2026 example. Sensitive lecturer details use placeholders only, and all students are dummy records. Do not treat this pilot workbook as an approved institutional timetable.

The original claim includes an ICT Distance session described as Test. For this prototype, that session is treated as Lecture because the tariff and verification rules are the same. The system currently treats all generated claimable teaching sessions as Lecture. Activity-type separation can be added later only if Payroll or policy requires separate reporting.

Create the pilot workbook:

```powershell
python -m app.create_maria_pilot_workbook
```

Validate and run the workflow manually:

```powershell
python -m app.import_master_data --file data/pilots/maria_matias_april_2026_master_data.xlsx --dry-run
python -m app.backup_database
python -m app.import_master_data --file data/pilots/maria_matias_april_2026_master_data.xlsx --yes
python -m app.session_generator --lecturer-id 1008977 --year 2026 --month 4 --export
python -m app.document_generator --lecturer-id 1008977 --year 2026 --month 4 --layout-mode template --strict-template
```

To compare against the previous generated layout:

```powershell
python -m app.document_generator --lecturer-id 1008977 --year 2026 --month 4 --layout-mode generated
```

Optional helper:

```powershell
python -m app.run_maria_pilot
python -m app.run_maria_pilot --import
```

Expected April 2026 pilot results:

- 69 sessions
- 94.00 hours
- 43240.00 total amount
- 0 clashes

## Phase 3.0 docxtpl proof of concept

Phase 3.0 added a separate experimental document generation path using `docxtpl`. It does not replace the old DOCX generator yet, and the old generator remains unchanged. Backend session generation, Excel exports, verification checklist logic, database schema, and Streamlit UI integration remain unchanged.

The v2 proof of concept uses explicit placeholders instead of paragraph indexes, table coordinates, arbitrary text replacement, and tab-based layout edits. It creates editable DOCX files under `data/generated_v2/` for comparison and visual inspection before any adoption decision.

The Maria render examples require the Maria pilot workbook to be imported first.

Phase 3.1 converts user-approved institutional Word files into docxtpl templates. The simple Phase 3.0 templates are proof-of-concept only and are not HR-approved.

Provide these user-approved source files:

```text
data/docx_templates_v2/user_claim_source.docx
data/docx_templates_v2/user_register_source.docx
```

Create the experimental placeholder templates:

```powershell
python -m app_docxtpl.create_v2_templates
```

Overwrite the experimental templates if you intentionally want to recreate them:

```powershell
python -m app_docxtpl.create_v2_templates --overwrite
```

Create v2 templates from the user-approved institutional sources:

```powershell
python -m app_docxtpl.create_v2_templates --from-user-sources --overwrite
```

Phase 3.2 uses manually placeholder-marked institutional templates as the preferred v2 source. Place the user-edited files at:

```text
data/docx_templates_v2/manual_claim_template_v2.docx
data/docx_templates_v2/manual_register_template_v2.docx
```

The v2 renderer copies those manual files into the render template paths before rendering:

```text
data/docx_templates_v2/claim_template_v2.docx
data/docx_templates_v2/attendance_register_template_v2.docx
```

The manual template sources are treated as read-only. Phase 3.3 always copies those manual files immediately before rendering and verifies that the copied render-template hashes match the manual source hashes. Each render writes `render_provenance.txt` under the generated output folder so you can see exactly which template files, hashes, modified times, and output paths were used.

Phase 3.3 hardens the separate `docxtpl` proof-of-concept path without changing backend calculations or document data.

If manual template edits do not appear in generated output, run:

```powershell
python -m app_docxtpl.manual_templates --diagnose
python -m app_docxtpl.render_documents_v2 --lecturer-id 1008977 --year 2026 --month 4 --debug-template-text
```

Visual inspection is still required after rendering.

Phase 3.4 confirms that the manual template is being used correctly, but the claim alignment issue can still occur when long replacement values are inserted into ordinary paragraphs that use tabs or spaces. Word reflows those paragraphs, which can move right-hand fields such as Budget Allocation, Tariff per hour, PAYE No., and Tel. no. Phase 3.4 introduces an experimental fixed-table claimant-details template:

Phase 3.4 adds an experimental fixed-table claim template for the docxtpl proof-of-concept path.

```text
data/docx_templates_v2/manual_claim_template_v2_fixed_table.docx
```

The fixed-table template keeps the same claim data and claim-row logic, but places claimant details in fixed cells so left and right fields stay aligned more reliably. Visual inspection is still required.

Phase 3.5 adds dynamic title marks from the lecturer title stored in the database. The manual claim template should place these placeholders inside the title boxes:

```text
{{ title_prof_mark }}
{{ title_dr_mark }}
{{ title_mr_mark }}
{{ title_ms_mark }}
```

Only the matching title receives `X`; unknown titles leave all title marks blank.

Phase 3.6 integrates the v2 `docxtpl` renderer into the Streamlit Document Generation page. The recommended engine is `v2 docxtpl, recommended`; legacy template and generated-layout engines remain available for comparison only and may not preserve institutional formatting.

Phase 3.6 integrates the preferred v2 `docxtpl` document generator into the Streamlit Document Generation page.

Phase 3.6 keeps legacy generators for comparison.

The v2 Streamlit workflow uses manually edited institutional templates from:

```text
data/docx_templates_v2/manual_claim_template_v2.docx
data/docx_templates_v2/manual_register_template_v2.docx
```

Generated v2 files are saved under:

```text
data/generated_v2/<year>/<month>/<staff_number>/
```

Attendance registers are generated as separate DOCX files under the `registers/` folder. The UI also creates a ZIP of the register DOCX files for browser download.

## Phase 3.7 contract helper

Phase 3.7 adds a local helper for drafting master data from lecturer contract/agreement PDFs. This helper is only for preparing the `Lecturers` and known `Courses` sheets. It is not a replacement for human review.

Phase 3.7 adds a local contract/agreement extraction helper for drafting only the Lecturers and Courses sheets.

Bank details are ignored and must never be stored. If bank details are detected, the console reports only `Bank details detected and ignored.` Missing or uncertain values are left blank.

The helper does not populate Groups, Students, Group_Enrolments, Timetable, or Academic_Calendar from contracts. Those sheets must be completed from approved group, enrolment, timetable, and calendar sources.

Extract one contract to JSON:

```powershell
python -m app.data_extraction.contract_extract --file "data/source_contracts/Signed Parttime Agreement - Matia M.pdf"
```

Populate a draft real-use workbook:

```powershell
python -m app.data_extraction.populate_master_workbook --contracts-dir data/source_contracts --output data/real_imports/real_master_data_draft.xlsx
```

Review `data/real_imports/real_master_data_draft.xlsx` carefully before importing it. Real master data must still go through dry-run validation, backup, and human review.

## Phase 3.8 OCR-assisted contract review

Scanned contracts require OCR-assisted review. OCR output is draft only and must be reviewed manually before any import workflow. OCR results are not imported directly into the database.

Phase 3.8 adds OCR-assisted scanned-contract review workbooks as draft helpers only.

Bank details are detected and ignored. Only lecturer and known course data are drafted from contracts. Groups, students, enrolments, and timetables remain manual/approved-data inputs.

Create an OCR-assisted review workbook:

```powershell
python -m app.data_extraction.ocr_contract_extract --contracts-dir data/source_contracts --output data/real_imports/ocr_contract_review.xlsx
```

Convert reviewed or approved rows into a master data workbook:

```powershell
python -m app.data_extraction.contract_review_workbook --review-file data/real_imports/ocr_contract_review.xlsx --output data/real_imports/real_master_data_from_review.xlsx
```

If OCR dependencies are not available, the helper creates a manual review workbook with blank fields. Review every row before creating or importing real master data.

Phase 3.9 improves OCR parser cleanup for noisy scanned-contract text. It strips noisy labels from staff numbers, titles, names, contact numbers, ID/passport values, PAYE/income tax values, contract periods, course codes, faculty/department values, and tariff fields where the value is clear. OCR remains draft-only and must be manually reviewed.

Raw OCR text is not saved by default. For local debugging only, use:

```powershell
python -m app.data_extraction.ocr_contract_extract --contracts-dir data/source_contracts --output data/real_imports/ocr_contract_review.xlsx --save-ocr-text
```

Saved OCR debug text has detected bank-detail lines removed where possible. Bank details are still ignored and must never be imported.

Diagnose the original manual claim template:

```powershell
python -m app_docxtpl.template_layout_diagnostics --file data/docx_templates_v2/manual_claim_template_v2.docx
```

Create the fixed-table claim template:

```powershell
python -m app_docxtpl.create_fixed_claim_template
```

Render the Maria claim with the fixed-table template:

```powershell
python -m app_docxtpl.render_claim_v2 --lecturer-id 1008977 --year 2026 --month 4 --template data/docx_templates_v2/manual_claim_template_v2_fixed_table.docx
```

Render the Maria Matias April 2026 proof-of-concept claim:

```powershell
python -m app_docxtpl.render_claim_v2 --lecturer-id 1008977 --year 2026 --month 4
```

Render the Maria Matias April 2026 proof-of-concept attendance registers:

```powershell
python -m app_docxtpl.render_register_v2 --lecturer-id 1008977 --year 2026 --month 4
```

Render both v2 document types:

```powershell
python -m app_docxtpl.render_documents_v2 --lecturer-id 1008977 --year 2026 --month 4
```

This proof of concept is for comparing output quality only. The generated v2 DOCX files should be visually inspected before deciding whether to replace the current document generation path.

## Run tests, development only

Do not run tests as part of real data-entry workflow. For development, confirm database isolation first:

```powershell
pytest tests/test_database_isolation.py -q
pytest -q
```

## Streamlit interface

Install dependencies and run the local prototype UI:

```powershell
pip install -r requirements.txt
streamlit run app_ui/streamlit_app.py
```

The Streamlit interface now requires authentication. Admin users can manage lecturers, courses, lecturer-scoped groups, timetable records, academic calendar exclusions, student uploads, session generation, document generation, account management, audit logs, and data inspection. Lecturer users see only their own dashboard, timetable/session views, documents, and password-change page.

The verified v2 `docxtpl` document path is the normal document-generation route. Do not run `dev_reset`, `seed_data`, or broad development tests as part of real data-entry workflow.

Phase 4.0 Lecturer Entry notes:

- Phase 4.0 adds a Lecturer Entry page for manually adding and updating lecturer records.
- The Streamlit UI includes a Lecturer Entry page for adding and updating lecturer records through a web form.
- Bank details are explicitly rejected and must not be entered or stored.
- ID/passport and PAYE values may be stored only because claim generation requires them.
- Confirmation panels show non-sensitive lecturer details and mask sensitive values.
- Excel import remains available for bulk import.
- No authentication yet, so this remains a local prototype.

Phase 4.1 Lecturer Entry notes:

- Phase 4.1 strengthens the Lecturer Entry page so staff number is treated as the unique lecturer identifier.
- Lecturer Entry is the preferred way to manually capture lecturer details without relying on OCR workbooks or manual Excel editing.
- `staff_number` is treated as the unique lecturer identifier.
- Duplicate staff numbers are blocked when adding lecturers.
- Existing lecturers can be searched, updated, deactivated, or reactivated.
- The Existing Lecturers tab shows a searchable non-sensitive lecturer list.
- Bank details are rejected.
- Excel import remains available for bulk workflows, but it is not required for lecturer entry.

Phase 4.2 Course and Group Entry notes:

- Phase 4.2 adds browser-based Course and Group Entry while keeping students and timetables separate future steps.
- A Course and Group Entry page was added to the Streamlit interface.
- Courses can be added and updated through the web interface.
- Groups can be added and updated through the web interface.
- `course_code` is unique.
- `group_name` plus `course_code` is unique.
- Groups must be linked to valid courses.
- Courses and groups can be deactivated or reactivated instead of deleted.
- Students and timetables are still separate future steps.

Phase 4.3 Lecturer-scoped group notes:

- Lecturer-scoped group management was added.
- Groups can be linked to a specific lecturer and course.
- `staff_number` plus `course_code` plus `group_name` must be unique for lecturer-scoped groups.
- Suggested group names follow `LECTURER_ALIAS_GROUP_LABEL_SEMESTER_YEAR`.
- The lecturer alias is derived automatically from the selected lecturer's first meaningful name.
- The generated group name updates from lecturer alias, group label, semester, and year, and is saved directly.
- Manual group-name override is not shown in the normal workflow.
- The nullable `lecturer_id` on groups prepares the system for future lecturer login access where lecturers see only their own groups.
- Authentication is not implemented yet.

Phase 6.1 UI cleanup notes:

- The Maria Pilot Helper is no longer shown in normal Streamlit navigation. Backend pilot scripts remain legacy/development utilities.
- Old generic demo groups with `lecturer_id IS NULL` can be reviewed with `python tools/cleanup_generic_demo_groups.py --dry-run`.
- The generic-group cleanup script deletes linked demo timetable entries first and creates `data/pt_claims_BEFORE_GENERIC_GROUP_CLEANUP_20260511.db` only when run with `--yes`.
- Review dry-run output before any cleanup is applied.

Phase 7.0 Timetable Entry notes:

- A Timetable Entry page was added to Streamlit for controlled real-data timetable capture.
- Timetable entries must be linked to lecturer-scoped groups where `lecturer_id IS NOT NULL`.
- Generic groups are not used in the Timetable Entry workflow.
- The UI filters groups by selected lecturer, then infers the course from the selected group.
- A database backup named `pt_claims_before_timetable_save_YYYYMMDD_HHMMSS.db` is created before each timetable save.
- Duplicate timetable entries are blocked.
- Overlapping timetable entries for the same lecturer or same group are blocked to prevent claim-generation clashes.
- Timetable entries are deactivated/reactivated in later workflows; they should not be deleted for routine corrections.

Phase 7.1 Timetable Entry notes:

- Timetable time inputs support 5-minute precision.
- Real institutional times such as `17:15`, `18:35`, `18:40`, `20:00`, and `21:25` are supported.
- Timetable entries can be updated after capture.
- Updates are validated and backed up before saving.
- Duplicates and overlaps remain blocked.
- Adjacent sessions such as `18:40` to `20:00` and `20:00` to `21:25` are allowed.

Phase 7.2 Timetable management notes:

- Timetable records can be managed after capture from the Timetable Entry page.
- Normal correction should use deactivate/reactivate rather than hard delete.
- Hard delete is available only for mistaken entries and requires the exact confirmation phrase `DELETE TIMETABLE ENTRY`.
- Backups are created before update, deactivate, reactivate, and delete actions.
- Reactivation is blocked if it would create an active duplicate or overlap.
- Inactive timetable entries do not block new active timetable entries.

Phase 9.0 Student Upload notes:

- Students are uploaded after lecturer-scoped groups and timetables are created.
- Word attendance sheets can be imported from the Student Upload page.
- The selected target database group is the source of truth; Word header fields are used for validation and warnings.
- Historical Word course, lecturer, group, date, time, and footer mismatches are warnings only; student rows are the only imported data.
- Imports are validated before writing and require confirmation of the Word GROUP to database group mapping.
- A backup named `pt_claims_before_student_import_YYYYMMDD_HHMMSS.db` is created before student import.
- Bank details are rejected and must not be uploaded or stored.
- Student enrolments can be deactivated/reactivated, with backups before enrolment updates.
- Attendance registers use active group enrolments and active students for the selected lecturer-scoped group.

Phase 10.0 Authentication and RBAC notes:

- Streamlit now requires login before any system page is shown.
- Lecturer usernames are their staff numbers, and lecturer accounts are linked to `lecturers.id`.
- Passwords are stored as salted PBKDF2-HMAC hashes; plaintext passwords are not stored.
- Lecturer accounts bootstrapped with `Nust@2026` must change password at first login.
- Lecturer role navigation is limited to `My Dashboard`, `My Timetable/Sessions`, `My Documents`, and `Change Password`.
- Lecturers can only access their own groups, timetable/session views, and v2 generated documents.
- Admin accounts are created explicitly with `python -m app.auth_create_admin --username admin --password "<chosen_password>" --yes`.
- Lecturer bootstrap supports `python -m app.auth_bootstrap_lecturers --dry-run` and `python -m app.auth_bootstrap_lecturers --yes`.

Phase 10.1 Authentication flow and duration notes:

- Forced first-login password changes redirect lecturers to `My Dashboard` and show `Password successfully changed.` once.
- The lecturer remains logged in after changing the default password.
- Claimable hours are truncated to two decimal places from total minutes, not rounded.
- A `20:00` to `21:25` session is `1.41` claimable hours.
- Amount calculations use the same truncated claimable session hours.

Phase 10.2 Professional UI theme notes:

- A central Streamlit theme helper adds a professional light administrative interface.
- Login, lecturer pages, admin pages, sidebar identity, cards, buttons, and data tables now share consistent styling.
- The refresh does not change database schema, business logic, RBAC, document generation, or DOCX templates.
- Lecturer and admin navigation rules remain enforced by application logic, not by CSS.

Phase 10.2.1 UI contrast notes:

- Contrast and readability issues from the professional theme refresh were fixed.
- White text is scoped to the dark sidebar/navy blocks, while light content areas use dark readable text.
- Metric cards, tabs, labels, forms, and table surroundings use readable light-background colours.
- This fix does not change database schema, RBAC, business logic, document generation, or DOCX templates.

Phase 11.0 Cloud readiness and production hardening notes:

- Cloud deployment is not approved for real data yet. Free cloud hosting should be used only with anonymised staging/demo data.
- Local SQLite remains the default when `DATABASE_URL` is not configured. SQLite files and local `data/` folders are not safe persistent storage for real cloud deployment.
- PostgreSQL configuration is detected through `DATABASE_URL`; full PostgreSQL migration and validation are a later production step.
- Secrets must be supplied through environment variables or Streamlit secrets. Do not commit `.streamlit/secrets.toml`, `.env`, or live database credentials.
- `APP_ENV` supports `development`, `staging`, and `production`.
- Production mode hides development/debug controls and keeps admin-only pages restricted to admins.
- Session timeout is configurable through `SESSION_TIMEOUT_MINUTES` and defaults to 30 minutes.
- Admin password reset is available through Account Management; reset passwords are hashed and force password change at next login.
- Audit logging records login success/failure, logout, password changes, admin password resets, and v2 document generation without storing plaintext passwords or secrets.
- Generated document storage supports `local` and `ephemeral` modes through `GENERATED_FILE_MODE`. Cloud deployments should not rely on local generated files surviving restarts.
- Local SQLite backups under `data/backups/` are for local mode only. Cloud PostgreSQL backups must be configured with the database provider.
- Object storage for durable generated documents, signed download links, and formal retention policies remain future production work.
- RBAC must be retested before any real-data deployment.

Phase 11.1 PostgreSQL migration path and anonymised staging notes:

- SQLite remains the local default when `DATABASE_URL` is absent.
- PostgreSQL mode is detected from `postgresql://` and `postgresql+psycopg://` URLs, and `psycopg` is declared for future PostgreSQL testing.
- PostgreSQL support is still partial/scaffolded. The schema and service layer still contain SQLite-specific areas that must be migrated and tested before production use.
- Real data must not be uploaded to free cloud hosting.
- An anonymised staging database can be generated at `data/staging/pt_claims_staging_anonymised.db`.
- The staging dataset replaces lecturer names, staff numbers, student numbers, student names, sensitive lecturer fields, user accounts, and audit logs with demo-safe values.
- Staging passwords are demo-only: lecturer accounts use `Staging@2026`, the staging admin uses `StagingAdmin@2026`, and all staging accounts must change password on first login.
- A staging package can be created without real `data/pt_claims.db`, backups, exports, generated documents, `.env`, or `.streamlit/secrets.toml`.
- Real deployment still requires tested PostgreSQL migration, provider backups, object storage for documents, HTTPS/domain/access review, and institutional approval if real data is used.

Create and validate anonymised staging data:

```powershell
python -m app.anonymise_staging_data --dry-run
python -m app.anonymise_staging_data --output data/staging/pt_claims_staging_anonymised.db --overwrite
python -m app.anonymise_staging_data --validate data/staging/pt_claims_staging_anonymised.db
```

Prepare a staging package:

```powershell
python -m app.staging_export
```

Phase 11.3 Disposable PostgreSQL staging migration notes:

- Disposable PostgreSQL migration tooling was added for anonymised staging data only.
- The migration source defaults to `data/staging/pt_claims_staging_anonymised.db`.
- The migration script refuses to use real `data/pt_claims.db`.
- PostgreSQL writes require `--confirm-disposable` and `--yes`.
- Disposable PostgreSQL credentials must be supplied through `PT_CLAIMS_TEST_DATABASE_URL`; no credentials are stored in the repository.
- The PostgreSQL schema avoids SQLite-only syntax such as `AUTOINCREMENT`, `sqlite_master`, and `PRAGMA`.
- PostgreSQL support remains staging-test tooling until validated against an actual disposable PostgreSQL database.
- The local app still defaults to SQLite when `DATABASE_URL` is absent.

Disposable PostgreSQL test commands:

```powershell
$env:PT_CLAIMS_TEST_DATABASE_URL = "postgresql://..."
python -m app.postgres_migrate_staging --dry-run
python -m app.postgres_migrate_staging --source data/staging/pt_claims_staging_anonymised.db --target-env PT_CLAIMS_TEST_DATABASE_URL --confirm-disposable --yes
python -m app.postgres_validate_staging --target-env PT_CLAIMS_TEST_DATABASE_URL
```

Do not use these commands with real data. Real cloud deployment still requires provider-level backups, object storage, HTTPS/domain/access review, institutional approval, and a formal real-data migration plan if such deployment is ever approved.

Phase 11.3.1 PostgreSQL runtime authentication notes:

- Authentication, audit logging, and admin account-management runtime paths now use the database provider abstraction.
- Local SQLite remains the default when `DATABASE_URL` is absent.
- PostgreSQL runtime paths use `%s` placeholders and normalise returned rows to dictionaries.
- Login success/failure, password change, last-login updates, and admin password reset can run against PostgreSQL staging.
- Audit logging fails safely if an audit write fails, so logging problems do not block login.
- A targeted PostgreSQL auth integration test is available and is skipped unless `PT_CLAIMS_TEST_DATABASE_URL` is configured.

Phase 11.3.2 PostgreSQL runtime performance notes:

- PostgreSQL runtime access now uses a central connection path with optional psycopg connection pooling.
- Set `DB_PERF_DEBUG=true` to print lightweight database timing diagnostics without exposing database URLs or secrets.
- Dashboard count queries were consolidated to reduce remote PostgreSQL round trips.
- Lecturer dashboard counts are loaded through one lecturer-scoped helper query.
- Data Inspection table previews are limited by default to reduce accidental large table loads.
- Audit Log remains limited to the latest 100 events.
- Local app plus remote Neon PostgreSQL can feel slower than local SQLite because every query travels over the network.
- Neon Free can scale to zero after inactivity, causing first-query delay.
- For real deployment, host the app and PostgreSQL in nearby regions and consider always-on database settings if consistent latency is required.

Phase 11.4 Deployment readiness checker and staging hardening notes:

- A deployment readiness checker was added for local, staging, and production configuration review.
- The checker never prints `DATABASE_URL`, passwords, tokens, or connection strings; it reports only whether sensitive settings are present.
- Run `python -m app.deployment_readiness_check` for a text report.
- Run `python -m app.deployment_readiness_check --json` for machine-readable output.
- Run `python -m app.deployment_readiness_check --fail-on-block` in automation to fail when blockers are present.
- Production with SQLite, missing `DATABASE_URL`, local generated-file mode, or `DB_PERF_DEBUG=true` is blocked.
- Staging PostgreSQL is treated as anonymised staging only.
- Staging SQLite warns if the path does not appear to be under `data/staging`.
- The admin dashboard no longer shows the obsolete DOCX/register draft-formatting warning.
- Theme contrast for form buttons, password inputs, and input icons was tightened centrally.

Safe readiness commands:

```powershell
python -m app.deployment_readiness_check
python -m app.deployment_readiness_check --json
python -m app.deployment_readiness_check --fail-on-block
```

Phase 11.5 Academic Calendar management and login contrast notes:

- An admin-only Academic Calendar page was added for viewing, adding, updating, deactivating, and reactivating claim/register exclusions.
- Calendar exclusions can be full-day or time-bound and can apply to all sessions, a specific lecturer, a specific course, or a specific lecturer-scoped group.
- Existing academic calendar rows are preserved by a backwards-compatible schema migration.
- Full-day exclusions continue to exclude sessions by date range; time-bound exclusions exclude only sessions whose time range overlaps the exclusion.
- Inactive exclusions do not affect session generation.
- Session generation, claim documents, and attendance registers use the same generated-session exclusion result.
- A non-destructive NUST 2026 reference section helps admins compare public holidays, institutional holidays, recesses, and breaks against official calendar items.
- Calendar add/update/deactivate/reactivate operations create database backups and are audit-logged when audit logging is available.
- Login and password input contrast was fixed centrally so typed text, password bullets, placeholders, caret, input icons, and button text remain readable.

Phase 12.0 Pre-Claim Verification notes:

- An admin-only Pre-Claim Verification page was added.
- Admin users can select a lecturer, year, and month to review readiness before claim/register document generation.
- The verification summary checks lecturer contract dates, active lecturer-scoped groups, timetable entries, active enrolments by group, academic calendar exclusions, generated claimable sessions, clashes, totals by course, totals by group, warnings, and blockers.
- Verification status is reported as `PASS`, `WARN`, or `BLOCK`.
- The page is read-only except for an optional verification CSV export under `data/exports/`.
- The verification export excludes sensitive lecturer fields such as ID/passport and PAYE.
- Pre-Claim Verification should be run before generating official documents, but it does not replace human administrative review.
- Phase 12.0 does not generate claim/register documents automatically and does not change DOCX templates.

Phase 13.0 Production usability and operational readiness notes:

- Claim/register periods are resolved centrally through `app.claim_period_service`.
- The selected attendance register month remains visible, but May to November 2026 use custom claim/register periods:
  May `2026-04-30` to `2026-05-29`, June `2026-05-30` to `2026-06-29`, July `2026-06-30` to `2026-07-31`, August `2026-08-01` to `2026-08-28`, September `2026-08-29` to `2026-09-30`, October `2026-10-01` to `2026-10-30`, and November `2026-10-31` to `2026-11-20`.
- Session generation, Pre-Claim Verification, claim totals, attendance registers, claim forms, and exports use the same resolved period.
- Admin users can temporarily use View as lecturer mode to inspect lecturer-scoped navigation and data, then return to admin. The admin database role is not changed, lecturer accounts are not changed, and Change Password is hidden during view-as mode.
- A demo/training lecturer workflow was added as an explicit command only: `python -m app.create_demo_workshop_account --dry-run` or `python -m app.create_demo_workshop_account --yes --password "<temporary_password>"`.
- The demo workflow creates labelled dummy lecturer, account, group, timetable, student, and enrolment data only when run with `--yes`; it is idempotent and is not run automatically.
- Theme/readability coverage was tightened for form controls, disabled controls, selectbox dropdowns, code/path blocks, and output file paths.
- Local use is ready for controlled operational use.
- Anonymised staging/demo online deployment is allowed.
- Real-data full online production is not complete until production PostgreSQL migration, durable document/object storage, safe secrets, backups, and access-control review are finalised.

Phase 13.1 Document Generation UI polish notes:

- Document Generation now uses operational wording: `Generate documents`.
- The old draft/under-review warning was removed from the Streamlit Document Generation page.
- The page now reminds admins to run Pre-Claim Verification and review generated documents before submission.
- The v2 `docxtpl` engine remains the normal default.
- Admin troubleshooting engine options are kept under Advanced options.
- Lecturer document generation does not expose the engine selector and automatically uses the recommended v2 path.
- File path and output sections use readable light path blocks instead of dark code-style blocks.

Phase 14.0 Production deployment foundation notes:

- Phase 14.0 does not deploy, upload real data, or migrate real data.
- The deployment readiness checker now separates local controlled use, anonymised staging/demo online use, and real-data online production.
- Local controlled use remains ready.
- Anonymised staging/demo online deployment remains allowed.
- Real-data online production remains blocked until production PostgreSQL migration is validated, durable generated document storage is configured, secrets are configured safely, provider-level backups are enabled, and access-control review is complete.
- Generated document storage is centralised through `app.document_storage` with `local`, `ephemeral`, `object_storage_pending`, and `object_storage` modes.
- Production with local generated-file storage is blocked.
- Production configuration examples were added to `.streamlit/secrets.example.toml`, `.env.example`, and `docs/production_deployment.md` with placeholders only.

Phase 14.1 S3-compatible document storage and production migration dry-run notes:

- Phase 14.1 does not deploy, upload real data, migrate real data, or generate bulk documents.
- `app.document_storage` now includes S3-compatible `object_storage` support for providers such as AWS S3, Cloudflare R2, Backblaze B2, or MinIO.
- Local mode remains the default and preserves existing `data/generated_v2/` behaviour.
- `ephemeral` mode remains suitable for anonymised staging/demo runs, but it is not durable.
- Production requires `DOCUMENT_STORAGE_MODE=object_storage` and placeholder-safe object storage settings such as `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_REGION`, `OBJECT_STORAGE_ENDPOINT_URL`, `OBJECT_STORAGE_ACCESS_KEY_ID`, and `OBJECT_STORAGE_SECRET_ACCESS_KEY`.
- The deployment readiness checker reports object-storage readiness and missing config keys without printing secret values.
- `python -m app.production_migration_plan --dry-run` inspects the SQLite schema, counts, migration blockers, and required backup steps without writing to PostgreSQL or printing `DATABASE_URL`.
- Real-data online production remains blocked until object storage is configured, production PostgreSQL migration is validated, secrets are safe, provider backups are enabled, and access-control review is complete.

Phase 14.2 live cloud infrastructure smoke-test notes:

- Phase 14.2 adds `python -m app.cloud_smoke_test` for safe production-style infrastructure checks without deploying, uploading real data, migrating real data, or generating claim/register documents.
- Safe commands include:
  - `python -m app.cloud_smoke_test --config-only`
  - `python -m app.cloud_smoke_test --all-dry-run`
  - `python -m app.cloud_smoke_test --postgres`
  - `python -m app.cloud_smoke_test --storage-dry-run`
  - `python -m app.cloud_smoke_test --storage-upload-dummy --yes`
- `--config-only` reports yes/no presence for required configuration and never prints secret values.
- `--postgres` runs read-only PostgreSQL checks only when `DATABASE_URL` is configured; it does not create tables or migrate data.
- `--storage-dry-run` validates object-storage configuration without uploading.
- `--storage-upload-dummy --yes` uploads only a tiny dummy text smoke-test file under `smoke-tests/`; it must not be used for real data.
- Real production data migration remains blocked until smoke tests, provider backups, object storage, secrets, and access-control review are complete.

Phase 14.3 real PostgreSQL migration command and backup gate notes:

- Phase 14.3 adds the guarded real-data migration command but does not run the real migration.
- Dry-run command:
  - `python -m app.production_migrate_real_data --dry-run`
- Real write mode, do not run until formally approved:
  - `python -m app.production_migrate_real_data --yes --backup-acknowledged --confirm-real-production-migration I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES`
- Write mode requires `DATABASE_URL`, configured object storage, an empty target PostgreSQL database, local SQLite backup creation, `--backup-acknowledged`, `--yes`, and the exact confirmation phrase.
- The migration preserves integer IDs, loads parent tables before child tables, and resets PostgreSQL identity sequences after explicit ID inserts.
- Console and JSON reports do not print database URLs, password hashes, object-storage keys, tokens, or sensitive lecturer/student values.
- The production migration plan now recognises the guarded command but still blocks real migration until dry-run, backups, object storage, empty target, and access-control review are complete.

Phase 14.3.1 boto3 dependency pinning notes:

- S3-compatible storage dependencies are pinned to avoid slow pip dependency backtracking during local setup and Streamlit Cloud installs.
- The pinned versions are `boto3==1.34.162`, `botocore==1.34.162`, and `s3transfer==0.10.4`.
- No deployment, cloud upload, data migration, document generation, or database data change is part of this phase.

Phase 14.4 production runtime download, storage, UI, and performance notes:

- PostgreSQL runtime database display is provider-aware and never renders `DATABASE_URL`; production PostgreSQL shows safe provider/environment text only.
- Object-storage document outputs support short-lived signed download links for generated claim, register ZIP, and checklist files where S3-compatible signing is available.
- Register ZIP downloads remain visible after document generation.
- Download and link-button styling was strengthened so claim/register/checklist download actions remain readable.
- Dashboard count lookups use short-lived scoped Streamlit caching to reduce repeated remote PostgreSQL round trips; lecturer-scoped cache keys include the lecturer staff number.
- Local SQLite remains the default when `DATABASE_URL` is absent.

Phase 14.5.3 PostgreSQL runtime and access-control notes:

- Admin View as lecturer and Course and Group Entry runtime lookups use the provider-aware database path so deployed PostgreSQL reads do not fall back to local SQLite.
- Generated document output metadata is kept in Streamlit session state so claim, register ZIP, checklist, and object-storage download references remain visible after download-triggered reruns.
- Lecturer-facing document generation uses the wording `Generate documents` and does not expose the document engine selector.
- Claim completeness checks compare distinct `course_code` plus `group_name` pairs so duplicate group names under different courses are audited correctly before rendering.
- Streamlit Cloud platform controls such as Manage app, Logs, Reboot app, Delete app, and Settings are outside the application RBAC; use Streamlit workspace/sharing permissions and an incognito/private viewer check to confirm what lecturers see.

Phase 14.6 separate training environment notes:

- `APP_ENV=training` is a first-class environment and displays a visible `TRAINING ENVIRONMENT, dummy data only.` banner.
- Training data must use a separate database and separate object-storage prefix or bucket; do not add dummy lecturers or dummy students to production.
- Create the local dummy-only training database with `python -m app.create_training_database --dry-run` and then `python -m app.create_training_database --overwrite --include-admin` after setting password environment variables.
- Migrate training data only with `TRAINING_DATABASE_URL` and the guarded command `python -m app.migrate_training_database --yes --confirm-training-migration I_UNDERSTAND_THIS_IS_TRAINING_DATA_ONLY`.
- `OBJECT_STORAGE_PREFIX=training-v2` keeps generated training documents separate from production object-storage keys.
- See `docs/training_environment.md` for the full training setup. Do not commit or print training or production secrets.

Phase 14.8 safe lecturer staff-number correction notes:

- Staff number remains locked in the normal Lecturer Entry update form because it is the lecturer login username and an operational identifier.
- Admins can use the separate `Correct staff number` panel only for genuine staff-number data-entry mistakes for the same lecturer.
- The correction requires the exact confirmation phrase `CORRECT STAFF NUMBER`, validates duplicates, updates `lecturers.staff_number`, and updates the linked lecturer account username while preserving role, lecturer link, password hash/salt, active state, first-login flag, created date, and last login.
- The lecturer must use the corrected staff number as the username after correction; the password is not changed.
- Historical audit rows, old local generated files, and old object-storage keys are not renamed. Regenerate official documents if previously generated files contain or are stored under the old staff number.
- Do not use this workflow to replace one lecturer with another person.

Phase 2.1 privacy notes:

- Session Generation UI hides sensitive lecturer fields such as ID/passport, PAYE, address, contact number, and highest qualification.
- Data Inspection masks sensitive lecturer fields by default.
- Backend exports may include fields required for document generation, so exports must be reviewed before sharing.
- The Streamlit UI remains a local prototype without authentication.

Phase 2.2 Session Generation notes:

- The Session Generation page now shows a cleaner administrative view.
- Lecturer details are shown once in summary cards, not repeated in every session row.
- Course and group filters affect the visible table only; totals remain based on all generated sessions.
- Grouped summaries by course and group support easier claim checking.

Phase 2.3 UI workflow notes:

- Master Data Import now follows a guided workflow: generate the template, upload a completed workbook, run dry-run validation, back up the database, then import.
- Dry-run validation should be completed and reviewed before import.
- A database backup should be created before importing real data.
- The UI disables import until the uploaded workbook has passed dry-run validation and the review/backup confirmation is checked.
- Session Generation shows lecturer name and staff number without truncation.
- Session Generation dates are displayed in `YYYY-MM-DD` format for clarity.

Phase 2.4 export feedback notes:

- Session Generation export buttons now show clear success or error feedback.
- Exported files show the saved path, file size, modified timestamp, and direct browser download buttons.
- Exports must still be reviewed before sharing because backend files may contain data needed for document generation.

Phase 2.5 persistent export feedback notes:

- Export buttons now persist success or error messages in the UI after Streamlit reruns.
- Export results show path, file size, modified timestamp, and browser download buttons directly below the clicked button.
- Users no longer need to check Windows Explorer to confirm export success.

Phase 2.6 export feedback bug-fix notes:

- Export button feedback is rendered directly below the clicked buttons on the Session Generation page.
- Session state keeps the message visible after Streamlit reruns.
- A temporary `Button clicked at` line appears under each export button after click to confirm the click was registered.

## Real data protection

- `pytest` is isolated from `data/pt_claims.db` by setting `PT_CLAIMS_DB_PATH` to a temporary SQLite database in `tests/conftest.py`.
- Normal Streamlit and command-line usage still use `data/pt_claims.db` unless `PT_CLAIMS_DB_PATH` is explicitly set.
- Do not run `dev_reset` on real data.
- Do not run `seed_data` on real data.
- Do not run `pytest` as part of real-use workflow. It is for development only and is isolated through `PT_CLAIMS_DB_PATH`.
- `python -m app.dev_reset` refuses to reset the real database unless both `--confirm-real-reset` and the exact phrase `I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA` are provided.
- `python -m app.seed_data` refuses to seed the real database unless both `--confirm-real-seed` and the exact phrase `I_UNDERSTAND_THIS_WILL_DELETE_REAL_DATA` are provided.
- `dev_reset` and `seed_data` create timestamped backups before destructive operations.
- Lecturer Entry creates a timestamped database backup before every lecturer save or update.
- Lecturer records can be exported from the Lecturer Entry page to `data/exports/lecturers_export_YYYYMMDD_HHMMSS.csv`.
- Real data entry should use Streamlit Lecturer Entry, immediate lecturer export, and backup checks.

## Safe real data entry workflow

1. Start Streamlit:

   ```powershell
   streamlit run app_ui/streamlit_app.py
   ```

2. Enter or update the lecturer in Lecturer Entry.
3. Confirm a backup was created under `data/backups/`.
4. Export lecturers to CSV from Lecturer Entry.
5. Confirm the CSV exists under `data/exports/`.
6. Make a manual zip backup of the project or at least the `data/` folder after major entry sessions.

## Safety check commands

Check which database the app will use in normal mode:

```powershell
python -c "from app.config import DB_PATH, REAL_DB_PATH; print('DB_PATH=', DB_PATH); print('REAL_DB_PATH=', REAL_DB_PATH); print('using_real=', DB_PATH.resolve()==REAL_DB_PATH.resolve())"
```

Check the current real lecturer count and names:

```powershell
python -c "import sqlite3; con=sqlite3.connect(r'data\pt_claims.db'); cur=con.cursor(); print('lecturers:', cur.execute('select count(*) from lecturers').fetchone()[0]); print(cur.execute('select staff_number, full_name from lecturers order by staff_number').fetchall()); con.close()"
```

## Isolated development testing

`pytest` is for development only. It must not be part of a real-use data-entry workflow. The test suite sets `PT_CLAIMS_DB_PATH` to a temporary database in `tests/conftest.py`; confirm this with `pytest tests/test_database_isolation.py -q` before running broader tests.

## Included seed data

- Lecturer: Ms. Lonia Nghitotelwa
- Staff number: 100718
- Campus: Eenhana Satellite Campus
- Tariff per hour: 410
- Course: CUS411S, Computer User Skills
- Groups: Group 1 to Group 11
- February 2026 timetable entries, including a deliberate overlap for clash detection
- Dummy-only ID/passport, PAYE, physical address, and contact number placeholders
- Dummy student records and group enrolment examples in the master data template
- Draft DOCX attendance register and claim form generation for internal Phase 1.2 testing
- Clean no-clash demo lecturer 200001 with enrolled dummy students for document QA

No bank details are stored in the schema, seed data, code, or exports.

Do not store bank details in this system. Generated DOCX files are drafts until official formatting is approved. Scanned PDF verification is not part of the current system.
