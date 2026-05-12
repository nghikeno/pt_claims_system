from zipfile import ZipFile

from app.staging_export import create_staging_package


def test_staging_package_excludes_real_data_paths(tmp_path):
    staging_db = tmp_path / "pt_claims_staging_anonymised.db"
    staging_db.write_bytes(b"not a real sqlite file for package test")

    package = create_staging_package(staging_db=staging_db, output_dir=tmp_path)

    with ZipFile(package) as archive:
        names = set(archive.namelist())

    assert "pt_claims_staging_anonymised.db" in names
    assert "README_STAGING.txt" in names
    assert "data/pt_claims.db" not in names
    assert ".streamlit/secrets.toml" not in names
    assert not any(name.startswith("data/backups/") for name in names)
    assert not any(name.startswith("data/generated_v2/") for name in names)
