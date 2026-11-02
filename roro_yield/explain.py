"""Find the player's decisions that cost the most versus the optimal plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .kpis import evaluate
from .models import UNIT_LABELS, Plan, Scenario


@dataclass(frozen=True)
class Decision:
    booking_id: str
    kind: Literal["accepted_not_optimal", "rejected_optimal"]
    impact_eur: float
    reason: str


def costly_decisions(scenario: Scenario, user: Plan, optimal: Plan, top_n: int = 4) -> list[Decision]:
    gap = scenario.vessel.lashing_gap_m
    user_ids, opt_ids = set(user.placements), set(optimal.placements)
    user_short = evaluate(scenario, user).shortfall_m > 0
    decisions = []
    for b in scenario.bookings:
        unit = UNIT_LABELS.get(b.unit_type, b.unit_type)
        if b.id in user_ids and b.id not in opt_ids:
            decisions.append(Decision(
                b.id, "accepted_not_optimal", abs(b.margin),
                f"You accepted {b.customer}'s {unit} at €{b.rate_per_m:.0f}/m. "
                f"Its {b.effective_length(gap):.1f} m were worth more to higher-yield cargo.",
            ))
        elif b.id in opt_ids and b.id not in user_ids:
            impact = abs(b.margin)
            if b.segment == "contract" and user_short:
                impact += scenario.shortfall_penalty_per_m * b.length_m
            decisions.append(Decision(
                b.id, "rejected_optimal", impact,
                f"You turned down {b.customer}'s {unit} at €{b.rate_per_m:.0f}/m — "
                f"€{b.margin:,.0f} of margin left on the quay.",
            ))
    decisions.sort(key=lambda d: d.impact_eur, reverse=True)
    return decisions[:top_n]
