import pytest

from roro_yield.deck import DeckState, check_plan
from roro_yield.models import Booking, Lane, Plan, Scenario, Vessel


def bk(i, length=13.6, weight=20.0, reefer=False, segment="spot"):
    return Booking(f"B{i}", i, segment, "C", "semi_trailer", length, weight, reefer, 100.0, 150.0, 100.0)


def scenario(bookings, lanes=(30.0, 30.0), dwt=1000.0, plugs=5, gap=0.5):
    vessel = Vessel("V", "A → B", tuple(Lane(f"L{i + 1}", l) for i, l in enumerate(lanes)), dwt, plugs, gap)
    return Scenario(vessel, tuple(bookings), 0.0, 200.0)


def test_first_fit_fills_lane_then_moves_on():
    bs = [bk(i) for i in range(3)]
    deck = DeckState(scenario(bs))
    assert deck.place(bs[0]) == "L1"
    assert deck.place(bs[1]) == "L1"  # 2 x 14.1 = 28.2 <= 30
    assert deck.place(bs[2]) == "L2"
    assert deck.remaining_m["L1"] == pytest.approx(30 - 28.2)
    assert deck.placements == {"B0": "L1", "B1": "L1", "B2": "L2"}


def test_why_not_doesnt_fit_any_lane():
    truck = bk(0, length=16.5)
    deck = DeckState(scenario([truck], lanes=(12.0, 12.0)))
    assert deck.why_not(truck) == "doesn't fit any lane"


def test_why_not_no_space_left():
    bs = [bk(i) for i in range(3)]
    deck = DeckState(scenario(bs, lanes=(15.0, 15.0)))
    deck.place(bs[0])
    deck.place(bs[1])
    assert deck.why_not(bs[2]) == "no lane has enough space left"


def test_why_not_deadweight():
    bs = [bk(0, weight=30), bk(1, weight=30)]
    deck = DeckState(scenario(bs, dwt=50))
    deck.place(bs[0])
    assert deck.why_not(bs[1]) == "would exceed max deadweight"


def test_why_not_reefer_plug():
    bs = [bk(0, reefer=True), bk(1, reefer=True)]
    deck = DeckState(scenario(bs, plugs=1))
    deck.place(bs[0])
    assert deck.plugs_used == 1
    assert deck.why_not(bs[1]) == "no reefer plug available"


def test_place_raises_when_not_placeable():
    truck = bk(0, length=16.5)
    deck = DeckState(scenario([truck], lanes=(12.0,)))
    with pytest.raises(ValueError):
        deck.place(truck)


def test_check_plan_empty_is_feasible():
    s = scenario([bk(0)])
    assert check_plan(s, Plan("x", {}, ["B0"])) == []


def test_check_plan_catches_violations():
    bs = [bk(0, weight=40, reefer=True), bk(1, weight=40, reefer=True), bk(2, weight=40)]
    s = scenario(bs, lanes=(20.0, 30.0), dwt=100, plugs=1)
    plan = Plan("x", {"B0": "L1", "B1": "L1", "B2": "L2"}, [])
    problems = check_plan(s, plan)
    assert any("L1" in p for p in problems)
    assert any("deadweight" in p for p in problems)
    assert any("reefer" in p for p in problems)


def test_check_plan_catches_bad_ids():
    s = scenario([bk(0)])
    assert check_plan(s, Plan("x", {"B9": "L1"}, []))
    assert check_plan(s, Plan("x", {"B0": "L9"}, []))
    assert check_plan(s, Plan("x", {"B0": "L1"}, ["B0"]))
