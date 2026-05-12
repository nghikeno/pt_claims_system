# Production Deployment Foundation

Phase 14.0 does not deploy, upload real data, or migrate the real SQLite database.

## Current Status

- Local controlled use is ready.
- Anonymised staging/demo online deployment is allowed.
- Real-data online production remains blocked.

## Production Blockers

Real-data online production must not proceed until:

- Production PostgreSQL migration is validated end to end.
- Durable generated document storage is configured.
- Secrets are configured through the deployment platform or Streamlit secrets.
- Provider-level database backups are enabled and tested.
- Access-control and lecturer scoping are reviewed in the deployed environment.

## Required Production Configuration

Use placeholders only in committed files:

```text
APP_ENV=production
DATABASE_URL=<managed-postgresql-url>
GENERATED_FILE_MODE=ephemeral
DOCUMENT_STORAGE_MODE=object_storage
SESSION_TIMEOUT_MINUTES=30
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=4
```

S3-compatible object storage settings must be configured as secrets in the deployment platform. The committed examples are placeholders only:

```text
OBJECT_STORAGE_PROVIDER=<provider>
OBJECT_STORAGE_BUCKET=<bucket>
OBJECT_STORAGE_REGION=<region>
OBJECT_STORAGE_ENDPOINT_URL=<s3-compatible-endpoint>
OBJECT_STORAGE_ACCESS_KEY_ID=<access-key-id>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<secret-access-key>
OBJECT_STORAGE_PREFIX=generated-v2
```

Object storage can target AWS S3, Cloudflare R2, Backblaze B2, MinIO, or another S3-compatible service. Do not commit real bucket names, keys, tokens, passwords, or connection strings.

S3-compatible storage dependencies are pinned for stable installs:

```text
boto3==1.34.162
botocore==1.34.162
s3transfer==0.10.4
```

## Readiness Check

Run:

```powershell
python -m app.deployment_readiness_check
python -m app.deployment_readiness_check --json
```

The checker reports whether secrets are present as yes/no only and never prints secret values.

## Production Migration Dry-Run

Run:

```powershell
python -m app.production_migration_plan --dry-run
```

The dry-run inspects SQLite schema, row counts, risky fields, remaining blockers, and required backup steps. It does not write to PostgreSQL and does not print `DATABASE_URL`.

This is not approval to migrate real data. Real production migration remains blocked until the production PostgreSQL target, provider backups, durable document storage, safe secrets, and access-control review are approved and validated.

## Live Infrastructure Smoke Tests

After production-style PostgreSQL and S3-compatible storage are created and secrets are configured in the deployment platform, run:

```powershell
python -m app.cloud_smoke_test --config-only
python -m app.cloud_smoke_test --all-dry-run
python -m app.cloud_smoke_test --storage-upload-dummy --yes
python -m app.production_migration_plan --dry-run
```

The smoke-test command reports `PASS`, `WARN`, or `BLOCK`. It reports whether secrets are present as yes/no only and must not print database URLs, access keys, secret keys, tokens, or connection strings.

`--storage-upload-dummy --yes` uploads one tiny dummy text file only. It must not be used for real claim/register documents or real data.

## Guarded Real PostgreSQL Migration Command

Phase 14.3 adds the real-data migration command but does not run it.

Dry-run:

```powershell
python -m app.production_migrate_real_data --dry-run
python -m app.production_migrate_real_data --dry-run --json
```

Write mode, do not run until formally approved:

```powershell
python -m app.production_migrate_real_data --yes --backup-acknowledged --confirm-real-production-migration I_UNDERSTAND_THIS_WILL_COPY_REAL_DATA_TO_POSTGRES
```

Before write mode:

- Run the object-storage smoke test successfully.
- Confirm provider-level PostgreSQL backups are enabled.
- Confirm the target PostgreSQL database is empty.
- Confirm secrets are configured through the host or Streamlit secrets.
- Run the migration dry-run and review counts.
- Complete RBAC/access-control review after migration and before user access.

The command preserves IDs, inserts parent tables before child tables, resets PostgreSQL identity sequences, and compares source/target counts. It must never print database URLs, password hashes, access keys, secret keys, tokens, or sensitive lecturer/student values.

## Runtime Document Downloads

In `DOCUMENT_STORAGE_MODE=object_storage`, generated documents are stored durably through the configured S3-compatible provider. The UI shows object keys and uses short-lived signed download links where supported. Do not expose local server paths as production download references.

Local testing against remote Neon PostgreSQL can be slower than the deployed app because every query crosses the internet. Keep the Streamlit app and PostgreSQL database in nearby regions where possible, and review provider plan settings if always-on performance is required.
