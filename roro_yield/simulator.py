"""Synthetic but realistic booking demand for one Ro-Ro sailing."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .models import DEFAULT_STABILITY, LANE_WIDTH_M, UNIT_TYPES, Booking, Lane, Scenario, Vessel

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
    max_heel_deg: float = 2.0
    max_trim_m: float = 0.5
    ballast_tank_cap_t: float = 300.0
    ballast_cost_per_t: float = 5.0
    broken_stowage_pct: float = 0.0
    displacement_t: float = 8000.0
    gm_m: float = 1.5
    mtc_tm_per_cm: float = 100.0
    seed: int = 42


def _draw_request(rng: np.random.Generator, params: ScenarioParams):
    """Draw one request: (arrival_frac, segment, customer, unit, weight, is_reefer, rate)."""
    type_names = list(TYPE_MIX)
    type_probs = list(TYPE_MIX.values())
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
    return (arrival_frac, segment, customer, unit, weight, is_reefer, rate)


def _make_booking(bid, arrival, frac, segment, customer, unit, weight, is_reefer, rate) -> Booking:
    return Booking(
        id=bid,
        arrival=arrival,
        segment=segment,
        customer=customer,
        unit_type=unit.name,
        length_m=unit.length_m,
        weight_t=weight,
        is_reefer=is_reefer,
        rate_per_m=rate,
        reefer_fee=REEFER_FEE[segment],
        handling_cost=HANDLING_PER_UNIT + HANDLING_PER_TONNE * weight,
        arrival_frac=frac,
    )


MAX_SAMPLE_ATTEMPTS = 10_000


def sample_future(
    params: ScenarioParams, after_frac: float, n_remaining: int, rng: np.random.Generator
) -> list[Booking]:
    """Sample plausible future requests arriving after `after_frac` (ids F001...).

    Rejection sampling over the generate_scenario recipe, at most MAX_SAMPLE_ATTEMPTS
    draws in total; if exhausted, returns however many were accepted (possibly fewer
    than n_remaining).
    """
    if n_remaining <= 0 or after_frac >= 1:
        return []
    drafts = []
    attempts = 0
    while len(drafts) < n_remaining and attempts < MAX_SAMPLE_ATTEMPTS:
        attempts += 1
        d = _draw_request(rng, params)
        if d[0] > after_frac:
            drafts.append(d)
    drafts.sort(key=lambda d: d[0])
    out = []
    spot_count = 0
    for i, (frac, segment, customer, unit, weight, is_reefer, rate) in enumerate(drafts):
        if customer is None:
            spot_count += 1
            customer = f"Future spot #{spot_count}"
        out.append(_make_booking(f"F{i + 1:03d}", i, frac, segment, customer, unit, weight, is_reefer, rate))
    return out


def expected_contract_m(
    params: ScenarioParams, after_frac: float, n_remaining: int, n_samples: int = 200, seed: int = 0
) -> float:
    """Mean contract metres among n_remaining sampled future requests."""
    rng = np.random.default_rng(seed)
    totals = [
        sum(b.length_m for b in sample_future(params, after_frac, n_remaining, rng) if b.segment == "contract")
        for _ in range(n_samples)
    ]
    return float(np.mean(totals))


def generate_scenario(params: ScenarioParams) -> Scenario:
    rng = np.random.default_rng(params.seed)
    drafts = [_draw_request(rng, params) for _ in range(params.n_requests)]

    drafts.sort(key=lambda d: d[0])
    bookings = []
    spot_count = 0
    for i, (frac, segment, customer, unit, weight, is_reefer, rate) in enumerate(drafts):
        if customer is None:
            spot_count += 1
            customer = f"Spot haulier #{spot_count}"
        bookings.append(_make_booking(f"B{i + 1:03d}", i, frac, segment, customer, unit, weight, is_reefer, rate))

    vessel = Vessel(
        name="MV Nordic Bridge",
        route="Esbjerg → Immingham",
        lanes=tuple(
            Lane(f"L{i}", params.lane_length_m, (i - 1 - (params.n_lanes - 1) / 2) * LANE_WIDTH_M)
            for i in range(1, params.n_lanes + 1)
        ),
        max_dwt_t=params.max_dwt_t,
        reefer_plugs=params.reefer_plugs,
        lashing_gap_m=params.lashing_gap_m,
        broken_stowage_pct=params.broken_stowage_pct,
        stability=replace(
            DEFAULT_STABILITY,
            displacement_t=params.displacement_t,
            gm_m=params.gm_m,
            mtc_tm_per_cm=params.mtc_tm_per_cm,
            max_heel_deg=params.max_heel_deg,
            max_trim_m=params.max_trim_m,
            tank_cap_t=params.ballast_tank_cap_t,
            ballast_cost_per_t=params.ballast_cost_per_t,
            end_tank_arm_m=0.4 * params.lane_length_m,
        ),
    )
    commitment = params.contract_floor_share * vessel.total_lane_m
    return Scenario(vessel, tuple(bookings), commitment, params.shortfall_penalty_per_m)
