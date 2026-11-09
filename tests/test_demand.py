from roro_yield.demand import DEMAND_LEVELS, expected_remaining, requests_for_level


def test_expected_remaining_bounds():
    assert expected_remaining(60, 0.0, 0.45) == 60
    assert expected_remaining(60, 1.0, 0.45) == 0
    values = [expected_remaining(60, f / 10, 0.45) for f in range(11)]
    assert values == sorted(values, reverse=True)


def test_requests_for_level():
    assert set(DEMAND_LEVELS) == {"low", "normal", "high"}
    assert requests_for_level("high", 600) == round(1.30 * 600 / 13.0) == 60
