"""Slot-based deck state (used by the game and FCFS) and a stability-aware plan checker.

`DeckState` only knows the `Vessel`: it never sees a Scenario's bookings.
"""

from __future__ import annotations

from .models import ZONES, Booking, Plan, Scenario, Slot, Vessel
from .stability import (
    Ballast,
    ballast_fits,
    moments,
    required_ballast,
    residual_heel_deg,
    residual_trim_m,
)

EPS = 1e-9


class DeckState:
    """Tracks remaining zone length, weight, plugs and the heel/trim moments as units are loaded."""

    def __init__(self, vessel: Vessel):
        self.vessel = vessel
        self.remaining_m: dict[Slot, float] = {
            Slot(lane.id, z): vessel.zone_capacity_m(lane) for lane in vessel.lanes for z in range(ZONES)
        }
        self.loads: dict[str, tuple[Booking, Slot]] = {}
        self.weight_t: float = 0.0
        self.plugs_used: int = 0
        self._m_t: float = 0.0
        self._m_l: float = 0.0
        self._lane_order = {lane.id: i for i, lane in enumerate(vessel.lanes)}

    # ---- derived state -------------------------------------------------
    @property
    def placements(self) -> dict[str, Slot]:
        return {bid: slot for bid, (_, slot) in self.loads.items()}

    @property
    def moments(self) -> tuple[float, float]:
        return self._m_t, self._m_l

    @property
    def ballast(self) -> Ballast:
        return required_ballast(self._m_t, self._m_l, self.vessel.stability)

    @property
    def heel_deg(self) -> float:
        return residual_heel_deg(self._m_t, self.ballast, self.vessel.stability)

    @property
    def trim_m(self) -> float:
        return residual_trim_m(self._m_l, self.ballast, self.vessel.stability)

    def copy(self) -> "DeckState":
        other = DeckState.__new__(DeckState)
        other.vessel = self.vessel
        other.remaining_m = dict(self.remaining_m)
        other.loads = dict(self.loads)
        other.weight_t = self.weight_t
        other.plugs_used = self.plugs_used
        other._m_t = self._m_t
        other._m_l = self._m_l
        other._lane_order = self._lane_order
        return other

    # ---- feasibility ---------------------------------------------------
    def _ballast_if(self, b: Booking, slot: Slot) -> Ballast:
        lane = self.vessel.lane(slot.lane_id)
        m_t = self._m_t + b.weight_t * lane.y_m
        m_l = self._m_l + b.weight_t * lane.zone_x_m(slot.zone)
        return required_ballast(m_t, m_l, self.vessel.stability)

    def _space_slots(self, b: Booking) -> list[Slot]:
        length = b.effective_length(self.vessel.lashing_gap_m)
        return [s for s, rem in self.remaining_m.items() if length <= rem + EPS]

    def _slot_ok(self, b: Booking, slot: Slot) -> tuple[bool, bool]:
        """(ballast fits the tanks, cargo + ballast within DWT) if `b` were loaded at `slot`."""
        ballast = self._ballast_if(b, slot)
        fits = ballast_fits(ballast, self.vessel.stability)
        dwt_ok = self.weight_t + b.weight_t + ballast.total_t <= self.vessel.max_dwt_t + EPS
        return fits, dwt_ok

    def feasible_slots(self, b: Booking) -> list[Slot]:
        if b.is_reefer and self.plugs_used >= self.vessel.reefer_plugs:
            return []
        if self.weight_t + b.weight_t > self.vessel.max_dwt_t + EPS:
            return []
        out = []
        for slot in self._space_slots(b):
            fits, dwt_ok = self._slot_ok(b, slot)
            if fits and dwt_ok:
                out.append(slot)
        return out

    def best_slot(self, b: Booking) -> Slot | None:
        """Slot giving the least ballast; ties go to the lower zone, then to lane order."""
        slots = self.feasible_slots(b)
        if not slots:
            return None
        return min(
            slots,
            key=lambda s: (round(self._ballast_if(b, s).total_t, 9), s.zone, self._lane_order[s.lane_id]),
        )

    def why_not(self, b: Booking) -> str | None:
        """None if the booking can be loaded now, otherwise a short human reason."""
        vessel = self.vessel
        length = b.effective_length(vessel.lashing_gap_m)
        if all(length > vessel.zone_capacity_m(lane) + EPS for lane in vessel.lanes):
            return "doesn't fit any lane"
        space = self._space_slots(b)
        if not space:
            return "no lane has enough space left"
        if b.is_reefer and self.plugs_used >= vessel.reefer_plugs:
            return "no reefer plug available"
        if self.weight_t + b.weight_t > vessel.max_dwt_t + EPS:
            return "would exceed max deadweight"
        oks = [self._slot_ok(b, s) for s in space]
        if any(fits and dwt_ok for fits, dwt_ok in oks):
            return None
        if any(fits for fits, _ in oks):
            return "would exceed max deadweight once ballast is added"
        return "would unbalance the ship beyond what ballast can correct"

    def place(self, b: Booking, slot: Slot | None = None) -> Slot:
        if slot is None:
            slot = self.best_slot(b)
            if slot is None:
                raise ValueError(f"{b.id}: {self.why_not(b) or 'cannot be placed'}")
        elif slot not in self.feasible_slots(b):
            raise ValueError(f"{b.id}: cannot be placed in {slot}")
        lane = self.vessel.lane(slot.lane_id)
        self.remaining_m[slot] -= b.effective_length(self.vessel.lashing_gap_m)
        self.weight_t += b.weight_t
        self.plugs_used += int(b.is_reefer)
        self._m_t += b.weight_t * lane.y_m
        self._m_l += b.weight_t * lane.zone_x_m(slot.zone)
        self.loads[b.id] = (b, slot)
        return slot

    def remove(self, booking_id: str) -> tuple[Booking, Slot]:
        """Take a unit off the deck, giving back its space, weight, plug and moments."""
        b, slot = self.loads.pop(booking_id)
        lane = self.vessel.lane(slot.lane_id)
        self.remaining_m[slot] += b.effective_length(self.vessel.lashing_gap_m)
        self.weight_t -= b.weight_t
        self.plugs_used -= int(b.is_reefer)
        self._m_t -= b.weight_t * lane.y_m
        self._m_l -= b.weight_t * lane.zone_x_m(slot.zone)
        return b, slot


