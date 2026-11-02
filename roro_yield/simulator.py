"""Synthetic but realistic booking demand for one Ro-Ro sailing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import UNIT_TYPES, Booking, Lane, Scenario, Vessel

KEY_ACCOUNTS = ("Nordfreight", "Baltic Logistics", "Humber Forwarding", "Jutland Cargo")
TYPE_MIX = {
    "semi_trailer": 0.50,
    "accompanied_truck": 0.20,
    "mafi": 0.10,
    "van": 0.12,
    "car_batch": 0.08,
}
REEFER_PROB = 0.30
CONTRACT_RATE = (45.0, 60.0)
SPOT_RATE = (75.0, 110.0)
SPOT_LATENESS_PREMIUM = 0.15
REEFER_FEE = {"contract": 80.0, "spot": 150.0}
HANDLING_PER_UNIT = 80.0
HANDLING_PER_TONNE = 1.5
CONTRACT_ARRIVAL = (0.0, 0.7)
SPOT_ARRIVAL = (0.2, 1.0)


@dataclass(frozen=True)
class ScenarioParams:
    n_requests: int = 60
    contract_share: float = 0.45
    n_lanes: int = 6
    lane_length_m: float = 120.0
    max_dwt_t: float = 1100.0
    reefer_plugs: int = 12
    lashing_gap_m: float = 0.5
    contract_floor_share: float = 0.35
    shortfall_penalty_per_m: float = 200.0
    spot_rate_multiplier: float = 1.0
    seed: int = 42


def generate_scenario(params: ScenarioParams) -> Scenario:
    rng = np.random.default_rng(params.seed)
    type_names = list(TYPE_MIX)
    type_probs = list(TYPE_MIX.values())

    drafts = []
    for _ in range(params.n_requests):
        segment = "contract" if rng.random() < params.contract_share else "spot"
        unit = UNIT_TYPES[type_names[rng.choice(len(type_names), p=type_probs)]]
        weight = round(float(rng.uniform(*unit.weight_range_t)), 1)
        is_reefer = unit.can_be_reefer and rng.random() < REEFER_PROB
        lo, hi = CONTRACT_ARRIVAL if segment == "contract" else SPOT_ARRIVAL
        arrival_frac = float(rng.uniform(lo, hi))
        if segment == "contract":
            rate = round(float(rng.uniform(*CONTRACT_RATE)), 2)
            customer = KEY_ACCOUNTS[int(rng.integers(len(KEY_ACCOUNTS)))]
        else:
            # Late spot requests pay a premium; the multiplier is the Lab's price/demand knob.
            base = round(float(rng.uniform(*SPOT_RATE)) * (1 + SPOT_LATENESS_PREMIUM * arrival_frac), 2)
            rate = base * params.spot_rate_multiplier
            customer = None
        drafts.append((arrival_frac, segment, customer, unit, weight, is_reefer, rate))

    drafts.sort(key=lambda d: d[0])
    bookings = []
    spot_count = 0
    for i, (_, segment, customer, unit, weight, is_reefer, rate) in enumerate(drafts):
        if customer is None:
            spot_count += 1
            customer = f"Spot haulier #{spot_count}"
        bookings.append(
            Booking(
                id=f"B{i + 1:03d}",
                arrival=i,
                segment=segment,
                customer=customer,
                unit_type=unit.name,
                length_m=unit.length_m,
                weight_t=weight,
                is_reefer=is_reefer,
                rate_per_m=rate,
                reefer_fee=REEFER_FEE[segment],
                handling_cost=HANDLING_PER_UNIT + HANDLING_PER_TONNE * weight,
            )
        )

    vessel = Vessel(
        name="MV Nordic Bridge",
        route="Esbjerg → Immingham",
        lanes=tuple(Lane(f"L{i}", params.lane_length_m) for i in range(1, params.n_lanes + 1)),
        max_dwt_t=params.max_dwt_t,
        reefer_plugs=params.reefer_plugs,
        lashing_gap_m=params.lashing_gap_m,
    )
    contract_m = sum(b.length_m for b in bookings if b.segment == "contract")
    floor = min(params.contract_floor_share * vessel.total_lane_m, contract_m)
    return Scenario(vessel, tuple(bookings), floor, params.shortfall_penalty_per_m)
