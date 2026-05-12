# Cloud Readiness Notes

Phase 11.0 prepares the local app for future cloud deployment. It does not deploy, upload real data, or migrate the real SQLite database.

## Current posture

- Local SQLite remains the default when `DATABASE_URL` is absent.
- PostgreSQL URLs are detected for future migration planning, but PostgreSQL migration is not complete in Phase 11.0.
- Secrets must come from environment variables or Streamlit secrets.
- Generated documents remain local in development and should be treated as ephemeral in production unless object storage is added later.

## Before real cloud deployment

- Use anonymised staging data first.
- Move persistent data to managed PostgreSQL.
- Configure provider-level database backups.
- Add object storage for generated documents.
- Re-run RBAC and audit-log checks in staging.

## Phase 11.1 staging data

Phase 11.1 adds a deterministic anonymised SQLite staging dataset generator. It copies the local SQLite database to `data/staging/pt_claims_staging_anonymised.db`, then replaces lecturer names, staff numbers, student numbers, student names, sensitive lecturer fields, and user accounts with demo values.

The staging dataset is for demo/testing only. It must not be treated as production data, and real `data/pt_claims.db`, backups, exports, generated documents, `.env`, and `.streamlit/secrets.toml` must never be included in staging packages.

Useful commands:

```powershell
python -m app.anonymise_staging_data --dry-run
python -m app.anonymise_staging_data --output data/staging/pt_claims_staging_anonymised.db --overwrite
python -m app.anonymise_staging_data --validate data/staging/pt_claims_staging_anonymised.db
python -m app.staging_export
```

## PostgreSQL status

PostgreSQL is still partial/scaffolded. `DATABASE_URL` can select PostgreSQL mode and the project declares the `psycopg` dependency, but the application still has SQLite-specific schema and metadata usage that must be migrated and tested against a real PostgreSQL database before any real cloud deployment.

## Phase 11.3 disposable PostgreSQL test path

Phase 11.3 adds a disposable PostgreSQL migration and validation path for anonymised staging data only. It does not deploy the app and does not migrate real `data/pt_claims.db`.

The migration script defaults to `data/staging/pt_claims_staging_anonymised.db`, refuses the real database, and requires both `--confirm-disposable` and `--yes` before writing to PostgreSQL. The target URL is read from `PT_CLAIMS_TEST_DATABASE_URL`, not from committed files.

Example:

```powershell
$env:PT_CLAIMS_TEST_DATABASE_URL = "postgresql://..."
python -m app.postgres_migrate_staging --dry-run
python -m app.postgres_migrate_staging --source data/staging/pt_claims_staging_anonymised.db --target-env PT_CLAIMS_TEST_DATABASE_URL --confirm-disposable --yes
python -m app.postgres_validate_staging --target-env PT_CLAIMS_TEST_DATABASE_URL
```

Compatibility remains honest: the PostgreSQL schema and migration scripts can be tested against a disposable database, but the Streamlit runtime is not production-certified on PostgreSQL until all service queries and UI workflows are validated end to end.

## Phase 11.3.1 runtime authentication fix

Authentication, audit logging, and admin account-management paths now use the runtime database provider instead of assuming SQLite. In PostgreSQL mode these paths use psycopg connections, `%s` placeholders, and dictionary-like row normalisation. Local SQLite remains the default when `DATABASE_URL` is absent.

This fixes the first PostgreSQL runtime blocker: staging accounts such as `staging_admin` and `900001` can authenticate against disposable PostgreSQL once `DATABASE_URL` is set to the validated staging database. Broader Streamlit runtime validation is still required before claiming production readiness.

## Phase 11.3.2 PostgreSQL runtime performance

Remote PostgreSQL is inherently slower than local SQLite when the app runs locally because every query crosses the network. Neon Free may also scale to zero after inactivity, so the first query can include cold-start latency.

Phase 11.3.2 reduces avoidable overhead by centralising PostgreSQL runtime connections, using optional psycopg pooling when available, consolidating dashboard count queries, limiting Data Inspection previews, and adding `DB_PERF_DEBUG=true` timing diagnostics. These changes improve the staging runtime path without changing local SQLite as the default.

For production-like performance, the Streamlit app and PostgreSQL database should be hosted in nearby regions, and the database plan should be selected with expected latency and cold-start behaviour in mind.

## Phase 11.4 deployment readiness checker

Phase 11.4 adds `python -m app.deployment_readiness_check`, a local readiness review command that reports environment mode, database provider mode, generated-file mode, session timeout, PostgreSQL performance settings, warnings, blockers, and final readiness status.

The checker deliberately does not print secret values. It reports whether `DATABASE_URL` and `PT_CLAIMS_DB_PATH` are set, but never prints either value.

Useful commands:

```powershell
python -m app.deployment_readiness_check
python -m app.deployment_readiness_check --json
python -m app.deployment_readiness_check --fail-on-block
```

Production checks are intentionally strict: production with SQLite, missing `DATABASE_URL`, local generated-file storage, or `DB_PERF_DEBUG=true` is blocked. Real-data deployment still requires institutional approval, provider-level backups, object storage, HTTPS/domain/access review, and a formal real-data migration plan.

## Phase 11.5 academic calendar and login contrast

Phase 11.5 adds an admin-only Academic Calendar management page for full-day and time-bound claim/register exclusions. Exclusions can apply globally or to a specific lecturer, course, or lecturer-scoped group. Existing calendar rows are preserved through a backwards-compatible migration and inactive rows do not affect session generation.

The page includes a non-destructive NUST 2026 institutional-calendar reference list for manual comparison. It does not automatically overwrite real calendar data.

