from dataclasses import dataclass


@dataclass(frozen=True)
class Lecturer:
    id: int
    staff_number: str
    title: str
    full_name: str
    tariff_per_hour: float
    campus: str
    contract_start_date: str
    contract_end_date: str
    active: int = 1


@dataclass(frozen=True)
class Course:
    id: int
    course_code: str
    course_name: str
    faculty: str
    department: str
    budget_allocation: str
    active: int = 1
