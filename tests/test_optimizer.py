import time

import pytest

from roro_yield.deck import check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import evaluate, objective
from roro_yield.models import Booking, Lane, Scenario, Vessel
from roro_yield.optimizer import OPTIMAL_LABEL, solve_optimal
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
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 15.0),), 100.0, 0, 0.5),
                 (_bk(1, "spot", 500 / 13.6), _bk(2, "spot", 900 / 13.6)), 0.0, 200.0)
    assert solve_optimal(s).accepted_ids == ["B2"]


def test_meets_contract_floor_when_possible():
    # Room for one unit. Spot pays more, but skipping the contract costs 13.6 m x 200 EUR of penalty.
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 15.0),), 100.0, 0, 0.5),
                 (_bk(1, "contract", 50.0), _bk(2, "spot", 110.0)), 13.6, 200.0)
    plan = solve_optimal(s)
    assert plan.accepted_ids == ["B1"]
    assert evaluate(s, plan).shortfall_m == 0


def test_solves_default_scenario_under_10s():
    s = generate_scenario(ScenarioParams())
    start = time.perf_counter()
    solve_optimal(s)
    assert time.perf_counter() - start < 10


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
