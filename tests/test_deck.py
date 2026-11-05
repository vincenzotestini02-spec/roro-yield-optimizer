from dataclasses import replace

import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.models import DEFAULT_STABILITY, Booking, Lane, Plan, Scenario, Slot, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario
from roro_yield.stability import moments, required_ballast


def bk(i, length=13.6, weight=20.0, reefer=False, segment="spot"):
    return Booking(f"B{i}", i, segment, "C", "semi_trailer", length, weight, reefer, 100.0, 150.0, 100.0)


def scenario(bookings, lanes=(120.0, 120.0), dwt=1000.0, plugs=5, gap=0.5, ys=None, stab=None):
    ys = ys if ys is not None else [0.0] * len(lanes)
    vessel = Vessel(
        "V",
        "A to B",
        tuple(Lane(f"L{i + 1}", length, ys[i]) for i, length in enumerate(lanes)),
        dwt,
        plugs,
        gap,
        stab or DEFAULT_STABILITY,
    )
    return Scenario(vessel, tuple(bookings), 0.0, 200.0)


def test_one_unit_per_small_zone():
    bs = [bk(i) for i in range(2)]
    deck = DeckState(scenario(bs, lanes=(60.0,)).vessel)  # zones of 15 m, a unit needs 14.1
    assert deck.place(bs[0]) == Slot("L1", 0)
    assert deck.remaining_m[Slot("L1", 0)] == pytest.approx(15 - 14.1)
    assert deck.place(bs[1]) != Slot("L1", 0)
    assert sum(deck.remaining_m.values()) == pytest.approx(60 - 2 * 14.1)


def test_why_not_doesnt_fit_any_lane():
    truck = bk(0, length=16.5)
    deck = DeckState(scenario([truck], lanes=(48.0, 48.0)).vessel)  # 12 m zones
    assert deck.why_not(truck) == "doesn't fit any lane"


def test_why_not_no_space_left():
    bs = [bk(i) for i in range(5)]
    deck = DeckState(scenario(bs, lanes=(60.0,)).vessel)  # 4 zones of 15 m, one unit each
    for b in bs[:4]:
        deck.place(b)
    assert deck.why_not(bs[4]) == "no lane has enough space left"


def test_why_not_deadweight():
    bs = [bk(0, weight=30), bk(1, weight=30)]
    deck = DeckState(scenario(bs, dwt=50).vessel)
    deck.place(bs[0])
    assert deck.why_not(bs[1]) == "would exceed max deadweight"


def test_why_not_reefer_plug():
    bs = [bk(0, reefer=True), bk(1, reefer=True)]
    deck = DeckState(scenario(bs, plugs=1).vessel)
    deck.place(bs[0])
    assert deck.plugs_used == 1
    assert deck.why_not(bs[1]) == "no reefer plug available"


def test_place_raises_when_not_placeable():
    truck = bk(0, length=16.5)
    deck = DeckState(scenario([truck], lanes=(48.0,)).vessel)
    with pytest.raises(ValueError):
        deck.place(truck)


def test_best_slot_balances():
    stab = replace(DEFAULT_STABILITY, max_heel_deg=0.1)
    s = scenario([bk(0, weight=60), bk(1, weight=60)], ys=[-3.2, 3.2], stab=stab)
    deck = DeckState(s.vessel)
    first = deck.place(s.bookings[0])
    second = deck.place(s.bookings[1])
    assert first.lane_id != second.lane_id
    assert deck.placements == {"B0": first, "B1": second}


def test_ties_prefer_stern_then_lane_order():
    s = scenario([bk(0, weight=2.0)], ys=[-1.6, 1.6])
    deck = DeckState(s.vessel)
    assert deck.best_slot(s.bookings[0]) == Slot("L1", 0)


def test_unbalance_reason():
    stab = replace(DEFAULT_STABILITY, tank_cap_t=0.0, max_heel_deg=0.1)
    b = bk(0, weight=40)
    deck = DeckState(scenario([b], lanes=(120.0,), ys=[9.0], stab=stab).vessel)
    assert deck.why_not(b) == "would unbalance the ship beyond what ballast can correct"
    assert deck.best_slot(b) is None


def test_dwt_with_ballast_reason():
    stab = replace(DEFAULT_STABILITY, max_heel_deg=0.1)
    b = bk(0, weight=60)
    # cargo alone (60 t) fits in 61 t, but the ballast needed to correct its heel does not
    deck = DeckState(scenario([b], lanes=(120.0,), ys=[9.0], dwt=61.0, stab=stab).vessel)
    assert deck.why_not(b) == "would exceed max deadweight once ballast is added"
    assert deck.feasible_slots(b) == []


