"""Domain models: unit types, bookings, vessel, scenario and plan."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

Segment = Literal["contract", "spot"]


@dataclass(frozen=True)
class UnitType:
    name: str
    length_m: float
    weight_range_t: tuple[float, float]
    can_be_reefer: bool


UNIT_TYPES: dict[str, UnitType] = {
    "semi_trailer": UnitType("semi_trailer", 13.6, (10.0, 30.0), True),
    "accompanied_truck": UnitType("accompanied_truck", 16.5, (20.0, 40.0), True),
    "mafi": UnitType("mafi", 12.2, (25.0, 60.0), False),
    "van": UnitType("van", 6.5, (2.0, 3.5), False),
    "car_batch": UnitType("car_batch", 4.8, (1.2, 2.0), False),
}


@dataclass(frozen=True)
class Booking:
    id: str
    arrival: int
    segment: Segment
    customer: str
    unit_type: str
    length_m: float
    weight_t: float
    is_reefer: bool
    rate_per_m: float
    reefer_fee: float
    handling_cost: float
    arrival_frac: float = 0.0

    @property
    def revenue(self) -> float:
        return self.length_m * self.rate_per_m + (self.reefer_fee if self.is_reefer else 0.0)

    @property
    def margin(self) -> float:
        return self.revenue - self.handling_cost

    def effective_length(self, gap_m: float) -> float:
        """Deck length used, including the lashing gap behind the unit."""
        return self.length_m + gap_m


ZONES = 4
LANE_WIDTH_M = 3.2


class Slot(NamedTuple):
    """One of the ZONES length-wise sections of a lane (zone 0 = stern, ZONES-1 = bow)."""

    lane_id: str
    zone: int

    def __str__(self) -> str:
        return f"{self.lane_id}-Z{self.zone}"


@dataclass(frozen=True)
class Lane:
    id: str
    length_m: float
    y_m: float = 0.0  # transverse offset from the centreline, port negative

    @property
    def zone_length_m(self) -> float:
        return self.length_m / ZONES

    def zone_x_m(self, zone: int) -> float:
        """Longitudinal centre of a zone from midships (aft negative)."""
        return -self.length_m / 2 + (zone + 0.5) * self.zone_length_m


@dataclass(frozen=True)
class Stability:
    displacement_t: float
    gm_m: float
    mtc_tm_per_cm: float
    max_heel_deg: float
    max_trim_m: float
    side_tank_arm_m: float
    end_tank_arm_m: float
    tank_cap_t: float
    ballast_cost_per_t: float

    @property
    def heel_limit_tm(self) -> float:
        return self.displacement_t * self.gm_m * math.tan(math.radians(self.max_heel_deg))

    @property
    def trim_limit_tm(self) -> float:
        return self.mtc_tm_per_cm * 100 * self.max_trim_m


DEFAULT_STABILITY = Stability(
    displacement_t=8000.0,
    gm_m=1.5,
    mtc_tm_per_cm=100.0,
    max_heel_deg=2.0,
    max_trim_m=0.5,
    side_tank_arm_m=9.0,
    end_tank_arm_m=48.0,
    tank_cap_t=300.0,
    ballast_cost_per_t=5.0,
)


@dataclass(frozen=True)
class Vessel:
    name: str
    route: str
    lanes: tuple[Lane, ...]
    max_dwt_t: float
    reefer_plugs: int
    lashing_gap_m: float
    stability: Stability = DEFAULT_STABILITY
    broken_stowage_pct: float = 0.0  # share of each zone lost to pillars, ramps and lashing points

    def zone_capacity_m(self, lane: Lane) -> float:
        """Usable length of one zone of `lane` after broken stowage."""
        return lane.zone_length_m * (1.0 - self.broken_stowage_pct)

    @property
    def total_lane_m(self) -> float:
        return sum(lane.length_m for lane in self.lanes)

    def lane(self, lane_id: str) -> Lane:
        for lane in self.lanes:
            if lane.id == lane_id:
                return lane
        raise KeyError(lane_id)

    @property
    def slots(self) -> tuple[Slot, ...]:
        return tuple(Slot(lane.id, z) for lane in self.lanes for z in range(ZONES))


@dataclass(frozen=True)
class Scenario:
    vessel: Vessel
    bookings: tuple[Booking, ...]
    contract_commitment_m: float
    shortfall_penalty_per_m: float

    @property
    def contract_floor_m(self) -> float:
        """Realised floor used for scoring: the commitment, capped by contract metres requested."""
        contract_m = sum(b.length_m for b in self.bookings if b.segment == "contract")
        return min(self.contract_commitment_m, contract_m)

    def booking(self, booking_id: str) -> Booking:
        for b in self.bookings:
            if b.id == booking_id:
                return b
        raise KeyError(booking_id)


@dataclass
class Plan:
    """Outcome of one acceptance method. `placements` maps booking id -> Slot,
    in loading order within each lane."""

    method: str
    placements: dict[str, Slot] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)
    moves: int = 0  # units moved after loading; each costs MOVE_COST_EUR in the objective

    @property
    def accepted_ids(self) -> list[str]:
        return list(self.placements)


UNIT_LABELS: dict[str, str] = {
    "semi_trailer": "semi-trailer",
    "accompanied_truck": "accompanied truck",
    "mafi": "mafi roll-trailer",
    "van": "van",
    "car_batch": "car batch",
}
