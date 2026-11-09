"""Voyage KPIs shared by every method, so You, FCFS and the optimizer are scored identically."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Plan, Scenario
from .simulator import HANDLING_PER_UNIT
from .stability import Ballast, moments, required_ballast, residual_heel_deg, residual_trim_m

MOVE_COST_EUR = HANDLING_PER_UNIT  # one unit driven off and back on in another zone


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
    ballast_t: float = 0.0
    ballast_cost: float = 0.0
    heel_deg: float = 0.0
    trim_m: float = 0.0
    moves: int = 0
    move_cost: float = 0.0


def plan_ballast(scenario: Scenario, plan: Plan) -> tuple[Ballast, tuple[float, float]]:
    """Closed-form minimum ballast for a plan, and its (M_T, M_L) moments."""
    loads = [(scenario.booking(i), slot) for i, slot in plan.placements.items()]
    m = moments(loads, scenario.vessel)
    return required_ballast(*m, scenario.vessel.stability), m


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
    stab = vessel.stability
    ballast, (m_t, m_l) = plan_ballast(scenario, plan)
    ballast_cost = stab.ballast_cost_per_t * ballast.total_t
    return Kpis(
        method=plan.method,
        n_accepted=len(accepted),
        revenue=revenue,
        margin=margin,
        shortfall_m=shortfall,
        penalty=penalty,
        objective=margin - penalty - ballast_cost - MOVE_COST_EUR * plan.moves,
        revpal=revenue / total_m if total_m > 0 else 0.0,
        deck_util_pct=used_m / total_m * 100 if total_m > 0 else 0.0,
        dwt_pct=(weight + ballast.total_t) / vessel.max_dwt_t * 100 if vessel.max_dwt_t > 0 else 0.0,
        plugs_used=sum(b.is_reefer for b in accepted),
        contract_m=contract_m,
        ballast_t=ballast.total_t,
        ballast_cost=ballast_cost,
        heel_deg=residual_heel_deg(m_t, ballast, stab),
        trim_m=residual_trim_m(m_l, ballast, stab),
        moves=plan.moves,
        move_cost=MOVE_COST_EUR * plan.moves,
    )


def objective(scenario: Scenario, plan: Plan) -> float:
    """Margin minus shortfall penalty minus ballast cost: the number every method competes on."""
    return evaluate(scenario, plan).objective


def yield_delta_pct(value: float, baseline: float) -> float | None:
    """Percentage gain over a baseline; None when the baseline is not positive."""
    if baseline <= 0:
        return None
    return (value - baseline) / baseline * 100
