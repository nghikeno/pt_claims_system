import pandas as pd
import pytest

from app.import_master_data import import_master_data
from app.master_data_template import generate_master_data_template
from app.seed_data import seed_database


@pytest.fixture(autouse=True)
def seeded_database():
    seed_database()


def _write_modified_workbook(source_path, target_path, sheet_name, modifier):
    workbook = pd.read_excel(source_path, sheet_name=None)
    workbook[sheet_name] = modifier(workbook[sheet_name].astype(object))
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        for name, df in workbook.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return target_path


def test_invalid_timetable_time_is_rejected(tmp_path):
    template_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    def modifier(df):
        df.loc[0, "end_time"] = "07:00"
        return df

    invalid_path = _write_modified_workbook(template_path, tmp_path / "invalid_time.xlsx", "Timetable", modifier)

    with pytest.raises(ValueError, match="Timetable row 2, column 'end_time'"):
        import_master_data(invalid_path)


def test_missing_required_lecturer_staff_number_is_rejected(tmp_path):
    template_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    def modifier(df):
        df.loc[0, "staff_number"] = ""
        return df

    invalid_path = _write_modified_workbook(template_path, tmp_path / "missing_staff.xlsx", "Lecturers", modifier)

    with pytest.raises(ValueError, match="Lecturers row 2, column 'staff_number'"):
        import_master_data(invalid_path)


def test_unknown_course_code_in_groups_is_rejected(tmp_path):
    template_path = generate_master_data_template(tmp_path / "master_data_template.xlsx")

    def modifier(df):
        df.loc[0, "course_code"] = "UNKNOWN101"
        return df

    invalid_path = _write_modified_workbook(template_path, tmp_path / "unknown_course.xlsx", "Groups", modifier)

    with pytest.raises(ValueError, match="Groups row 2, column 'course_code'"):
        import_master_data(invalid_path)
