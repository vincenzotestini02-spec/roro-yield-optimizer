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
    deck = DeckState(s)
    for b in sorted(s.bookings, key=lambda b: b.arrival):
        if b.id in plan.placements:
            deck.place(b)
        else:
            assert deck.why_not(b) is not None


def test_fcfs_accepts_in_arrival_order():
    def bk(i, arrival, margin_rate):
        return Booking(f"B{i}", arrival, "spot", "C", "semi_trailer", 13.6, 10.0, False, margin_rate, 0.0, 0.0)

    # One 15 m lane: only the first arrival fits, even though the second pays more.
    cheap_first = bk(1, 0, 50.0)
    rich_second = bk(2, 1, 120.0)
    vessel = Vessel("V", "A → B", (Lane("L1", 15.0),), 100.0, 0, 0.5)
    s = Scenario(vessel, (rich_second, cheap_first), 0.0, 200.0)
    plan = solve_fcfs(s)
    assert plan.accepted_ids == ["B1"]
    assert plan.rejected == ["B2"]
