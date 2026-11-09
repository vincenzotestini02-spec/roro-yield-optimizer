import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import objective
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams, generate_scenario

# FCFS score of seeds 1-3 with the engine before broken stowage existed.
FCFS_V2 = {1: 43657.950999999994, 2: 36704.60857438943, 3: 37236.992}


def used_m(scenario, plan):
    return sum(scenario.booking(i).effective_length(scenario.vessel.lashing_gap_m) for i in plan.placements)


def test_defaults_reproduce_previous_results():
    for seed in (1, 2, 3):
        s = generate_scenario(ScenarioParams(seed=seed))
        assert s.vessel.broken_stowage_pct == 0.0 and s.vessel.stability.displacement_t == 8000.0
        assert objective(s, solve_fcfs(s)) == pytest.approx(FCFS_V2[seed])


def test_broken_stowage_shrinks_every_zone():
    s = generate_scenario(ScenarioParams(broken_stowage_pct=0.15))
    deck = DeckState(s.vessel)
    assert all(m == pytest.approx(30.0 * 0.85) for m in deck.remaining_m.values())


def test_lost_space_loads_fewer_metres():
    base = generate_scenario(ScenarioParams(seed=3))
    lost = generate_scenario(ScenarioParams(seed=3, broken_stowage_pct=0.2))
    assert used_m(lost, solve_fcfs(lost)) < used_m(base, solve_fcfs(base))


def test_optimizer_respects_lost_space():
    s = generate_scenario(ScenarioParams(seed=3, broken_stowage_pct=0.2))
    assert check_plan(s, solve_optimal(s, time_limit_s=3)) == []


def test_extreme_lost_space_explains_long_units():
    s = generate_scenario(ScenarioParams(n_lanes=1, lane_length_m=70.0, broken_stowage_pct=0.3))
    truck = next(b for b in s.bookings if b.length_m >= 16)
    assert "doesn't fit" in (DeckState(s.vessel).why_not(truck) or "")


def test_stability_constants_come_from_params():
    s = generate_scenario(ScenarioParams(displacement_t=20000, gm_m=2.0, mtc_tm_per_cm=250))
    stab = s.vessel.stability
    assert (stab.displacement_t, stab.gm_m, stab.mtc_tm_per_cm) == (20000, 2.0, 250)
