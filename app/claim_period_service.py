from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ClaimPeriod:
    year: int
    month: int
    start_date: date
    end_date: date
    custom: bool = False

    @property
    def label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def display(self) -> str:
        return f"{self.start_date.isoformat()} to {self.end_date.isoformat()}"


CUSTOM_CLAIM_PERIODS_2026: dict[tuple[int, int], tuple[date, date]] = {
    (2026, 5): (date(2026, 4, 30), date(2026, 5, 29)),
    (2026, 6): (date(2026, 5, 30), date(2026, 6, 29)),
    (2026, 7): (date(2026, 6, 30), date(2026, 7, 31)),
    (2026, 8): (date(2026, 8, 1), date(2026, 8, 28)),
    (2026, 9): (date(2026, 8, 29), date(2026, 9, 30)),
    (2026, 10): (date(2026, 10, 1), date(2026, 10, 30)),
    (2026, 11): (date(2026, 10, 31), date(2026, 11, 20)),
}


def default_month_period(year: int, month: int) -> ClaimPeriod:
    year = int(year)
    month = int(month)
    last_day = calendar.monthrange(year, month)[1]
    return ClaimPeriod(year=year, month=month, start_date=date(year, month, 1), end_date=date(year, month, last_day))


def resolve_claim_period(year: int, month: int) -> ClaimPeriod:
    year = int(year)
    month = int(month)
    if (year, month) in CUSTOM_CLAIM_PERIODS_2026:
        start_date, end_date = CUSTOM_CLAIM_PERIODS_2026[(year, month)]
        return ClaimPeriod(year=year, month=month, start_date=start_date, end_date=end_date, custom=True)
    return default_month_period(year, month)
