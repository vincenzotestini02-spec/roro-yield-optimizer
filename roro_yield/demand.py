"""Planner demand assumptions: how many requests a sailing gets, and how many are still to come."""

from __future__ import annotations

from .simulator import CONTRACT_ARRIVAL, SPOT_ARRIVAL

# Demand as a share of the usable deck, as on the Demand levels page.
DEMAND_LEVELS = {"low": 0.75, "normal": 1.08, "high": 1.30}
# Mean deck length of one request in the simulator's unit mix, lashing gap included.
MEAN_REQUEST_M = 13.0


def _uniform_cdf(x: float, low: float, high: float) -> float:
    return min(max((x - low) / (high - low), 0.0), 1.0)


def arrived_share(frac: float, contract_share: float) -> float:
    """Expected share of a sailing's requests that have arrived by `frac` of the booking window."""
    return (contract_share * _uniform_cdf(frac, *CONTRACT_ARRIVAL)
            + (1 - contract_share) * _uniform_cdf(frac, *SPOT_ARRIVAL))


def expected_remaining(n_total: int, frac: float, contract_share: float) -> int:
    return round(n_total * (1 - arrived_share(frac, contract_share)))


def requests_for_level(level: str, usable_m: float) -> int:
    return round(DEMAND_LEVELS[level] * usable_m / MEAN_REQUEST_M)
