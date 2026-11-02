"""Voyage KPIs shared by every method, so You, FCFS and the optimizer are scored identically."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Plan, Scenario


@dataclass(frozen=True)
class Kpis:
    method: str
    n_accepted: int
    revenue: float
    margin: float
    shortfall_m: float
    penalty: float
    objective: float
    revpal: float
    deck_util_pct: float
    dwt_pct: float
    plugs_used: int
    contract_m: float


def evaluate(scenario: Scenario, plan: Plan) -> Kpis:
    vessel = scenario.vessel
    accepted = [scenario.booking(i) for i in plan.placements]
    revenue = sum(b.revenue for b in accepted)
    margin = sum(b.margin for b in accepted)
    contract_m = sum(b.length_m for b in accepted if b.segment == "contract")
    shortfall = max(0.0, scenario.contract_floor_m - contract_m)
    penalty = scenario.shortfall_penalty_per_m * shortfall
    total_m = vessel.total_lane_m
    used_m = sum(b.effective_length(vessel.lashing_gap_m) for b in accepted)
    weight = sum(b.weight_t for b in accepted)
    return Kpis(
        method=plan.method,
        n_accepted=len(accepted),
        revenue=revenue,
        margin=margin,
        shortfall_m=shortfall,
        penalty=penalty,
        objective=margin - penalty,
        revpal=revenue / total_m if total_m > 0 else 0.0,
        deck_util_pct=used_m / total_m * 100 if total_m > 0 else 0.0,
        dwt_pct=weight / vessel.max_dwt_t * 100 if vessel.max_dwt_t > 0 else 0.0,
        plugs_used=sum(b.is_reefer for b in accepted),
        contract_m=contract_m,
    )


def objective(scenario: Scenario, plan: Plan) -> float:
    """Margin minus contract-shortfall penalty: the number every method competes on."""
    return evaluate(scenario, plan).objective


def yield_delta_pct(value: float, baseline: float) -> float | None:
    """Percentage gain over a baseline; None when the baseline is not positive."""
    if baseline <= 0:
        return None
    return (value - baseline) / baseline * 100
