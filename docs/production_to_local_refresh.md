# Production-to-Local Refresh

Phase 14.10 adds a safe way to refresh local SQLite operational data from production PostgreSQL before continuing local-first data entry.

Git pull and git push move code only. They do not move database records. If records are added directly in production, local SQLite can become stale and should be refreshed before running local-to-production sync.

## What This Tool Does

- Reads production PostgreSQL using `DATABASE_URL`.
- Writes only to a local SQLite output file or, with explicit flags, replaces `data/pt_claims.db`.
- Copies the current local SQLite database first, then replaces only supported operational tables in the copy.
- Preserves local `user_accounts`, passwords, password hashes/salts, `audit_logs`, local backups, generated documents, generated metadata, and object-storage/R2 objects.
- Never prints `DATABASE_URL`, passwords, tokens, hashes, salts, or object-storage secrets.

## Supported Tables

- `lecturers`
- `courses`
- `student_groups`
- `timetable_entries`
- `students`
- `group_enrolments`
- `academic_calendar`

## Excluded Tables And Artifacts

- `user_accounts`
- password hashes and salts
- `audit_logs`
- generated documents
- generated document metadata
- R2/object-storage objects
- local backups
- secrets and configuration

Local user accounts may not include newly created production lecturer accounts after refresh. That is acceptable for local admin data entry.

## Commands

Summary:

```powershell
python -m app.production_to_local_refresh --summary
```

Dry-run:

```powershell
python -m app.production_to_local_refresh --dry-run
```

Create a refreshed local copy without replacing `data/pt_claims.db`:

```powershell
python -m app.production_to_local_refresh --yes --output data/pt_claims_FROM_PRODUCTION_REFRESHED.db --confirm-refresh I_UNDERSTAND_THIS_WILL_COPY_PRODUCTION_OPERATIONAL_DATA_TO_LOCAL
```

Replace local `data/pt_claims.db` only after reviewing the refreshed copy:

```powershell
python -m app.production_to_local_refresh --yes --replace-local --backup-local --confirm-refresh I_UNDERSTAND_THIS_WILL_REPLACE_LOCAL_OPERATIONAL_DATA_WITH_PRODUCTION
```

The replace command creates a timestamped local backup before replacing the local DB.

## Clearing DATABASE_URL In PowerShell

After running production-connected commands locally:

```powershell
Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
```

Do not paste or commit secrets into repository files.
