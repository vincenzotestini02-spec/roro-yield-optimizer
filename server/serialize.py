"""Engine objects to JSON-friendly dicts."""

from __future__ import annotations

from dataclasses import asdict

from roro_yield.advisor import Verdict
from roro_yield.deck import DeckState
from roro_yield.kpis import Kpis
from roro_yield.models import UNIT_LABELS, ZONES, Booking, Plan, Scenario, Slot


def booking_out(b: Booking) -> dict:
    return {
        "id": b.id,
        "segment": b.segment,
        "customer": b.customer,
        "unit_type": b.unit_type,
        "unit_label": UNIT_LABELS.get(b.unit_type, b.unit_type),
        "length_m": b.length_m,
        "weight_t": b.weight_t,
        "is_reefer": b.is_reefer,
        "rate_per_m": b.rate_per_m,
        "revenue": b.revenue,
        "margin": b.margin,
    }


def deck_out(deck: DeckState) -> dict:
    vessel, stab = deck.vessel, deck.vessel.stability
    used = sum(b.effective_length(vessel.lashing_gap_m) for b, _ in deck.loads.values())
    return {
        "vessel": vessel.name,
        "route": vessel.route,
        "zones": ZONES,
        "lanes": [{"id": lane.id, "length_m": lane.length_m, "y_m": lane.y_m} for lane in vessel.lanes],
        "placements": [{"booking_id": b.id, "slot": str(slot), "booking": booking_out(b)}
                       for b, slot in deck.loads.values()],
        "remaining_m": {str(slot): m for slot, m in deck.remaining_m.items()},
        "used_m": used,
        "capacity_m": vessel.total_lane_m,
        "usable_m": sum(vessel.zone_capacity_m(lane) * ZONES for lane in vessel.lanes),
        "broken_stowage_pct": vessel.broken_stowage_pct,
        "weight_t": deck.weight_t,
        "max_dwt_t": vessel.max_dwt_t,
        "plugs_used": deck.plugs_used,
        "reefer_plugs": vessel.reefer_plugs,
        "heel_deg": deck.heel_deg,
        "trim_m": deck.trim_m,
        "max_heel_deg": stab.max_heel_deg,
        "max_trim_m": stab.max_trim_m,
        "ballast": asdict(deck.ballast),
        "ballast_total_t": deck.ballast.total_t,
        "tank_cap_t": stab.tank_cap_t,
    }


def plan_deck(scenario: Scenario, plan: Plan) -> DeckState:
    deck = DeckState(scenario.vessel)
    for booking_id, slot in plan.placements.items():
        deck.place(scenario.booking(booking_id), slot)
    return deck


def kpis_out(k: Kpis) -> dict:
    return asdict(k)


def verdict_out(v: Verdict) -> dict:
    return {**asdict(v), "text": v.text}


def parse_slot(text: str) -> Slot:
    """`L1-Z0` to a Slot; ValueError on anything else."""
    lane_id, sep, zone = text.rpartition("-Z")
    if not sep or not lane_id or not zone.isdigit():
        raise ValueError(text)
    return Slot(lane_id, int(zone))