def test_place_rejects_infeasible_manual_slot():
    stab = replace(DEFAULT_STABILITY, tank_cap_t=0.0, max_heel_deg=0.1)
    b = bk(0, weight=40)
    s = scenario([b], ys=[9.0, 0.0], stab=stab)
    deck = DeckState(s.vessel)
    with pytest.raises(ValueError):
        deck.place(b, Slot("L1", 2))
    assert deck.loads == {} and deck.weight_t == 0
    assert deck.place(b, Slot("L2", 2)) == Slot("L2", 2)


def test_deck_state_copy_is_independent():
    b = bk(0)
    deck = DeckState(scenario([b]).vessel)
    clone = deck.copy()
    clone.place(b)
    assert deck.loads == {} and deck.weight_t == 0 and deck.moments == (0.0, 0.0)
    assert b.id in clone.loads


def test_deck_moments_match_stability_module():
    s = generate_scenario(ScenarioParams(seed=3))
    plan = solve_fcfs(s)
    deck = DeckState(s.vessel)
    for b in s.bookings:
        if b.id in plan.placements:
            deck.place(b, plan.placements[b.id])
    m = moments(list(deck.loads.values()), s.vessel)
    assert deck.moments == pytest.approx(m)
    assert deck.ballast == required_ballast(*m, s.vessel.stability)


def test_check_plan_empty_is_feasible():
    s = scenario([bk(0)])
    assert check_plan(s, Plan("x", {}, ["B0"])) == []


def test_check_plan_catches_violations():
    bs = [bk(0, weight=40, reefer=True), bk(1, weight=40, reefer=True), bk(2, weight=40), bk(3, length=20)]
    s = scenario(bs, lanes=(40.0, 120.0), dwt=100, plugs=1)
    plan = Plan("x", {"B0": Slot("L1", 0), "B1": Slot("L1", 0), "B2": Slot("L2", 0), "B3": Slot("L1", 1)}, [])
    problems = check_plan(s, plan)
    assert any("L1-Z0" in p for p in problems)  # zone overfilled
    assert any("L1-Z1" in p for p in problems)
    assert any("deadweight" in p for p in problems)
    assert any("reefer" in p for p in problems)


def test_check_plan_catches_heel_and_tank():
    stab = replace(DEFAULT_STABILITY, tank_cap_t=0.0, max_heel_deg=0.1)
    b = bk(0, weight=40)
    s = scenario([b], lanes=(120.0,), ys=[9.0], stab=stab)
    problems = check_plan(s, Plan("x", {"B0": Slot("L1", 0)}, []))
    assert any("tank" in p for p in problems)
    assert any("heel" in p for p in problems)


def test_check_plan_catches_bad_ids():
    s = scenario([bk(0)])
    assert check_plan(s, Plan("x", {"B9": Slot("L1", 0)}, []))
    assert check_plan(s, Plan("x", {"B0": Slot("L9", 0)}, []))
    assert check_plan(s, Plan("x", {"B0": Slot("L1", 7)}, []))
    assert check_plan(s, Plan("x", {"B0": Slot("L1", 0)}, ["B0"]))


def _fcfs_loads(s, plan):
    return [(s.booking(bid), slot) for bid, slot in plan.placements.items()]


def test_calibration_default():
    for seed in range(1, 6):
        s = generate_scenario(ScenarioParams(seed=seed))
        plan = solve_fcfs(s)
        deck = DeckState(s.vessel)
        for b, slot in _fcfs_loads(s, plan):
            deck.place(b, slot)
        assert deck.ballast.total_t <= 0.05 * s.vessel.max_dwt_t, (seed, deck.ballast)

        # same units, loaded balance-blind: stern-first, port-side lanes only (units that do not fit are dropped)
        port = [lane for lane in s.vessel.lanes if lane.y_m < 0]
        order = [Slot(lane.id, z) for z in range(4) for lane in port]
        rem = {sl: s.vessel.lane(sl.lane_id).zone_length_m for sl in order}
        loads = []
        for b, _ in _fcfs_loads(s, plan):
            length = b.effective_length(s.vessel.lashing_gap_m)
            for sl in order:
                if length <= rem[sl] + 1e-9:
                    rem[sl] -= length
                    loads.append((b, sl))
                    break
        bad = required_ballast(*moments(loads, s.vessel), s.vessel.stability)
        assert bad.total_t > 0.15 * s.vessel.max_dwt_t, (seed, bad)
