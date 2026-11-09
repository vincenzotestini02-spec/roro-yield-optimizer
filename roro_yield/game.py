"""The planner game: requests arrive one by one and the player accepts or rejects them."""

from __future__ import annotations

from .advisor import PolicyView, view_for
from .deck import DeckState
from .models import Booking, Plan, Scenario, Slot
from .simulator import ScenarioParams, expected_contract_m

PLAYER_LABEL = "You"


class GameSession:
    def __init__(self, scenario: Scenario, params: ScenarioParams):
        self.scenario = scenario
        self.params = params
        self.queue = sorted(scenario.bookings, key=lambda b: b.arrival)
        self.index = 0
        self.pending_index: int | None = None  # manual mode: accept clicked, slot not chosen yet
        self.deck = DeckState(scenario.vessel)
        self.log: list[tuple[str, str, Slot | None]] = []
        self.moves = 0
        self._expected_cache: dict[int, float] = {}

    @property
    def is_finished(self) -> bool:
        return self.index >= len(self.queue)

    @property
    def current(self) -> Booking | None:
        return None if self.is_finished else self.queue[self.index]

    def _stale(self, expected_index: int) -> bool:
        return expected_index != self.index or self.is_finished

    def _slot_reason(self, b: Booking, slot: Slot) -> str | None:
        """None if `b` can go into `slot`, else a short human reason."""
        reason = self.deck.why_not(b)
        if reason is not None:
            return reason
        if slot not in self.deck.feasible_slots(b):
            return "that zone can't take this unit (not enough space or stability)"
        return None

    def _load(self, slot: Slot | None) -> str | None:
        b = self.current
        reason = self.deck.why_not(b) if slot is None else self._slot_reason(b, slot)
        if reason is not None:
            return reason
        placed = self.deck.place(b, slot)
        self.log.append((b.id, "accepted", placed))
        self.pending_index = None
        self.index += 1
        return None

    def accept(self, expected_index: int, slot: Slot | None = None) -> str | None:
        """Load the current request (auto slot unless `slot` given). Returns None on success,
        or the reason it can't be loaded. Stale `expected_index` clicks are ignored."""
        if self._stale(expected_index):
            return None
        return self._load(slot)

    def request_accept(self, expected_index: int) -> str | None:
        """Manual mode step 1: mark the current request as pending a slot choice."""
        if self._stale(expected_index):
            return None
        reason = self.deck.why_not(self.current)
        if reason is not None:
            return reason
        self.pending_index = expected_index
        return None

    def confirm_slot(self, expected_index: int, slot: Slot) -> str | None:
        """Manual mode step 2: load the pending request into `slot`."""
        if self._stale(expected_index) or self.pending_index != expected_index:
            return None
        return self._load(slot)

    def cancel_pending(self) -> None:
        self.pending_index = None

    def reject(self, expected_index: int) -> None:
        if self._stale(expected_index):
            return
        self.log.append((self.current.id, "rejected", None))
        self.pending_index = None
        self.index += 1

    def view_at_current(self) -> PolicyView:
        """The advisor's view of the current request. Raises ValueError once the game is finished."""
        if self.is_finished:
            raise ValueError("game is finished: no current request")
        return view_for(self.scenario, self.params, self.deck, self.index)

    def contract_floor_at_risk(self) -> bool:
        """True when loaded contract metres plus the expected contract metres still to come fall
        short of the commitment. Uses only the demand distribution, never the real queue."""
        if self.is_finished:
            return False
        loaded = sum(self.scenario.booking(i).length_m for i in self.deck.placements
                     if self.scenario.booking(i).segment == "contract")
        if self.index not in self._expected_cache:
            remaining = len(self.queue) - self.index - 1
            self._expected_cache[self.index] = expected_contract_m(
                self.params, self.current.arrival_frac, remaining)
        return loaded + self._expected_cache[self.index] < self.scenario.contract_commitment_m - 1e-9

    def move(self, booking_id: str, slot: Slot) -> str | None:
        """Move a loaded unit to another zone. None on success, otherwise the reason; nothing changes then."""
        if self.is_finished:
            return "the ship has sailed"
        if booking_id not in self.deck.loads:
            return f"{booking_id} is not on the deck"
        if slot not in self.deck.remaining_m:
            return f"{slot} is not a zone of this ship"
        b, old = self.deck.remove(booking_id)
        if slot == old or slot not in self.deck.feasible_slots(b):
            self.deck.place(b, old)
            return "it is already there" if slot == old else "it does not fit there (space or stability)"
        self.deck.place(b, slot)
        self.moves += 1
        self.log.append((booking_id, "moved", slot))
        return None

    def to_plan(self) -> Plan:
        rejected = [booking_id for booking_id, action, _ in self.log if action == "rejected"]
        rejected += [b.id for b in self.queue[self.index:]]
        return Plan(PLAYER_LABEL, dict(self.deck.placements), rejected, moves=self.moves)
