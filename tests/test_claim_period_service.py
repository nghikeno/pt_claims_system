from datetime import date

from app.claim_period_service import resolve_claim_period


def test_custom_claim_periods_for_2026():
    expected = {
        5: (date(2026, 4, 30), date(2026, 5, 29)),
        6: (date(2026, 5, 30), date(2026, 6, 29)),
        7: (date(2026, 6, 30), date(2026, 7, 31)),
        8: (date(2026, 8, 1), date(2026, 8, 28)),
        9: (date(2026, 8, 29), date(2026, 9, 30)),
        10: (date(2026, 10, 1), date(2026, 10, 30)),
        11: (date(2026, 10, 31), date(2026, 11, 20)),
    }

    for month, (start, end) in expected.items():
        period = resolve_claim_period(2026, month)
        assert period.start_date == start
        assert period.end_date == end
        assert period.custom is True


def test_may_period_includes_april_30_and_ends_may_29():
    period = resolve_claim_period(2026, 5)

    assert period.start_date.isoformat() == "2026-04-30"
    assert period.end_date.isoformat() == "2026-05-29"


def test_november_period_ends_november_20():
    period = resolve_claim_period(2026, 11)

    assert period.end_date.isoformat() == "2026-11-20"


def test_unlisted_month_keeps_calendar_month_default():
    period = resolve_claim_period(2026, 2)

    assert period.start_date.isoformat() == "2026-02-01"
    assert period.end_date.isoformat() == "2026-02-28"
    assert period.custom is False
