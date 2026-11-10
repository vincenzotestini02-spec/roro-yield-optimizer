import pytest

from roro_yield.deck import DeckState
from roro_yield.models import DEFAULT_STABILITY, Booking, Lane, Reservation, Vessel, customer_key
from roro_yield.simulator import ScenarioParams, generate_scenario

VESSEL = Vessel("V", "A → B", (Lane("L1", 70.0, 0.0),), 5000.0, 10, 0.5, DEFAULT_STABILITY)  # 70 m, zones of 17.5


def van(bid, customer):
    return Booking(bid, 0, "contract", customer, "van", 6.5, 3.0, False, 50.0, 0.0, 0.0)  # 7.0 m on deck


def test_no_reservations_change_nothing():
    s = generate_scenario(ScenarioParams(seed=3))
    plain, empty = DeckState(s.vessel), DeckState(s.vessel, ())
    for b in s.bookings:
        assert plain.feasible_slots(b) == empty.feasible_slots(b)
        assert plain.why_not(b) == empty.why_not(b)


def test_others_cannot_use_reserved_space():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 65.0)])  # 5 m of common space left
    assert deck.why_not(van("O1", "Baltic Logistics")) == "space is reserved for Nordfreight"
    assert deck.feasible_slots(van("O1", "Baltic Logistics")) == []


def test_the_reserved_customer_uses_its_quota():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 65.0)])
    assert deck.why_not(van("N1", "Nordfreight")) is None
    deck.place(van("N1", "Nordfreight"))
    assert deck.reserved_left() == pytest.approx(58.0)


def test_beyond_the_quota_the_customer_uses_common_space():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 7.0), Reservation("B", 49.0)])  # 14 m common
    deck.place(van("N1", "Nordfreight"))  # its quota
    deck.place(van("N2", "Nordfreight"))  # common space
    assert deck.reservation_status()[0]["left"] == 0.0
    assert deck.why_not(van("O1", "Other")) is None  # 7 m of common space still free
    deck.place(van("O1", "Other"))
    assert deck.why_not(van("O2", "Other")) == "space is reserved for B"


def test_reservations_do_not_steal_from_each_other():
    deck = DeckState(VESSEL, [Reservation("A", 7.0), Reservation("B", 56.0)])  # common 7 m
    deck.place(van("A1", "A"))   # uses A's quota
    deck.place(van("A2", "A"))   # uses the 7 m of common space
    assert deck.why_not(van("A3", "A")) == "space is reserved for B"


def test_customer_names_match_without_case_or_spaces():
    deck = DeckState(VESSEL, [Reservation(" nordfreight ", 65.0)])
    assert customer_key(" NordFreight ") == "nordfreight"
    assert deck.why_not(van("N1", "Nordfreight")) is None


def test_status_reports_used_and_left():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 20.0)])
    deck.place(van("N1", "Nordfreight"))
    assert deck.reservation_status() == [{"customer": "Nordfreight", "metres": 20.0, "used": 7.0, "left": 13.0}]


def test_removing_a_unit_gives_the_quota_back():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 20.0)])
    deck.place(van("N1", "Nordfreight"))
    deck.remove("N1")
    assert deck.reserved_left() == pytest.approx(20.0)


def test_copy_keeps_reservations():
    deck = DeckState(VESSEL, [Reservation("Nordfreight", 65.0)])
    assert deck.copy().why_not(van("O1", "Other")) == "space is reserved for Nordfreight"


def test_an_over_committed_deck_never_crashes_and_the_customer_keeps_its_quota():
    # Units on board first, then a reservation bigger than the space they leave (allowed: on board wins).
    deck = DeckState(VESSEL)
    deck.place(van("O1", "Other"))
    deck.place(van("O2", "Other"))
    deck = deck.with_reservations([Reservation("N", 60.0)])
    assert deck.why_not(van("N1", "N")) is None          # filling its own quota commits nothing new
    assert deck.why_not(van("O3", "Other")) == "space is reserved for N"
    for i in range(1, 7):
        deck.place(van(f"N{i}", "N"))
    reason = deck.why_not(van("N9", "N"))                # beyond the quota on a full deck: a reason, no crash
    assert isinstance(reason, str) and reason
