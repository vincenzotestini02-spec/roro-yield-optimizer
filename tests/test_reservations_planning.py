from dataclasses import replace

from roro_yield.advisor import advise, view_for
from roro_yield.deck import DeckState
from roro_yield.models import DEFAULT_STABILITY, Booking, Lane, Reservation, Scenario, Vessel
from roro_yield.optimizer import solve_optimal
from roro_yield.planning import plan_accepted
from roro_yield.simulator import ScenarioParams, generate_scenario


def demo(n, seed=7):
    s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=n, seed=seed))
    return s.vessel, list(s.bookings)


def used(vessel, bookings, placements):
    return sum(b.effective_length(vessel.lashing_gap_m) for b in bookings if b.id in placements)


def test_plan_without_reservations_is_unchanged():
    vessel, bookings = demo(40)
    assert plan_accepted(vessel, bookings).plan.placements == plan_accepted(vessel, bookings, reservations=()).plan.placements


def test_plan_keeps_reserved_space_free():
    vessel, bookings = demo(60)
    result = plan_accepted(vessel, bookings, reservations=[Reservation("Nobody yet", 200.0)], time_limit_s=10)
    capacity = DeckState(vessel).capacity_m
    assert used(vessel, bookings, result.plan.placements) <= capacity - 200.0 + 1e-6


def test_accepted_booking_pushed_out_by_a_reservation_is_explained():
    vessel, bookings = demo(45)
    result = plan_accepted(vessel, bookings, reservations=[Reservation("Nobody yet", 400.0)], time_limit_s=10)
    assert any("reserved for Nobody yet" in reason for _, reason in result.excluded)


def test_a_reservation_never_costs_its_customer_a_booking():
    # A reservation holds metres on the whole ship, not zones: a unit can still miss out because of how
    # the zones are filled, but never because of its own customer's reservation.
    vessel, bookings = demo(60)
    for customer in sorted({b.customer for b in bookings if b.segment == "contract"}):
        theirs = {b.id for b in bookings if b.customer == customer}
        quota = sum(b.effective_length(vessel.lashing_gap_m) for b in bookings if b.id in theirs)
        without = plan_accepted(vessel, bookings, time_limit_s=10)
        held = plan_accepted(vessel, bookings, reservations=[Reservation(customer, quota)], time_limit_s=10)
        assert len(theirs & set(held.plan.placements)) >= len(theirs & set(without.plan.placements))
        assert not any(bid in theirs and "reserved" in reason for bid, reason in held.excluded)


def test_milp_respects_reservations():
    vessel, bookings = demo(60)
    deck = DeckState(vessel, [Reservation("Nobody yet", 150.0)])
    scenario = Scenario(vessel, tuple(bookings), 0.0, 0.0)
    plan = solve_optimal(scenario, time_limit_s=5, deck=deck)
    assert used(vessel, bookings, plan.placements) <= deck.capacity_m - 150.0 + 1e-6


def test_advisor_cannot_load_a_non_reserved_request_into_reserved_space():
    vessel = Vessel("V", "A → B", (Lane("L1", 70.0, 0.0),), 5000.0, 10, 0.5, DEFAULT_STABILITY)
    deck = DeckState(vessel, [Reservation("Nordfreight", 65.0)])
    request = Booking("R1", 0, "spot", "Other", "van", 6.5, 3.0, False, 100.0, 0.0, 0.0, arrival_frac=0.5)
    scenario = Scenario(vessel, (request,), 0.0, 0.0)
    v = advise(view_for(scenario, replace(ScenarioParams(), n_requests=30), deck, 0), k=3)
    assert not v.feasible and "reserved for Nordfreight" in v.reason


def test_a_reservation_added_after_a_plan_is_respected():
    # The usual flow: plan first, then reserve. The previous plan must not win over the reservation.
    vessel, bookings = demo(60)
    first = plan_accepted(vessel, bookings, time_limit_s=10)
    capacity = DeckState(vessel).capacity_m
    again = plan_accepted(vessel, bookings, previous=first.plan.placements,
                          reservations=[Reservation("Nobody yet", 200.0)], time_limit_s=10)
    assert used(vessel, bookings, again.plan.placements) <= capacity - 200.0 + 1e-6
    assert any("reserved for Nobody yet" in reason for _, reason in again.excluded)


def test_on_board_units_plus_reservations_beyond_the_deck_load_nothing_else():
    vessel, bookings = demo(30)
    first = plan_accepted(vessel, bookings, time_limit_s=5)
    on_board = frozenset(list(first.plan.placements)[:10])
    capacity = DeckState(vessel).capacity_m
    aboard = used(vessel, bookings, on_board)
    result = plan_accepted(vessel, bookings, previous=first.plan.placements, on_board=on_board,
                           reservations=[Reservation("Nobody yet", capacity - aboard + 30)], time_limit_s=5)
    assert set(result.plan.placements) == set(on_board)
    assert all("reserved for Nobody yet" in reason for _, reason in result.excluded)
