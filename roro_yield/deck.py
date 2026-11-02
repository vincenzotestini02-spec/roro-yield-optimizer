"""Incremental deck state (used by the game and FCFS) and a plan feasibility checker."""

from __future__ import annotations

from .models import Booking, Plan, Scenario

EPS = 1e-9


class DeckState:
    """Tracks remaining lane length, weight and plugs while units are loaded one by one."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.remaining_m: dict[str, float] = {lane.id: lane.length_m for lane in scenario.vessel.lanes}
        self.weight_t: float = 0.0
        self.plugs_used: int = 0
        self.placements: dict[str, str] = {}

    def _first_fit(self, length: float) -> str | None:
        for lane_id, remaining in self.remaining_m.items():
            if length <= remaining + EPS:
                return lane_id
        return None

    def why_not(self, b: Booking) -> str | None:
        """None if the booking can be loaded now, otherwise a short human reason."""
        vessel = self.scenario.vessel
        length = b.effective_length(vessel.lashing_gap_m)
        if all(length > lane.length_m + EPS for lane in vessel.lanes):
            return "doesn't fit any lane"
        if self._first_fit(length) is None:
            return "no lane has enough space left"
        if self.weight_t + b.weight_t > vessel.max_dwt_t + EPS:
            return "would exceed max deadweight"
        if b.is_reefer and self.plugs_used >= vessel.reefer_plugs:
            return "no reefer plug available"
        return None

    def place(self, b: Booking) -> str:
        reason = self.why_not(b)
        if reason is not None:
            raise ValueError(f"{b.id}: {reason}")
        length = b.effective_length(self.scenario.vessel.lashing_gap_m)
        lane_id = self._first_fit(length)
        self.remaining_m[lane_id] -= length
        self.weight_t += b.weight_t
        self.plugs_used += int(b.is_reefer)
        self.placements[b.id] = lane_id
        return lane_id


def check_plan(scenario: Scenario, plan: Plan) -> list[str]:
    """Return every physical-constraint violation in `plan` (empty list = feasible)."""
    vessel = scenario.vessel
    known = {b.id: b for b in scenario.bookings}
    lanes = {lane.id: lane.length_m for lane in vessel.lanes}
    problems: list[str] = []

    used = {lane_id: 0.0 for lane_id in lanes}
    weight = 0.0
    plugs = 0
    for booking_id, lane_id in plan.placements.items():
        if booking_id not in known:
            problems.append(f"unknown booking {booking_id}")
            continue
        if lane_id not in lanes:
            problems.append(f"{booking_id} placed in unknown lane {lane_id}")
            continue
        b = known[booking_id]
        used[lane_id] += b.effective_length(vessel.lashing_gap_m)
        weight += b.weight_t
        plugs += int(b.is_reefer)
        if booking_id in plan.rejected:
            problems.append(f"{booking_id} is both placed and rejected")

    for lane_id, total in used.items():
        if total > lanes[lane_id] + EPS:
            problems.append(f"lane {lane_id} overfilled: {total:.1f} m > {lanes[lane_id]:.1f} m")
    if weight > vessel.max_dwt_t + EPS:
        problems.append(f"max deadweight exceeded: {weight:.1f} t > {vessel.max_dwt_t:.1f} t")
    if plugs > vessel.reefer_plugs:
        problems.append(f"reefer plugs exceeded: {plugs} > {vessel.reefer_plugs}")
    return problems
