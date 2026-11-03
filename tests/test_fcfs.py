import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.models import Booking, Lane, Scenario, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario


@pytest.mark.parametrize("seed", range(1, 21))
def test_fcfs_plans_are_feasible(seed):
    s = generate_scenario(ScenarioParams(seed=seed))
    plan = solve_fcfs(s)
    assert plan.method == "First come, first served"
    assert check_plan(s, plan) == []
    assert sorted(plan.accepted_ids + plan.rejected) == sorted(b.id for b in s.bookings)


def test_fcfs_rejects_only_what_did_not_fit_at_its_turn():
    s = generate_scenario(ScenarioParams(seed=5))
    plan = solve_fcfs(s)
    deck = DeckState(s.vessel)
    for b in sorted(s.bookings, key=lambda b: b.arrival):
        if b.id in plan.placements:
            deck.place(b, plan.placements[b.id])
        else:
            assert deck.why_not(b) is not None


def test_fcfs_accepts_in_arrival_order():
    def bk(i, arrival, margin_rate):
        return Booking(f"B{i}", arrival, "spot", "C", "semi_trailer", 13.6, 10.0, False, margin_rate, 0.0, 0.0)

    # One 15 m lane has 3.75 m zones: nothing fits, so use a 60 m lane (4 x 15 m zones) pre-filled
    # by three earlier arrivals; of the last two only the first can still be loaded.
    fillers = [bk(i, i, 10.0) for i in range(3)]
    cheap_first = bk(10, 10, 50.0)
    rich_second = bk(11, 11, 120.0)
    vessel = Vessel("V", "A to B", (Lane("L1", 60.0),), 1000.0, 0, 0.5)
    s = Scenario(vessel, (rich_second, cheap_first, *fillers), 0.0, 200.0)
    plan = solve_fcfs(s)
    assert "B10" in plan.accepted_ids
    assert plan.rejected == ["B11"]
