from dataclasses import replace

import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import objective
from roro_yield.models import Booking, Scenario, Slot
from roro_yield.optimizer import solve_optimal
from roro_yield.planning import OnBoardConflict, plan_accepted
from roro_yield.simulator import ScenarioParams, generate_scenario

# solve_optimal(time_limit_s=3) on the 6-lane default, seeds 1-3, before the deck argument existed.
OPTIMAL_BEFORE = {1: 47750.687, 2: 45652.64, 3: 48491.822129944994}


def demo(n, seed=7):
    s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=n, seed=seed))
    return s.vessel, list(s.bookings)


def metres(bookings, placements, gap=0.5):
    return sum(b.length_m + gap for b in bookings if b.id in placements)


def unit(bid, length, weight=3.0):
    return Booking(bid, 0, "contract", "Test", "van", length, weight, False, 50.0, 0.0, 0.0)


def test_solve_optimal_default_is_unchanged():
    # A generous time limit keeps this independent of machine load; HiGHS stops at a 0.5% gap.
    for seed, value in OPTIMAL_BEFORE.items():
        s = generate_scenario(ScenarioParams(seed=seed))
        assert objective(s, solve_optimal(s, time_limit_s=30)) >= value * (1 - 0.006)


def test_all_fit_means_nothing_excluded():
    vessel, bookings = demo(30)
    result = plan_accepted(vessel, bookings)
    assert result.excluded == [] and set(result.plan.placements) == {b.id for b in bookings}


def test_overbooked_sailing_excludes_with_reasons():
    vessel, bookings = demo(90)
    result = plan_accepted(vessel, bookings, time_limit_s=10)
    assert result.excluded and all(reason for _, reason in result.excluded)
    lengths = [next(b.length_m for b in bookings if b.id == bid) for bid, _ in result.excluded]
    assert lengths == sorted(lengths, reverse=True)


def test_excluded_metres_are_minimal():
    vessel, bookings = demo(90)
    result = plan_accepted(vessel, bookings, time_limit_s=10)
    fcfs = solve_fcfs(Scenario(vessel, tuple(bookings), 0.0, 0.0))
    assert metres(bookings, result.plan.placements) >= metres(bookings, fcfs.placements) - 1e-6


def test_on_board_units_never_move():
    vessel, bookings = demo(40)
    first = plan_accepted(vessel, bookings[:30])
    keep = frozenset(list(first.plan.placements)[:3])
    later = plan_accepted(vessel, bookings, previous=first.plan.placements, on_board=keep, time_limit_s=10)
    for bid in keep:
        assert later.plan.placements[bid] == first.plan.placements[bid]


def test_new_booking_that_fits_moves_nothing():
    vessel, bookings = demo(31)
    first = plan_accepted(vessel, bookings[:30])
    small = min(bookings[30:], key=lambda b: b.length_m)
    later = plan_accepted(vessel, bookings[:30] + [small], previous=first.plan.placements)
    assert later.moved == [] and small.id in later.plan.placements


def test_replan_lists_moved_units():
    vessel = generate_scenario(ScenarioParams(n_lanes=1, lane_length_m=60.0)).vessel  # 4 zones of 15 m
    vans = [unit(f"V{i}", 6.5) for i in range(4)]
    previous = {f"V{i}": Slot("L1", i) for i in range(4)}  # one van per zone: 8 m left in each
    trailer = unit("T1", 13.6)
    result = plan_accepted(vessel, vans + [trailer], previous=previous)
    assert "T1" in result.plan.placements and result.excluded == []
    changed = {bid for bid in previous if result.plan.placements.get(bid) != previous[bid]}
    assert result.moved and set(result.moved) == changed


def test_on_board_unit_that_no_longer_fits_raises():
    vessel, bookings = demo(5)
    with pytest.raises(OnBoardConflict) as error:
        plan_accepted(vessel, bookings, previous={bookings[0].id: Slot("L6", 0)}, on_board=frozenset({bookings[0].id}))
    assert error.value.booking_id == bookings[0].id and error.value.reason


def test_plan_respects_check_plan():
    vessel, bookings = demo(70)
    result = plan_accepted(vessel, bookings, time_limit_s=10)
    assert check_plan(Scenario(vessel, tuple(bookings), 0.0, 0.0), result.plan) == []


def test_lost_space_is_respected():
    s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=60, broken_stowage_pct=0.15, seed=3))
    result = plan_accepted(s.vessel, list(s.bookings), time_limit_s=10)
    assert check_plan(replace(s, contract_commitment_m=0.0), result.plan) == []


def test_a_replan_after_one_new_unit_keeps_most_units_in_place():
    checked = 0
    for seed in range(1, 9):
        vessel, bookings = demo(40, seed=seed)
        first = plan_accepted(vessel, bookings, time_limit_s=10)
        if first.excluded:
            continue
        truck = replace(bookings[0], id="TRUCK", length_m=16.5, unit_type="accompanied_truck", weight_t=30.0)
        deck = DeckState(vessel)
        for bid, slot in first.plan.placements.items():
            deck.place(next(b for b in bookings if b.id == bid), slot)
        if deck.best_slot(truck) is not None:
            continue  # the fast path places it without moves: not the case under test
        later = plan_accepted(vessel, bookings + [truck], previous=first.plan.placements, time_limit_s=10)
        checked += 1
        assert len(later.moved) <= 0.25 * len(first.plan.placements), (seed, len(later.moved))
    assert checked > 0


def test_marking_every_unit_on_board_after_a_plan_never_conflicts():
    for seed in range(1, 6):
        s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=45, ballast_tank_cap_t=30.0, seed=seed))
        first = plan_accepted(s.vessel, list(s.bookings), time_limit_s=5)
        again = plan_accepted(s.vessel, list(s.bookings), previous=first.plan.placements,
                              on_board=frozenset(first.plan.placements), time_limit_s=5)
        assert again.plan.placements == first.plan.placements
