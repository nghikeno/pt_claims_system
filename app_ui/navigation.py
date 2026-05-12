from __future__ import annotations

from app.config import enable_development_page


def admin_navigation_options() -> list[str]:
    options = [
        "Home / Dashboard",
        "Master Data Import",
        "Lecturer Entry",
        "Course and Group Entry",
        "Timetable Entry",
        "Academic Calendar",
        "Student Upload",
        "Pre-Claim Verification",
        "Account Management",
        "Audit Log",
        "Data Inspection",
        "Session Generation",
        "Document Generation",
        "Change Password",
    ]
    if enable_development_page():
        options.append("Development")
    return options


def lecturer_navigation_options() -> list[str]:
    return ["My Dashboard", "My Timetable/Sessions", "My Documents", "Change Password"]
