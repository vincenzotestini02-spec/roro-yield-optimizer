"""Plan a set of accepted bookings: every one is mandatory, units on board stay put.

The optimizer is reused with each booking worth `METRE_WEIGHT` per metre and nothing else, so it
loads as many metres as the deck allows; at equal metres the ballast cost decides. A booking that
cannot be loaded is never dropped silently: it is returned with the reason from `DeckState`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .deck import DeckState
from .models import Booking, Plan, Scenario, Slot, Vessel
from .optimizer import solve_optimal

METRE_WEIGHT = 1000.0
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


def _fixed_deck(vessel: Vessel, by_id: dict[str, Booking], previous: dict[str, Slot],
                on_board: frozenset[str]) -> DeckState:
    deck = DeckState(vessel)
    for booking_id in sorted(on_board):
        b = by_id[booking_id]
        slot = previous.get(booking_id)
        if slot is None:
            raise OnBoardConflict(booking_id, "it is marked on board but has no position in the plan")
        if slot not in deck.remaining_m:
            raise OnBoardConflict(booking_id, f"its zone {slot} does not exist on this vessel")
        if slot not in deck.feasible_slots(b):
            raise OnBoardConflict(booking_id, deck.why_not(b) or f"it no longer fits in zone {slot}")
        deck.place(b, slot)
    return deck


def _keep_previous(deck: DeckState, others: Sequence[Booking], previous: dict[str, Slot]) -> DeckState | None:
    """The previous plan with new bookings added where they fit, or None if anything has to move."""
    trial = deck.copy()
    old = [b for b in others if b.id in previous]
    new = [b for b in others if b.id not in previous]
    for b in old:
        slot = previous[b.id]
        if slot not in trial.remaining_m or slot not in trial.feasible_slots(b):
            return None
        trial.place(b, slot)
    for b in new:
        slot = trial.best_slot(b)
        if slot is None:
            return None
        trial.place(b, slot)
    return trial


def plan_accepted(vessel: Vessel, bookings: Sequence[Booking], previous: dict[str, Slot] | None = None,
                  on_board: frozenset[str] = frozenset(), time_limit_s: float = 20) -> PlanningResult:
    by_id = {b.id: b for b in bookings}
    previous = {k: v for k, v in (previous or {}).items() if k in by_id}
    deck = _fixed_deck(vessel, by_id, previous, on_board)
    others = [b for b in bookings if b.id not in on_board]

    kept = _keep_previous(deck, others, previous)
    if kept is not None:
        placements = kept.placements
    else:
        weighted = tuple(replace(b, rate_per_m=METRE_WEIGHT, reefer_fee=0.0, handling_cost=0.0) for b in others)
        scenario = Scenario(vessel, weighted, 0.0, 0.0)
        start = {k: v for k, v in previous.items() if k not in on_board}
        candidates = (Plan("Previous", start, []),) if start else ()
        placements = solve_optimal(scenario, time_limit_s=time_limit_s, candidates=candidates, deck=deck).placements

    final = DeckState(vessel)
    for booking_id, slot in placements.items():
        final.place(by_id[booking_id], slot)
    missing = sorted((b for b in bookings if b.id not in placements), key=lambda b: (-b.length_m, b.id))
    excluded = [(b.id, final.why_not(b) or NO_ROOM) for b in missing]
    moved = [k for k, slot in previous.items() if k in placements and placements[k] != slot]
    order = [b.id for b in bookings if b.id in placements]
    plan = Plan(PLANNER_LABEL, {k: placements[k] for k in order}, [b.id for b in missing])
    return PlanningResult(plan, excluded, moved)
