"""The planner game: requests arrive one by one and the player accepts or rejects them."""

from __future__ import annotations

from .deck import DeckState
from .models import Booking, Plan, Scenario

PLAYER_LABEL = "You"


class GameSession:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.queue = sorted(scenario.bookings, key=lambda b: b.arrival)
        self.index = 0
        self.deck = DeckState(scenario.vessel)
        self.log: list[tuple[str, str]] = []

    @property
    def is_finished(self) -> bool:
        return self.index >= len(self.queue)

    @property
    def current(self) -> Booking | None:
        return None if self.is_finished else self.queue[self.index]

    def accept(self, expected_index: int) -> str | None:
        """Load the current request. Returns None on success, or the reason it can't be loaded.
        Clicks whose `expected_index` is stale (e.g. replayed on a rerun) are ignored."""
        if expected_index != self.index or self.is_finished:
            return None
        b = self.current
        reason = self.deck.why_not(b)
        if reason is not None:
            return reason
        self.deck.place(b)
        self.log.append((b.id, "accepted"))
        self.index += 1
        return None

    def reject(self, expected_index: int) -> None:
        if expected_index != self.index or self.is_finished:
            return
        self.log.append((self.current.id, "rejected"))
        self.index += 1

    def contract_floor_at_risk(self) -> bool:
        """True when even accepting every remaining contract request can't reach the floor."""
        loaded = sum(self.scenario.booking(i).length_m for i in self.deck.placements
                     if self.scenario.booking(i).segment == "contract")
        still_to_come = sum(b.length_m for b in self.queue[self.index:] if b.segment == "contract")
        return loaded + still_to_come < self.scenario.contract_floor_m - 1e-9

    def to_plan(self) -> Plan:
        rejected = [booking_id for booking_id, action in self.log if action == "rejected"]
        rejected += [b.id for b in self.queue[self.index:]]
        return Plan(PLAYER_LABEL, dict(self.deck.placements), rejected)
