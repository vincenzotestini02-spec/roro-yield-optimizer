"""Domain models: unit types, bookings, vessel, scenario and plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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

    @property
    def revenue(self) -> float:
        return self.length_m * self.rate_per_m + (self.reefer_fee if self.is_reefer else 0.0)

    @property
    def margin(self) -> float:
        return self.revenue - self.handling_cost

    def effective_length(self, gap_m: float) -> float:
        """Deck length used, including the lashing gap behind the unit."""
        return self.length_m + gap_m


@dataclass(frozen=True)
class Lane:
    id: str
    length_m: float


@dataclass(frozen=True)
class Vessel:
    name: str
    route: str
    lanes: tuple[Lane, ...]
    max_dwt_t: float
    reefer_plugs: int
    lashing_gap_m: float

    @property
    def total_lane_m(self) -> float:
        return sum(lane.length_m for lane in self.lanes)


@dataclass(frozen=True)
class Scenario:
    vessel: Vessel
    bookings: tuple[Booking, ...]
    contract_floor_m: float
    shortfall_penalty_per_m: float

    def booking(self, booking_id: str) -> Booking:
        for b in self.bookings:
            if b.id == booking_id:
                return b
        raise KeyError(booking_id)


@dataclass
class Plan:
    """Outcome of one acceptance method. `placements` maps booking id -> lane id,
    in loading order within each lane."""

    method: str
    placements: dict[str, str] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)

    @property
    def accepted_ids(self) -> list[str]:
        return list(self.placements)