def check_plan(scenario: Scenario, plan: Plan) -> list[str]:
    """Return every physical-constraint violation in `plan` (empty list = feasible)."""
    vessel = scenario.vessel
    stab = vessel.stability
    known = {b.id: b for b in scenario.bookings}
    lanes = {lane.id: lane for lane in vessel.lanes}
    problems: list[str] = []

    used: dict[Slot, float] = {}
    loads: list[tuple[Booking, Slot]] = []
    weight = 0.0
    plugs = 0
    for booking_id, slot in plan.placements.items():
        if booking_id not in known:
            problems.append(f"unknown booking {booking_id}")
            continue
        if slot.lane_id not in lanes or not (0 <= slot.zone < ZONES):
            problems.append(f"{booking_id} placed in unknown slot {slot}")
            continue
        b = known[booking_id]
        used[slot] = used.get(slot, 0.0) + b.effective_length(vessel.lashing_gap_m)
        loads.append((b, slot))
        weight += b.weight_t
        plugs += int(b.is_reefer)
        if booking_id in plan.rejected:
            problems.append(f"{booking_id} is both placed and rejected")

    for slot, total in used.items():
        cap = vessel.zone_capacity_m(lanes[slot.lane_id])
        if total > cap + EPS:
            problems.append(f"zone {slot} overfilled: {total:.1f} m > {cap:.1f} m")
    if plugs > vessel.reefer_plugs:
        problems.append(f"reefer plugs exceeded: {plugs} > {vessel.reefer_plugs}")

    m_t, m_l = moments(loads, vessel)
    ballast = required_ballast(m_t, m_l, stab)
    if weight + ballast.total_t > vessel.max_dwt_t + EPS:
        problems.append(
            f"max deadweight exceeded: {weight:.1f} t cargo + {ballast.total_t:.1f} t ballast "
            f"> {vessel.max_dwt_t:.1f} t"
        )
    if not ballast_fits(ballast, stab):
        worst = max(ballast.port_t, ballast.stbd_t, ballast.fore_t, ballast.aft_t)
        problems.append(f"ballast tank capacity exceeded: {worst:.1f} t > {stab.tank_cap_t:.1f} t")
        cap = stab.tank_cap_t
        capped = Ballast(
            min(ballast.port_t, cap), min(ballast.stbd_t, cap), min(ballast.fore_t, cap), min(ballast.aft_t, cap)
        )
        heel = residual_heel_deg(m_t, capped, stab)
        trim = residual_trim_m(m_l, capped, stab)
        if abs(heel) > stab.max_heel_deg + 1e-6:
            problems.append(f"heel {abs(heel):.2f} deg exceeds limit {stab.max_heel_deg:.2f} deg")
        if abs(trim) > stab.max_trim_m + 1e-6:
            problems.append(f"trim {abs(trim):.2f} m exceeds limit {stab.max_trim_m:.2f} m")
    return problems
