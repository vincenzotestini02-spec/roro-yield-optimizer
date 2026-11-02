"""First-come-first-served baseline: accept each request in arrival order if it still fits."""

from __future__ import annotations

from .deck import DeckState
from .models import Plan, Scenario

FCFS_LABEL = "First come, first served"


def solve_fcfs(scenario: Scenario) -> Plan:
    deck = DeckState(scenario)
    rejected = []
    for b in sorted(scenario.bookings, key=lambda b: b.arrival):
        if deck.why_not(b) is None:
            deck.place(b)
        else:
            rejected.append(b.id)
    return Plan(FCFS_LABEL, dict(deck.placements), rejected)