The central Streamlit theme also fixes login and password input contrast so typed text, placeholders, password bullets, carets, input icons, and submit-button text remain readable while preserving the dark sidebar styling.

## Phase 13.0 operational readiness clarification

Local SQLite use is ready for controlled operational use on the approved local machine and recovery workflow.

Anonymised staging/demo online deployment is allowed when it uses anonymised data only.

Real-data full online production is still not complete. It requires a final production PostgreSQL migration path, durable document/object storage, safe secrets configuration, provider-level backups, and an access-control review before real data is placed online.

Phase 13.0 also centralises custom claim/register periods, adds admin-only View as lecturer mode for operational checking, adds an explicit demo workshop account/data command, and improves readability for file paths, code blocks, and form controls.

Phase 13.1 polishes the operational Document Generation UI. The normal action is now `Generate documents`, the old draft warning is removed from the Streamlit page, advanced engine choices remain admin troubleshooting controls, and lecturer document generation always uses the recommended v2 path without exposing engine selection.

## Phase 14.0 production deployment foundation

Phase 14.0 prepares the technical foundation for future real online deployment but does not deploy, upload real data, or migrate real data.

The readiness checker now separates local controlled use, anonymised staging/demo online use, and real-data online production. Production remains blocked until production PostgreSQL migration is validated, durable generated document storage is configured, safe secrets are in place, provider-level backups are enabled, and access-control review is complete.

Generated document storage is now represented by a storage abstraction with `local`, `ephemeral`, `object_storage_pending`, and `object_storage` modes. Local mode remains valid for local controlled use, but production with local-only generated file storage is blocked.

Configuration examples live in `.streamlit/secrets.example.toml`, `.env.example`, and `docs/production_deployment.md`. These files contain placeholders only.

## Phase 14.1 S3-compatible storage and migration dry-run

Phase 14.1 adds S3-compatible generated-document storage support without uploading any files during implementation. Supported storage modes are:

- `local`: default for local controlled use; generated files remain under `data/generated_v2/`.
- `ephemeral`: suitable for anonymised staging/demo runs where generated files are immediate-download only.
- `object_storage_pending`: explicit blocker state while durable storage is not ready.
- `object_storage`: durable S3-compatible mode once bucket, endpoint, region, and access credentials are configured as deployment secrets.

Object storage can target compatible providers such as AWS S3, Cloudflare R2, Backblaze B2, or MinIO. The app reports only whether required config keys are present; it must never display access keys, secret keys, bucket credentials, or connection strings.

Phase 14.1 also adds:

```powershell
python -m app.production_migration_plan --dry-run
```

This command inspects the current SQLite schema, row counts, migration blockers, risky fields, and required backup steps. It does not write to PostgreSQL and does not print `DATABASE_URL`.

Real-data online production remains blocked until the production PostgreSQL migration is validated, object storage is configured, secrets are safe, provider backups are enabled, and access-control review is complete.

## Phase 14.2 live infrastructure smoke tests

Phase 14.2 adds safe smoke-test commands for production-style cloud infrastructure. These commands do not deploy the app, do not upload real data, do not migrate real data, and do not generate claim/register documents.

Use placeholders only in committed files. Configure actual values in the deployment platform or Streamlit secrets.

Recommended manual setup:

1. Create the managed PostgreSQL database.
2. Create the S3-compatible bucket.
3. Create least-privilege object-storage access keys.
4. Add secrets through the deployment platform or Streamlit secrets.
5. Run:

```powershell
python -m app.cloud_smoke_test --config-only
python -m app.cloud_smoke_test --all-dry-run
python -m app.cloud_smoke_test --storage-upload-dummy --yes
python -m app.production_migration_plan --dry-run
```

`--storage-upload-dummy --yes` uploads only a tiny dummy text file under `smoke-tests/` and must never be used for real claim/register data. Do not migrate real data until smoke tests and provider backup checks pass.

## Phase 14.3 guarded real-data migration command

Phase 14.3 adds a real-data PostgreSQL migration command, but this phase does not run the migration.

Dry-run:

```powershell
python -m app.production_migrate_real_data --dry-run
python -m app.production_migrate_real_data --dry-run --json
```

Write mode, do not run until formally approved:

```powershell
python -m app.production_migrate_real_data --yes --backup-acknowledged --confirm-real-production-migration I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES
```

Write mode is guarded by:

- `DATABASE_URL` must be configured and must point to PostgreSQL.
- Object storage must be configured and ready.
- The target PostgreSQL core tables must be empty.
- A timestamped local SQLite backup is created before writes.
- `--backup-acknowledged`, `--yes`, and the exact confirmation phrase are required.
- Source and target counts are compared after migration.
- PostgreSQL identity sequences are reset after explicit ID inserts.

The command must not print database URLs, password hashes, object storage credentials, tokens, lecturer sensitive fields, or student names. Provider backups and access-control review are still required before any real online production use.

## Phase 14.4 production runtime fixes

Phase 14.4 improves the production runtime path after real PostgreSQL and object storage smoke testing.

- The Streamlit dashboard now displays PostgreSQL provider status safely without rendering `DATABASE_URL`.
- Object-storage document outputs can provide short-lived signed download links, normally expiring after 15 minutes.
- Register ZIP downloads remain visible in the document-generation workflow.
- Download buttons and signed-link buttons use readable high-contrast styling.
- Local testing against remote Neon PostgreSQL can still feel slower than a deployed app because each query crosses the internet. The app reduces repeated dashboard count queries with short-lived, scoped Streamlit caching, but production performance still depends on hosting the app and database in nearby regions where possible.
- Secrets remain hidden from UI, logs, and readiness output.
