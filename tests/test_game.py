from roro_yield.deck import check_plan
from roro_yield.game import GameSession
from roro_yield.models import Booking, Lane, Scenario, Slot, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario


def bk(i, segment="spot", length=13.6):
    return Booking(f"B{i}", i, segment, "C", "semi_trailer", length, 10.0, False, 80.0, 0.0, 50.0)


PARAMS = ScenarioParams(seed=1)


def session(scenario):
    return GameSession(scenario, PARAMS)


def tiny(bookings, lanes=(60.0,), floor=0.0):
    vessel = Vessel("V", "A → B", tuple(Lane(f"L{i + 1}", l) for i, l in enumerate(lanes)), 1000.0, 5, 0.5)
    return Scenario(vessel, tuple(bookings), floor, 200.0)


def test_accept_places_and_advances():
    g = session(tiny([bk(0), bk(1)]))
    assert g.current.id == "B0"
    assert g.accept(expected_index=0) is None
    assert g.index == 1
    assert list(g.deck.placements) == ["B0"]
    assert g.deck.placements["B0"].lane_id == "L1"
    assert g.log == [("B0", "accepted", g.deck.placements["B0"])]


def test_infeasible_accept_returns_reason_and_stays():
    g = session(tiny([bk(0, length=40.0), bk(1)]))
    assert g.accept(expected_index=0) == "doesn't fit any lane"
    assert g.index == 0
    assert g.current.id == "B0"
    assert g.log == []


def test_reject_advances():
    g = session(tiny([bk(0), bk(1)]))
    g.reject(expected_index=0)
    assert g.index == 1
    assert g.log == [("B0", "rejected", None)]


def test_stale_clicks_are_ignored():
    g = session(tiny([bk(0), bk(1), bk(2)]))
    g.accept(expected_index=0)
    g.accept(expected_index=0)  # browser rerun replays the same click
    g.reject(expected_index=0)
    assert g.index == 1
    assert g.log == [("B0", "accepted", Slot("L1", 0))]


def test_finishes_after_last_booking():
    g = session(tiny([bk(0)]))
    assert not g.is_finished
    g.reject(expected_index=0)
    assert g.is_finished
    assert g.current is None
    g.reject(expected_index=1)  # no-op after finish
    assert g.log == [("B0", "rejected", None)]


def test_full_random_game_gives_feasible_plan():
    s = generate_scenario(ScenarioParams(seed=3))
    g = GameSession(s, ScenarioParams(seed=3))
    while not g.is_finished:
        if g.accept(expected_index=g.index) is not None:
            g.reject(expected_index=g.index)
    plan = g.to_plan()
    assert plan.method == "You"
    assert check_plan(s, plan) == []
    assert sorted(plan.accepted_ids + plan.rejected) == sorted(b.id for b in s.bookings)


def test_contract_floor_at_risk_after_rejecting_contracts():
    # Floor 27.2 m = both contracts. Rejecting one makes the floor unreachable.
    g = session(tiny([bk(0, "contract"), bk(1, "contract"), bk(2)], lanes=(60.0,), floor=27.2))
    g.accept(expected_index=0)
    g.accept(expected_index=1)
    assert not g.contract_floor_at_risk()  # both loaded: 27.2 m >= commitment
    h = session(tiny([bk(0, "contract"), bk(1, "contract"), bk(2)], lanes=(60.0,), floor=500.0))
    h.reject(expected_index=0)
    assert h.contract_floor_at_risk()


def two_lanes(bookings, **kw):
    return tiny(bookings, lanes=(60.0, 60.0), **kw)


def test_accept_with_slot_places_there():
    g = session(two_lanes([bk(0)]))
    assert g.accept(0, Slot("L2", 1)) is None
    assert g.deck.placements == {"B0": Slot("L2", 1)}
    assert g.log == [("B0", "accepted", Slot("L2", 1))]


def test_accept_with_infeasible_slot_returns_reason():
    g = session(two_lanes([bk(0, length=40.0)]))
    reason = g.accept(0, Slot("L1", 0))
    assert isinstance(reason, str) and reason
    assert g.index == 0 and g.log == []


def test_manual_flow():
    g = session(two_lanes([bk(0), bk(1)]))
    assert g.request_accept(0) is None
    assert g.pending_index == 0
    assert g.confirm_slot(0, Slot("L2", 1)) is None
    assert g.deck.placements == {"B0": Slot("L2", 1)}
    assert g.index == 1 and g.pending_index is None


def test_confirm_infeasible_slot_returns_reason():
    g = session(two_lanes([bk(0), bk(1)]))
    g.accept(0, Slot("L1", 0))
    assert g.request_accept(1) is None
    reason = g.confirm_slot(1, Slot("L1", 0))  # zone already full
    assert isinstance(reason, str) and reason
    assert g.index == 1 and list(g.deck.placements) == ["B0"] and g.pending_index == 1


def test_request_accept_unloadable_returns_reason_without_pending():
    g = session(tiny([bk(0, length=80.0)]))
    assert g.request_accept(0) == "doesn't fit any lane"
    assert g.pending_index is None


def test_confirm_without_pending_does_nothing():
    g = session(two_lanes([bk(0)]))
    assert g.confirm_slot(0, Slot("L1", 0)) is None
    assert g.index == 0 and g.deck.placements == {}


def test_pending_accept_cleared():
    g = session(two_lanes([bk(0), bk(1), bk(2)]))
    g.request_accept(0)
    g.reject(0)
    assert g.pending_index is None and g.deck.placements == {} and g.index == 1
    g.request_accept(1)
    g.cancel_pending()
    assert g.pending_index is None and g.index == 1 and g.deck.placements == {}


def test_stale_index_ignored_in_manual_mode():
    g = session(two_lanes([bk(0), bk(1)]))
    g.request_accept(0)
    g.confirm_slot(0, Slot("L1", 0))
    assert g.request_accept(0) is None and g.pending_index is None
    g.confirm_slot(0, Slot("L2", 0))
    assert g.index == 1 and len(g.deck.placements) == 1


def test_view_at_current_hides_future():
    g = session(two_lanes([bk(0), bk(1), bk(2)]))
    g.accept(0)
    v = g.view_at_current()
    assert v.current.id == "B1" and v.index == 1 and v.n_total == 3
    assert [b.id for b in v.history] == ["B0"]


def test_floor_risk_uses_expectation_not_queue():
    def risky(future_segment):
        bookings = [bk(0, "contract"), bk(1, future_segment), bk(2, future_segment)]
        return session(two_lanes(bookings, floor=500.0))

    a, b = risky("spot"), risky("contract")
    a.accept(0)
    b.accept(0)
    assert a.contract_floor_at_risk() == b.contract_floor_at_risk() is True
    # a tiny commitment is safe either way
    c = session(two_lanes([bk(0, "contract"), bk(1)], floor=1.0))
    c.accept(0)
    assert not c.contract_floor_at_risk()


def test_floor_risk_false_when_finished():
    g = session(two_lanes([bk(0, "contract")], floor=500.0))
    g.reject(0)
    assert not g.contract_floor_at_risk()
