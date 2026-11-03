import pytest

from roro_yield.explain import costly_decisions
from roro_yield.kpis import evaluate
from roro_yield.models import Booking, Lane, Plan, Scenario, Slot, Vessel


def scenario():
    bookings = (
        Booking("B1", 0, "contract", "Nordfreight", "semi_trailer", 13.6, 20.0, False, 48.0, 80.0, 110.0),
        Booking("B2", 1, "spot", "Spot haulier #1", "semi_trailer", 13.6, 20.0, True, 100.0, 150.0, 110.0),
        Booking("B3", 2, "spot", "Spot haulier #2", "van", 6.5, 3.0, False, 90.0, 0.0, 84.5),
    )
    vessel = Vessel("V", "A → B", (Lane("L1", 30.0),), 1000.0, 5, 0.5)
    return Scenario(vessel, bookings, 0.0, 200.0)


def test_identical_plans_have_no_costly_decisions():
    s = scenario()
    plan = Plan("x", {"B1": Slot("L1", 0)}, ["B2", "B3"])
    assert costly_decisions(s, plan, plan) == []


def test_both_kinds_with_exact_copy_and_order():
    s = scenario()
    user = Plan("You", {"B1": Slot("L1", 0), "B3": Slot("L1", 0)}, ["B2"])
    opt = Plan("Best", {"B2": Slot("L1", 0), "B3": Slot("L1", 0)}, ["B1"])
    ds = costly_decisions(s, user, opt)
    assert [d.booking_id for d in ds] == ["B2", "B1"]  # B2 margin 1400 > B1 margin 542.8
    assert ds[0].kind == "rejected_optimal"
    assert ds[0].impact_eur == pytest.approx(1400.0)
    assert ds[0].reason == "You turned down Spot haulier #1's semi-trailer at €100/m — €1,400 of margin left on the quay."
    assert ds[1].kind == "accepted_not_optimal"
    assert ds[1].reason == "You accepted Nordfreight's semi-trailer at €48/m. Its 14.1 m were worth more to higher-yield cargo."


def test_top_n_is_respected():
    s = scenario()
    user = Plan("You", {"B1": Slot("L1", 0)}, ["B2", "B3"])
    opt = Plan("Best", {"B2": Slot("L1", 0), "B3": Slot("L1", 0)}, ["B1"])
    assert len(costly_decisions(s, user, opt, top_n=2)) == 2
    assert len(costly_decisions(s, user, opt)) == 3


def test_ballast_decision_appears():
    bookings = (
        Booking("B1", 0, "spot", "H1", "semi_trailer", 13.6, 60.0, False, 100.0, 150.0, 110.0),
        Booking("B2", 1, "spot", "H2", "semi_trailer", 13.6, 60.0, False, 100.0, 150.0, 110.0),
    )
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 120.0, 9.0), Lane("L2", 120.0, -9.0)), 1000.0, 5, 0.5),
                 bookings, 0.0, 200.0)
    user = Plan("You", {"B1": Slot("L1", 0), "B2": Slot("L1", 1)}, [])
    opt = Plan("Best", {"B1": Slot("L1", 0), "B2": Slot("L2", 0)}, [])
    ds = costly_decisions(s, user, opt)
    assert len(ds) == 1
    d = ds[0]
    assert d.kind == "ballast" and d.booking_id is None
    assert d.impact_eur == pytest.approx(5.0 * (evaluate(s, user).ballast_t - evaluate(s, opt).ballast_t))
    assert d.reason.startswith("Your placement needed ")
    assert "t more than the best plan" in d.reason


def test_no_ballast_decision_when_close():
    s = scenario()
    plan = Plan("x", {"B1": Slot("L1", 0)}, [])
    assert all(d.kind != "ballast" for d in costly_decisions(s, plan, plan))
