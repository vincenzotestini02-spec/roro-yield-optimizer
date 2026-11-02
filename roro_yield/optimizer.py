"""MILP booking acceptance with lane assignment (perfect-foresight benchmark).

The formulation is a simplified one-deck version of the lane-based RoRo stowage
model of Øvstebø, Hvattum & Fagerholt (2011), "Optimization of stowage plans for
RoRo ships", as extended and benchmarked by Thomsen, Levinsen, Pacino & Reinhardt
(DTU / DFDS, 2026), "RoRo stowage planning: a systematic study of mathematical
formulations". Differences: one deck, 1-D lanes (length only), no stability or
ballast; their pseudo-revenue objective is replaced by real commercial margin, and
their remark that optional vs. required cargo "could easily be introduced" is
realised as a soft Key Account floor with a per-metre shortfall penalty.

    max  Σ_i margin_i · Σ_l y[i,l]  −  penalty · s
    s.t. Σ_l y[i,l] ≤ 1                                  ∀ i
         Σ_i eff_len_i · y[i,l] ≤ len_l                   ∀ l
         Σ_i weight_i · Σ_l y[i,l] ≤ max_dwt
         Σ_{i reefer} Σ_l y[i,l] ≤ plugs
         s ≥ floor − Σ_{i contract} length_i · Σ_l y[i,l],   s ≥ 0
"""

from __future__ import annotations

import pulp

from .fcfs import solve_fcfs
from .kpis import objective
from .models import Plan, Scenario

OPTIMAL_LABEL = "Best possible (perfect foresight)"


def solve_optimal(scenario: Scenario, time_limit_s: float = 3) -> Plan:
    vessel = scenario.vessel
    gap = vessel.lashing_gap_m
    prob = pulp.LpProblem("roro_yield", pulp.LpMaximize)

    y = {
        (b.id, lane.id): prob.add_variable(f"y_{b.id}_{lane.id}", cat="Binary")
        for b in scenario.bookings
        for lane in vessel.lanes
        if b.effective_length(gap) <= lane.length_m + 1e-9
    }
    lanes_of = {b.id: [y[b.id, l.id] for l in vessel.lanes if (b.id, l.id) in y] for b in scenario.bookings}
    taken = {b.id: pulp.lpSum(lanes_of[b.id]) for b in scenario.bookings}
    shortfall = prob.add_variable("shortfall", lowBound=0)

    prob += (
        pulp.lpSum(b.margin * taken[b.id] for b in scenario.bookings)
        - scenario.shortfall_penalty_per_m * shortfall
    )
    for b in scenario.bookings:
        if len(lanes_of[b.id]) > 1:
            prob += taken[b.id] <= 1
    for lane in vessel.lanes:
        in_lane = [b.effective_length(gap) * y[b.id, lane.id] for b in scenario.bookings if (b.id, lane.id) in y]
        if in_lane:
            prob += pulp.lpSum(in_lane) <= lane.length_m
    prob += pulp.lpSum(b.weight_t * taken[b.id] for b in scenario.bookings) <= vessel.max_dwt_t
    prob += pulp.lpSum(taken[b.id] for b in scenario.bookings if b.is_reefer) <= vessel.reefer_plugs
    prob += shortfall >= scenario.contract_floor_m - pulp.lpSum(
        b.length_m * taken[b.id] for b in scenario.bookings if b.segment == "contract"
    )

    # HiGHS reaches ~1% of the proven optimum within 2-3 s on the default instance;
    # identical lanes make closing the last 1% slow, so we stop at the time limit.
    prob.solve(pulp.HiGHS(msg=False, timeLimit=time_limit_s, gapRel=0.005))

    placements: dict[str, str] = {}
    for b in sorted(scenario.bookings, key=lambda b: b.arrival):
        for lane in vessel.lanes:
            var = y.get((b.id, lane.id))
            if var is not None and (var.value() or 0) > 0.5:
                placements[b.id] = lane.id
                break
    plan = Plan(OPTIMAL_LABEL, placements, [b.id for b in scenario.bookings if b.id not in placements])

    # Guard: if the time limit stopped CBC early, never present a benchmark worse than FCFS.
    fallback = solve_fcfs(scenario)
    if objective(scenario, fallback) > objective(scenario, plan):
        return Plan(OPTIMAL_LABEL, fallback.placements, fallback.rejected)
    return plan
