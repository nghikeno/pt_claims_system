# Training Environment

Phase 14.6 adds a separate training path for lecturer demonstrations. Training must not use the production PostgreSQL database or production object-storage namespace.

## Why Training Is Separate

The production app contains real lecturer, student, timetable, enrolment, and account data. Training uses a separate database with dummy-only data so workshop screens and generated documents do not expose production records.

Use a separate Streamlit Cloud app such as `pt-claims-training.streamlit.app` with the same repo, branch, and main file:

```text
Repository: nghikeno/pt_claims_system
Branch: main
Main file: app_ui/streamlit_app.py
```

## Local Training SQLite Database

Set passwords in your local shell or deployment secret manager. Do not commit them.

```powershell
$env:TRAINING_LECTURER_PASSWORD = "<training lecturer password>"
$env:TRAINING_ADMIN_PASSWORD = "<optional training admin password>"
python -m app.create_training_database --dry-run
python -m app.create_training_database --overwrite --include-admin
```

The default output is:

```text
data/training/pt_claims_training.db
```

The script refuses to write to `data/pt_claims.db` and prints only safe summary counts.

## Training PostgreSQL Migration

Create a separate Neon training database. Do not use the production `DATABASE_URL`.

Configure only a training target variable:

```powershell
$env:TRAINING_DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/TRAINING_DB"
python -m app.migrate_training_database --dry-run
python -m app.migrate_training_database --yes --confirm-training-migration I_UNDERSTAND_THIS_IS_TRAINING_DATA_ONLY
```

The command hides the URL value, refuses `data/pt_claims.db`, and requires the exact confirmation phrase for write mode.

## Training Streamlit Secrets

Use placeholders like this in the Streamlit Cloud training app settings. Never paste production secrets into the training app.

```toml
APP_ENV = "training"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/TRAINING_DB"
DOCUMENT_STORAGE_MODE = "object_storage"
GENERATED_FILE_MODE = "ephemeral"
OBJECT_STORAGE_PROVIDER = "r2"
OBJECT_STORAGE_BUCKET = "training-bucket-or-shared-bucket"
OBJECT_STORAGE_REGION = "auto"
OBJECT_STORAGE_ENDPOINT_URL = "https://placeholder-storage-endpoint"
OBJECT_STORAGE_ACCESS_KEY_ID = "placeholder-training-access-key"
OBJECT_STORAGE_SECRET_ACCESS_KEY = "placeholder-training-secret-key"
OBJECT_STORAGE_PREFIX = "training-v2"
```

`OBJECT_STORAGE_PREFIX=training-v2` keeps generated training files separate from production object keys. A separate bucket is also acceptable.

## Training App Use

Use the training app link for workshops and demos. The app displays a visible `TRAINING ENVIRONMENT, dummy data only.` banner when `APP_ENV=training`.

Streamlit Cloud controls such as Manage app, Logs, Reboot app, Delete app, and Settings are platform-owner controls. Normal app users are governed by the app RBAC, but platform permissions are managed in Streamlit Cloud sharing/workspace settings.
