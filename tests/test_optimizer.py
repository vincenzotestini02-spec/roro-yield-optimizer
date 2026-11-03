import time

import pulp
import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import evaluate, objective, plan_ballast
from roro_yield.models import Booking, Lane, Plan, Scenario, Slot, Vessel
from roro_yield.optimizer import OPTIMAL_LABEL, build_model, solve_optimal
from roro_yield.simulator import ScenarioParams, generate_scenario


@pytest.mark.parametrize("seed", range(1, 11))
def test_optimal_is_feasible_and_beats_fcfs(seed):
    s = generate_scenario(ScenarioParams(seed=seed))
    opt, fcfs = solve_optimal(s), solve_fcfs(s)
    assert opt.method == OPTIMAL_LABEL == "Best possible (perfect foresight)"
    assert check_plan(s, opt) == []
    assert sorted(opt.accepted_ids + opt.rejected) == sorted(b.id for b in s.bookings)
    assert objective(s, opt) >= objective(s, fcfs) - 1e-6


def _bk(i, segment, rate, length=13.6):
    return Booking(f"B{i}", i, segment, "C", "semi_trailer", length, 10.0, False, rate, 0.0, 0.0)


def test_prefers_high_margin_when_capacity_binds():
    # Deadweight (15 t, units weigh 10 t) lets only one unit on.
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 70.0),), 15.0, 0, 0.5),
                 (_bk(1, "spot", 500 / 13.6), _bk(2, "spot", 900 / 13.6)), 0.0, 200.0)
    assert solve_optimal(s).accepted_ids == ["B2"]


def test_meets_contract_floor_when_possible():
    # Deadweight for one unit. Spot pays more, but skipping the contract costs 13.6 m x 200 EUR of penalty.
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 70.0),), 15.0, 0, 0.5),
                 (_bk(1, "contract", 50.0), _bk(2, "spot", 110.0)), 13.6, 200.0)
    plan = solve_optimal(s)
    assert plan.accepted_ids == ["B1"]
    assert evaluate(s, plan).shortfall_m == 0


def test_solves_default_under_5s():
    s = generate_scenario(ScenarioParams())
    start = time.perf_counter()
    solve_optimal(s)
    assert time.perf_counter() - start < 5


def test_balances_when_cheaper():
    # Two heavy units, two lanes on opposite sides: loading both on one side needs ballast,
    # splitting them across the beam needs none.
    lanes = (Lane("L1", 80.0, -3.0), Lane("L2", 80.0, 3.0))
    vessel = Vessel("V", "A → B", lanes, 1000.0, 0, 0.5)
    heavy = lambda i: Booking(f"B{i}", i, "spot", "C", "mafi", 12.2, 60.0, False, 40.0, 0.0, 0.0)
    s = Scenario(vessel, (heavy(1), heavy(2)), 0.0, 200.0)
    plan = solve_optimal(s)
    assert sorted(plan.accepted_ids) == ["B1", "B2"]
    assert {slot.lane_id for slot in plan.placements.values()} == {"L1", "L2"}
    assert evaluate(s, plan).ballast_t == 0


def test_candidate_guard():
    s = generate_scenario(ScenarioParams(seed=3))
    best = solve_optimal(s)
    # A candidate with a higher score than whatever a 0.01 s MILP finds: use the real optimum.
    out = solve_optimal(s, time_limit_s=0.01, candidates=[best])
    assert objective(s, out) >= objective(s, best) - 1e-6
    assert out.method == OPTIMAL_LABEL
    assert out.placements == best.placements or objective(s, out) > objective(s, best)


def test_candidate_beats_poor_milp_and_fcfs():
    # Hand-made candidate: only the best-margin booking, which beats FCFS's fill of a tiny deck.
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 70.0),), 1000.0, 0, 0.5),
                 (_bk(1, "spot", 10.0), _bk(2, "spot", 11.0)), 0.0, 0.0)
    cand = Plan("hand", {"B2": Slot("L1", 0)}, ["B1"])
    out = solve_optimal(s, time_limit_s=0.01, candidates=[cand])
    assert objective(s, out) >= objective(s, cand)
    assert check_plan(s, out) == []


@pytest.mark.parametrize("params", [
    ScenarioParams(n_lanes=1),
    ScenarioParams(reefer_plugs=0),
    ScenarioParams(max_dwt_t=10),
    ScenarioParams(lane_length_m=12.0),
    ScenarioParams(contract_share=0.0),
    ScenarioParams(n_requests=200, n_lanes=16),
])
def test_extreme_scenarios_solve_and_evaluate(params):
    s = generate_scenario(params)
    plan = solve_optimal(s)
    assert check_plan(s, plan) == []
    evaluate(s, plan)


@pytest.mark.parametrize("params", [
    ScenarioParams(n_lanes=1),
    ScenarioParams(ballast_tank_cap_t=0),
    ScenarioParams(max_heel_deg=0.5),
    ScenarioParams(max_dwt_t=10),
    ScenarioParams(n_requests=200, n_lanes=16),
    ScenarioParams(contract_share=0.0),
])
def test_extreme_scenarios_v2(params):
    s = generate_scenario(params)
    for plan in (solve_fcfs(s), solve_optimal(s)):
        assert check_plan(s, plan) == []
        evaluate(s, plan)


def _lopsided_deck(scenario) -> DeckState:
    """Load each request as far starboard and towards the bow as it may go, so ballast is needed."""
    deck = DeckState(scenario.vessel)
    vessel = scenario.vessel

    def lean(slot):
        lane = vessel.lane(slot.lane_id)
        return lane.y_m + lane.zone_x_m(slot.zone)

    for b in sorted(scenario.bookings, key=lambda b: -b.weight_t):  # heaviest first
        slots = deck.feasible_slots(b)
        if slots:
            deck.place(b, max(slots, key=lean))
    return deck


def _fcfs_deck(scenario) -> DeckState:
    deck = DeckState(scenario.vessel)
    for bid, slot in solve_fcfs(scenario).placements.items():
        deck.place(scenario.booking(bid), slot)
    return deck


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("make_deck", [_fcfs_deck, _lopsided_deck])
def test_closed_form_ballast_equals_milp_ballast(seed, make_deck):
    """Spec §5.6: on fixed placements the MILP's ballast is exactly the closed-form minimum."""
    s = generate_scenario(ScenarioParams(seed=seed))
    deck = make_deck(s)
    plan = Plan("fixed", deck.placements, [])
    closed, _ = plan_ballast(s, plan)
    model = build_model(s.vessel, [], s.contract_floor_m, s.shortfall_penalty_per_m, deck=deck)
    model.prob.solve(pulp.HiGHS(msg=False))
    assert pulp.LpStatus[model.prob.status] == "Optimal"
    milp_total = sum(v.value() or 0.0 for v in model.ballast.values())
    assert milp_total == pytest.approx(closed.total_t, abs=1e-6)
    if make_deck is _lopsided_deck:
        assert closed.total_t > 0  # the comparison is not trivially 0 == 0
