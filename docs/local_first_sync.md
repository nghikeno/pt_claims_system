# Local-First Data Entry and Guarded Production Sync

Phase 14.9 adds a guarded way to enter operational data locally in SQLite and then review a table-by-table sync plan before writing safe changes to production PostgreSQL.

Git push deploys code only. It does not move local database records into Neon PostgreSQL.

## Supported Tables

- `lecturers`
- `courses`
- `student_groups`
- `timetable_entries`
- `students`
- `group_enrolments`
- `academic_calendar`

## Excluded Data

The sync deliberately excludes:

- `user_accounts`
- password hashes and salts
- `audit_logs`
- generated documents
- generated file metadata
- R2/object-storage objects
- local backups
- secrets and configuration

Do not use this workflow as a full database overwrite. Phase 14.9 does not delete production rows.

## Natural Keys

The sync compares records using stable operational keys:

- lecturers: `staff_number`
- courses: `course_code`
- student groups: `staff_number + course_code + group_name`
- students: `student_number`
- enrolments: `student_number + staff_number + course_code + group_name`
- timetable entries: `staff_number + course_code + group_name + day + start/end time + effective dates`
- academic calendar: title/category/date range/scope identifiers

Staff-number correction is not supported by this sync. Use the separate admin staff-number correction workflow for genuine data-entry mistakes.

## Commands

Inspect counts:

```powershell
python -m app.local_first_sync --summary
```

Dry-run all supported tables:

```powershell
python -m app.local_first_sync --dry-run
```

Dry-run selected tables:

```powershell
python -m app.local_first_sync --dry-run --tables lecturers,student_groups,timetable_entries
```

Write mode is guarded and must only be run after reviewing the dry-run, confirming provider-level backups, and ensuring `DATABASE_URL` points to production PostgreSQL:

```powershell
python -m app.local_first_sync --yes --backup-acknowledged --confirm-sync I_UNDERSTAND_THIS_WILL_WRITE_LOCAL_CHANGES_TO_PRODUCTION
```

The command never prints `DATABASE_URL`, passwords, tokens, object-storage keys, or password hashes.

## Conflict Review

Dry-run reports inserts, updates, skips, conflicts, warnings, and blockers. Any blocker prevents write mode. Examples include duplicate natural keys, generic groups, conflicting lecturer/student identity details, and timetable overlaps.

Provider-level PostgreSQL backups remain the operator's responsibility before write mode.
