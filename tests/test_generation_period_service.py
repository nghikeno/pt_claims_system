from datetime import date

import pytest

from app.generation_period_service import (
    describe_generation_period,
    resolve_custom_generation_period,
    resolve_standard_generation_period,
)


def test_standard_generation_period_uses_claim_period_service():
    period = resolve_standard_generation_period(2026, 5)

    assert period.mode == "standard"
    assert period.start_date == date(2026, 4, 30)
    assert period.end_date == date(2026, 5, 29)
    assert period.slug == "2026/05"
    assert period.standard_claim_period_custom is True


def test_custom_generation_period_uses_selected_dates():
    period = resolve_custom_generation_period(date(2026, 4, 3), date(2026, 4, 29))

    assert period.mode == "custom"
    assert period.start_date == date(2026, 4, 3)
    assert period.end_date == date(2026, 4, 29)
    assert period.slug == "custom_20260403_to_20260429"
    assert describe_generation_period(period) == "custom date range 2026-04-03 to 2026-04-29"


def test_custom_generation_period_rejects_end_before_start():
    with pytest.raises(ValueError, match="End date cannot be before start date"):
        resolve_custom_generation_period(date(2026, 4, 29), date(2026, 4, 3))
