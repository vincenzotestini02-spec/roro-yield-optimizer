import pytest

from roro_yield.kpis import evaluate, objective, yield_delta_pct
from roro_yield.models import Booking, Lane, Plan, Scenario, Slot, Vessel


def two_booking_scenario(floor=20.0):
    contract = Booking("C1", 0, "contract", "KA", "semi_trailer", 13.6, 20.0, False, 50.0, 80.0, 110.0)
    spot = Booking("S1", 1, "spot", "H", "semi_trailer", 13.6, 30.0, True, 100.0, 150.0, 125.0)
    # C2 is never placed; it raises the contract metres requested so the realised floor is not capped below `floor`.
    extra = Booking("C2", 2, "contract", "KB", "semi_trailer", 6.4, 5.0, False, 50.0, 0.0, 0.0)
    vessel = Vessel("V", "A → B", (Lane("L1", 50.0), Lane("L2", 50.0)), 200.0, 4, 0.5)
    return Scenario(vessel, (contract, spot, extra), floor, 200.0)


def test_evaluate_hand_computed():
    s = two_booking_scenario()
    k = evaluate(s, Plan("You", {"C1": Slot("L1", 0), "S1": Slot("L2", 0)}, []))
    revenue = 680.0 + 1510.0
    margin = (680.0 - 110.0) + (1510.0 - 125.0)
    shortfall = 20.0 - 13.6
    assert k.method == "You"
    assert k.n_accepted == 2
    assert k.revenue == pytest.approx(revenue)
    assert k.margin == pytest.approx(margin)
    assert k.contract_m == pytest.approx(13.6)
    assert k.shortfall_m == pytest.approx(shortfall)
    assert k.penalty == pytest.approx(200.0 * shortfall)
    assert k.objective == pytest.approx(margin - 200.0 * shortfall)
    assert k.revpal == pytest.approx(revenue / 100.0)
    assert k.deck_util_pct == pytest.approx(28.2)
    assert k.dwt_pct == pytest.approx(25.0)
    assert k.plugs_used == 1


def test_objective_matches_evaluate():
    s = two_booking_scenario()
    plan = Plan("x", {"S1": Slot("L1", 0)}, ["C1"])
    assert objective(s, plan) == pytest.approx(evaluate(s, plan).objective)


def test_empty_plan_is_all_zero_with_full_shortfall():
    s = two_booking_scenario()
    k = evaluate(s, Plan("x", {}, ["C1", "S1", "C2"]))
    assert (k.n_accepted, k.revenue, k.margin, k.revpal, k.deck_util_pct, k.dwt_pct, k.plugs_used) == (0, 0, 0, 0, 0, 0, 0)
    assert (k.ballast_t, k.ballast_cost, k.heel_deg, k.trim_m) == (0, 0, 0, 0)
    assert k.shortfall_m == pytest.approx(20.0)


def test_zero_dwt_does_not_divide_by_zero():
    s = two_booking_scenario()
    s = Scenario(Vessel("V", "A → B", s.vessel.lanes, 0.0, 0, 0.5), s.bookings, 0.0, 200.0)
    assert evaluate(s, Plan("x", {}, [])).dwt_pct == 0


def test_yield_delta_pct():
    assert yield_delta_pct(110, 100) == pytest.approx(10)
    assert yield_delta_pct(90, 100) == pytest.approx(-10)
    assert yield_delta_pct(5, 0) is None
    assert yield_delta_pct(5, -3) is None


def unbalanced_scenario():
    b = Booking("B1", 0, "spot", "H", "semi_trailer", 13.6, 60.0, False, 100.0, 150.0, 125.0)
    vessel = Vessel("V", "A → B", (Lane("L1", 120.0, 9.0),), 1000.0, 4, 0.5)
    return Scenario(vessel, (b,), 0.0, 200.0)


def test_objective_includes_ballast_cost():
    s = unbalanced_scenario()
    k = evaluate(s, Plan("x", {"B1": Slot("L1", 0)}, []))
    assert k.ballast_t > 0
    assert k.ballast_cost == pytest.approx(5.0 * k.ballast_t)
    assert k.objective == pytest.approx(k.margin - 5 * k.ballast_t)
    assert abs(k.heel_deg) <= s.vessel.stability.max_heel_deg + 1e-6


def test_dwt_pct_counts_ballast():
    s = unbalanced_scenario()
    k = evaluate(s, Plan("x", {"B1": Slot("L1", 0)}, []))
    assert k.dwt_pct == pytest.approx((60.0 + k.ballast_t) / 1000.0 * 100)
