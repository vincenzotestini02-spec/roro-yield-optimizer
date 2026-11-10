"""Plan a set of accepted bookings: every one is mandatory, units on board stay put.

The optimizer is reused with each booking worth `METRE_WEIGHT` per metre and nothing else, so it
loads as many metres as the deck allows; at equal metres the ballast cost decides. A booking that
cannot be loaded is never dropped silently: it is returned with the reason from `DeckState`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .deck import DeckState
from .models import Booking, Plan, Reservation, Scenario, Slot, Vessel, customer_key
from .optimizer import solve_optimal

METRE_WEIGHT = 1000.0
# Staying put is worth less than half a metre of cargo, so the planner never trades loaded
# metres for fewer moves, but between equally full plans it keeps units where they were.
KEEP_BONUS = 400.0
# Bookings of a customer with a reservation fill that reservation first: worth a little more per
# metre, still far less than a metre of cargo, so no loaded metre is ever traded for it.
RESERVED_BONUS_PER_M = 50.0
PLANNER_LABEL = "Planner"
NO_ROOM = "no zone can take it with the units already planned"


class OnBoardConflict(Exception):
    """A unit marked on board cannot stay at its position with the current vessel settings."""

    def __init__(self, booking_id: str, reason: str):
        super().__init__(f"{booking_id}: {reason}")
        self.booking_id = booking_id
        self.reason = reason


@dataclass(frozen=True)
class PlanningResult:
    plan: Plan
    excluded: list[tuple[str, str]]
    moved: list[str]


def place_all(deck: DeckState, items: Sequence[tuple[Booking, Slot]]) -> list[tuple[Booking, Slot, str]]:
    """Place units at given slots in any order that works; return those that never fit, with reasons.

    `DeckState` checks ballast and deadweight after every unit, while a plan only has to be feasible
    once complete, so a unit refused early can fit after others are on. Repeat passes until no
    progress is made.
    """
    pending = list(items)
    while pending:
        left = []
        for b, slot in pending:
            if slot in deck.remaining_m and slot in deck.feasible_slots(b):
                deck.place(b, slot)
            else:
                left.append((b, slot))
        if len(left) == len(pending):
            break
        pending = left
    failed = []
    for b, slot in pending:
        if slot not in deck.remaining_m:
            failed.append((b, slot, f"its zone {slot} does not exist on this vessel"))
        else:
            failed.append((b, slot, deck.why_not(b) or f"it no longer fits in zone {slot}"))
    return failed


def _fixed_deck(vessel: Vessel, by_id: dict[str, Booking], previous: dict[str, Slot],
                on_board: frozenset[str], reservations: Sequence[Reservation] = ()) -> DeckState:
    deck = DeckState(vessel)  # units on board are physically there: no reservation can push them out
    for booking_id in sorted(on_board):
        if booking_id not in previous:
            raise OnBoardConflict(booking_id, "it has no zone in the plan yet")
    failed = place_all(deck, [(by_id[k], previous[k]) for k in sorted(on_board)])
    if failed:
        b, _, reason = failed[0]
        raise OnBoardConflict(b.id, reason)
    return deck.with_reservations(reservations)


def _keep_previous(deck: DeckState, others: Sequence[Booking], previous: dict[str, Slot]) -> DeckState | None:
    """The previous plan with new bookings added where they fit, or None if anything has to move."""
    trial = deck.copy()
    old = [b for b in others if b.id in previous]
    new = [b for b in others if b.id not in previous]
    if place_all(trial, [(b, previous[b.id]) for b in old]):
        return None
    for b in new:
        slot = trial.best_slot(b)
        if slot is None:
            return None
        trial.place(b, slot)
    return trial


def plan_accepted(vessel: Vessel, bookings: Sequence[Booking], previous: dict[str, Slot] | None = None,
                  on_board: frozenset[str] = frozenset(), time_limit_s: float = 20,
                  reservations: Sequence[Reservation] = ()) -> PlanningResult:
    by_id = {b.id: b for b in bookings}
    previous = {k: v for k, v in (previous or {}).items() if k in by_id}
    deck = _fixed_deck(vessel, by_id, previous, on_board, reservations)
    others = [b for b in bookings if b.id not in on_board]

    kept = _keep_previous(deck, others, previous)
    if kept is not None:
        placements = kept.placements
    else:
        reserved = {customer_key(r.customer) for r in reservations}
        weighted = tuple(replace(b, rate_per_m=METRE_WEIGHT + (RESERVED_BONUS_PER_M if customer_key(b.customer) in reserved else 0.0),
                                 reefer_fee=0.0, handling_cost=0.0) for b in others)
        scenario = Scenario(vessel, weighted, 0.0, 0.0)
        start = {k: v for k, v in previous.items() if k not in on_board}
        candidates = (Plan("Previous", start, []),) if start else ()
        placements = solve_optimal(scenario, time_limit_s=time_limit_s, candidates=candidates, deck=deck,
                                   keep=start, keep_bonus=KEEP_BONUS).placements

    final = DeckState(vessel, reservations)
    place_all(final, [(by_id[k], slot) for k, slot in placements.items()])
    missing = sorted((b for b in bookings if b.id not in placements), key=lambda b: (-b.length_m, b.id))
    excluded = [(b.id, final.why_not(b) or NO_ROOM) for b in missing]
    moved = [k for k, slot in previous.items() if k in placements and placements[k] != slot]
    order = [b.id for b in bookings if b.id in placements]
    plan = Plan(PLANNER_LABEL, {k: placements[k] for k in order}, [b.id for b in missing])
    return PlanningResult(plan, excluded, moved)
