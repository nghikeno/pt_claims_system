from app.validators import calculate_hours, minutes_to_claim_hours


def test_minutes_to_claim_hours_truncates_not_rounds():
    assert str(minutes_to_claim_hours(60)) == "1"
    assert str(minutes_to_claim_hours(80)) == "1.33"
    assert str(minutes_to_claim_hours(85)) == "1.41"
    assert str(minutes_to_claim_hours(90)) == "1.5"
    assert str(minutes_to_claim_hours(120)) == "2"


def test_calculate_hours_truncates_institutional_times():
    assert calculate_hours("20:00", "21:25") == 1.41
    assert calculate_hours("18:40", "20:00") == 1.33


def test_amount_uses_truncated_claim_hours():
    hours = calculate_hours("20:00", "21:25")
    assert hours == 1.41
    assert round(hours * 440, 2) == 620.40
