from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.anonymise_staging_data import DEFAULT_OUTPUT, create_anonymised_staging_db
from app.config import DATA_DIR, PROJECT_ROOT


STAGING_DIR = DATA_DIR / "staging"


def create_staging_readme() -> str:
    return """# Anonymised staging package

This package is for local staging/demo preparation only.

Included:
- anonymised SQLite staging database
- Streamlit secrets example
- cloud readiness notes, when available

Excluded:
- real data/pt_claims.db
- data/backups/
- real generated documents
- real exports
- .env
- .streamlit/secrets.toml

Do not upload real data to free cloud hosting.
"""


def create_staging_package(
    staging_db: Path = DEFAULT_OUTPUT,
    output_dir: Path = STAGING_DIR,
    *,
    overwrite_db: bool = False,
) -> Path:
    staging_db = Path(staging_db)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not staging_db.exists() or overwrite_db:
        create_anonymised_staging_db(output=staging_db, overwrite=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_path = output_dir / f"staging_package_{timestamp}.zip"
    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        archive.write(staging_db, arcname=staging_db.name)
        archive.writestr("README_STAGING.txt", create_staging_readme())
        secrets_example = PROJECT_ROOT / ".streamlit" / "secrets.example.toml"
        if secrets_example.exists():
            archive.write(secrets_example, arcname="secrets.example.toml")
        cloud_doc = PROJECT_ROOT / "docs" / "cloud_readiness.md"
        if cloud_doc.exists():
            archive.write(cloud_doc, arcname="cloud_readiness.md")
    return package_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an anonymised staging package.")
    parser.add_argument("--staging-db", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-dir", default=str(STAGING_DIR))
    parser.add_argument("--overwrite-db", action="store_true")
    args = parser.parse_args()

    package_path = create_staging_package(
        staging_db=Path(args.staging_db),
        output_dir=Path(args.output_dir),
        overwrite_db=args.overwrite_db,
    )
    print(f"Created staging package: {package_path}")


if __name__ == "__main__":
    main()
