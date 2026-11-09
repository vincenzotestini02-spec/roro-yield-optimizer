import time
from dataclasses import replace

from roro_yield.advisor import MOVE_COST_EUR, advise, find_moves, view_for
from roro_yield.deck import DeckState
from roro_yield.models import DEFAULT_STABILITY, Booking, Lane, Scenario, Slot, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario

STAB = replace(DEFAULT_STABILITY, tank_cap_t=2000.0)


def unit(bid, length, rate=60.0, weight=3.0, arrival=0):
    return Booking(bid, arrival, "spot", "Test", "van", length, weight, False, rate, 0.0, 0.0, arrival_frac=0.5)


def one_lane():
    vessel = Vessel("V", "A → B", (Lane("L1", 60.0, 0.0),), 5000.0, 10, 0.5, STAB)  # 4 zones of 15 m
    deck = DeckState(vessel)
    vans = [unit(f"V{i}", 6.5) for i in range(4)]
    for i, v in enumerate(vans):
        deck.place(v, Slot("L1", i))  # 8 m left in every zone
    return vessel, deck, vans


def two_lanes():
    # L1: 4 zones of 15 m, each with a van and a car (12.3 m used); L2: 4 empty zones of 10 m.
    vessel = Vessel("V", "A → B", (Lane("L1", 60.0, -1.6), Lane("L2", 40.0, 1.6)), 5000.0, 10, 0.5, STAB)
    deck = DeckState(vessel)
    units = []
    for z in range(4):
        van, car = unit(f"V{z}", 6.5), unit(f"C{z}", 4.8)
        deck.place(van, Slot("L1", z))
        deck.place(car, Slot("L1", z))
        units += [van, car]
    return vessel, deck, units


def test_one_move_makes_room():
    _, deck, _ = one_lane()
    moves = find_moves(deck, unit("T1", 13.6))
    assert moves is not None and len(moves) == 1


def test_two_moves_when_one_is_not_enough():
    _, deck, _ = two_lanes()
    trailer = unit("T1", 13.6)
    moves = find_moves(deck, trailer)
    assert moves is not None and len(moves) == 2
    trial = deck.copy()
    for m in moves:
        b, _ = trial.remove(m.booking_id)
        trial.place(b, m.to_slot)
    assert trial.why_not(trailer) is None


def test_no_moves_when_nothing_helps():
    _, deck, _ = one_lane()
    assert find_moves(deck, unit("LONG", 16.5)) is None  # longer than any 15 m zone


def _view(vessel, deck, placed, current):
    scenario = Scenario(vessel, tuple(placed) + (current,), 0.0, 0.0)
    return view_for(scenario, ScenarioParams(n_requests=30), deck, len(placed))


def test_suggested_moves_are_in_the_verdict():
    vessel, deck, vans = one_lane()
    v = advise(_view(vessel, deck, vans, unit("T1", 13.6, rate=110.0)), k=5)
    assert v.feasible and len(v.moves) == 1
    assert v.text.startswith("Move ")


def test_moves_are_not_suggested_when_they_cost_more_than_they_earn():
    vessel, deck, vans = one_lane()
    cheap = unit("T1", 13.6, rate=0.5)  # earns about €7 against €80 per move
    v = advise(_view(vessel, deck, vans, cheap), k=5)
    assert not v.feasible and v.moves == ()
    assert MOVE_COST_EUR == 80.0


def test_search_stays_fast_on_a_big_deck():
    s = generate_scenario(ScenarioParams(n_lanes=16, lane_length_m=156.0, n_requests=190, max_dwt_t=5000.0,
                                         displacement_t=26000.0, gm_m=2.0, mtc_tm_per_cm=320.0,
                                         ballast_tank_cap_t=600.0, reefer_plugs=40, seed=5))
    deck = DeckState(s.vessel)
    for b in s.bookings:
        if deck.why_not(b) is None:
            deck.place(b)
    start = time.perf_counter()
    find_moves(deck, unit("BIG", 16.5))
    assert time.perf_counter() - start < 2.0
