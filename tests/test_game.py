from roro_yield.deck import check_plan
from roro_yield.game import GameSession
from roro_yield.models import Booking, Lane, Scenario, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario


def bk(i, segment="spot", length=13.6):
    return Booking(f"B{i}", i, segment, "C", "semi_trailer", length, 10.0, False, 80.0, 0.0, 50.0)


def tiny(bookings, lanes=(30.0,), floor=0.0):
    vessel = Vessel("V", "A → B", tuple(Lane(f"L{i + 1}", l) for i, l in enumerate(lanes)), 1000.0, 5, 0.5)
    return Scenario(vessel, tuple(bookings), floor, 200.0)


def test_accept_places_and_advances():
    g = GameSession(tiny([bk(0), bk(1)]))
    assert g.current.id == "B0"
    assert g.accept(expected_index=0) is None
    assert g.index == 1
    assert g.deck.placements == {"B0": "L1"}
    assert g.log == [("B0", "accepted")]


def test_infeasible_accept_returns_reason_and_stays():
    g = GameSession(tiny([bk(0, length=40.0), bk(1)]))
    assert g.accept(expected_index=0) == "doesn't fit any lane"
    assert g.index == 0
    assert g.current.id == "B0"
    assert g.log == []


def test_reject_advances():
    g = GameSession(tiny([bk(0), bk(1)]))
    g.reject(expected_index=0)
    assert g.index == 1
    assert g.log == [("B0", "rejected")]


def test_stale_clicks_are_ignored():
    g = GameSession(tiny([bk(0), bk(1), bk(2)]))
    g.accept(expected_index=0)
    g.accept(expected_index=0)  # browser rerun replays the same click
    g.reject(expected_index=0)
    assert g.index == 1
    assert g.log == [("B0", "accepted")]


def test_finishes_after_last_booking():
    g = GameSession(tiny([bk(0)]))
    assert not g.is_finished
    g.reject(expected_index=0)
    assert g.is_finished
    assert g.current is None
    g.reject(expected_index=1)  # no-op after finish
    assert g.log == [("B0", "rejected")]


def test_full_random_game_gives_feasible_plan():
    s = generate_scenario(ScenarioParams(seed=3))
    g = GameSession(s)
    while not g.is_finished:
        if g.accept(expected_index=g.index) is not None:
            g.reject(expected_index=g.index)
    plan = g.to_plan()
    assert plan.method == "You"
    assert check_plan(s, plan) == []
    assert sorted(plan.accepted_ids + plan.rejected) == sorted(b.id for b in s.bookings)


def test_contract_floor_at_risk_after_rejecting_contracts():
    # Floor 27.2 m = both contracts. Rejecting one makes the floor unreachable.
    g = GameSession(tiny([bk(0, "contract"), bk(1, "contract"), bk(2)], lanes=(60.0,), floor=27.2))
    assert not g.contract_floor_at_risk()
    g.reject(expected_index=0)
    assert g.contract_floor_at_risk()
