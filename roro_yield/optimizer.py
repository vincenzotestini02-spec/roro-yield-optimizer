"""MILP booking acceptance with zone placement and ballast (perfect-foresight benchmark).

The formulation is a simplified one-deck version of the lane-based RoRo stowage
model of Øvstebø, Hvattum & Fagerholt (2011), "Optimization of stowage plans for
RoRo ships", as extended and benchmarked by Thomsen, Levinsen, Pacino & Reinhardt
(DTU / DFDS, 2026), "RoRo stowage planning: a systematic study of mathematical
formulations". Differences: one deck, lanes split into ZONES length-wise zones,
a linear (simplified) stability model with four ballast tanks; their pseudo-revenue
objective is replaced by real commercial margin, and their remark that optional vs.
required cargo "could easily be introduced" is realised as a soft Key Account floor
with a per-metre shortfall penalty.

    max  Σ_i margin_i · Σ_s y[i,s]  −  penalty · sf  −  ballast_cost · Σ_k b_k
    s.t. Σ_s y[i,s] ≤ 1                                        ∀ i
         Σ_i eff_len_i · y[i,s] ≤ zone_len_s                    ∀ slots s = (lane, zone)
         Σ_i w_i · Σ_s y[i,s] + Σ_k b_k ≤ max_dwt
         Σ_{i reefer} Σ_s y[i,s] ≤ plugs
         sf ≥ floor − Σ_{i contract} length_i · Σ_s y[i,s],   sf ≥ 0
         0 ≤ b_k ≤ tank_cap                                     k ∈ {port, stbd, fore, aft}
         −H ≤ Σ w_i y[i,s]·y_lane(s) − a_T·b_port + a_T·b_stbd ≤ H     (heel)
         −T ≤ Σ w_i y[i,s]·x_zone(s) + a_L·b_fore − a_L·b_aft ≤ T      (trim)

The result is the best, by the common `objective`, of {MILP, FCFS, any supplied
candidates}, so the benchmark is never worse than any method it is compared with,
even when the time limit stops HiGHS early. The MILP is warm-started from that best
plan (a subclass of PuLP's HiGHS interface hands the start to highspy).
"""

from __future__ import annotations

from typing import Sequence

import pulp

from .deck import check_plan
from .fcfs import solve_fcfs
from .kpis import objective, plan_ballast
from .models import ZONES, Plan, Scenario, Slot

OPTIMAL_LABEL = "Best possible (perfect foresight)"


class _WarmHiGHS(pulp.HiGHS):
    """PuLP's HiGHS API solver with an optional starting solution (variable name -> value)."""

    def __init__(self, *args, start: dict[str, float] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._start = start or {}
        self.warm_started = False

    def callSolver(self, lp):
        if self._start:
            try:
                import highspy

                sol = highspy.HighsSolution()
                sol.col_value = [float(self._start.get(v.name, 0.0)) for v in lp.variables()]
                lp.solverModel.setSolution(sol)
                self.warm_started = True
            except Exception:  # warm start is optional; solve cold if it is refused
                self.warm_started = False
        super().callSolver(lp)


def _sorted_plan(scenario: Scenario, placements: dict[str, Slot]) -> Plan:
    order = sorted((b for b in scenario.bookings if b.id in placements), key=lambda b: b.arrival)
    placed = {b.id: placements[b.id] for b in order}
    return Plan(OPTIMAL_LABEL, placed, [b.id for b in scenario.bookings if b.id not in placed])


def _best_of(scenario: Scenario, plans: Sequence[Plan]) -> Plan:
    feasible = [p for p in plans if check_plan(scenario, p) == []]
    pool = feasible or list(plans)
    return max(pool, key=lambda p: objective(scenario, p))


def solve_optimal(scenario: Scenario, time_limit_s: float = 3, candidates: Sequence[Plan] = ()) -> Plan:
    vessel = scenario.vessel
    stab = vessel.stability
    gap = vessel.lashing_gap_m

    seeds = [solve_fcfs(scenario), *candidates]
    incumbent = _best_of(scenario, seeds)

    prob = pulp.LpProblem("roro_yield", pulp.LpMaximize)
    slots = [Slot(lane.id, z) for lane in vessel.lanes for z in range(ZONES)]
    y = {}
    for b in scenario.bookings:
        for lane in vessel.lanes:
            if b.effective_length(gap) > lane.zone_length_m + 1e-9:
                continue
            for z in range(ZONES):
                y[b.id, lane.id, z] = prob.add_variable(f"y_{b.id}_{lane.id}_{z}", cat="Binary")
    slots_of = {b.id: [k for k in y if k[0] == b.id] for b in scenario.bookings}
    taken = {b.id: pulp.lpSum(y[k] for k in slots_of[b.id]) for b in scenario.bookings}
    shortfall = prob.add_variable("shortfall", lowBound=0)
    bal = {k: prob.add_variable(f"ballast_{k}", lowBound=0, upBound=stab.tank_cap_t)
           for k in ("port", "stbd", "fore", "aft")}
    total_ballast = pulp.lpSum(bal.values())

    prob += (
        pulp.lpSum(b.margin * taken[b.id] for b in scenario.bookings)
        - scenario.shortfall_penalty_per_m * shortfall
        - stab.ballast_cost_per_t * total_ballast
    )
    for b in scenario.bookings:
        if len(slots_of[b.id]) > 1:
            prob += taken[b.id] <= 1
    for slot in slots:
        in_slot = [b.effective_length(gap) * y[b.id, slot.lane_id, slot.zone]
                   for b in scenario.bookings if (b.id, slot.lane_id, slot.zone) in y]
        if in_slot:
            prob += pulp.lpSum(in_slot) <= vessel.lane(slot.lane_id).zone_length_m
    prob += pulp.lpSum(b.weight_t * taken[b.id] for b in scenario.bookings) + total_ballast <= vessel.max_dwt_t
    prob += pulp.lpSum(taken[b.id] for b in scenario.bookings if b.is_reefer) <= vessel.reefer_plugs
    prob += shortfall >= scenario.contract_floor_m - pulp.lpSum(
        b.length_m * taken[b.id] for b in scenario.bookings if b.segment == "contract"
    )

    lane_y = {lane.id: lane.y_m for lane in vessel.lanes}
    zone_x = {(lane.id, z): lane.zone_x_m(z) for lane in vessel.lanes for z in range(ZONES)}
    by_id = {b.id: b for b in scenario.bookings}
    m_t = pulp.lpSum(by_id[i].weight_t * lane_y[lane] * var for (i, lane, z), var in y.items())
    m_l = pulp.lpSum(by_id[i].weight_t * zone_x[lane, z] * var for (i, lane, z), var in y.items())
    m_t = m_t - stab.side_tank_arm_m * bal["port"] + stab.side_tank_arm_m * bal["stbd"]
    m_l = m_l + stab.end_tank_arm_m * bal["fore"] - stab.end_tank_arm_m * bal["aft"]
    prob += m_t <= stab.heel_limit_tm
    prob += m_t >= -stab.heel_limit_tm
    prob += m_l <= stab.trim_limit_tm
    prob += m_l >= -stab.trim_limit_tm

    # Warm start from the incumbent (best of FCFS and candidates).
    start = {v.name: 0.0 for v in prob.variables()}
    for bid, slot in incumbent.placements.items():
        name = f"y_{bid}_{slot.lane_id}_{slot.zone}"
        if name in start:
            start[name] = 1.0
    contract_m = sum(by_id[i].length_m for i in incumbent.placements if by_id[i].segment == "contract")
    start["shortfall"] = max(0.0, scenario.contract_floor_m - contract_m)
    ib, _ = plan_ballast(scenario, incumbent)
    for k, v in (("port", ib.port_t), ("stbd", ib.stbd_t), ("fore", ib.fore_t), ("aft", ib.aft_t)):
        start[f"ballast_{k}"] = v

    # HiGHS gets near the proven optimum quickly; stop at the time limit rather than
    # chasing the last fraction of a percent.
    prob.solve(_WarmHiGHS(msg=False, timeLimit=time_limit_s, gapRel=0.005, start=start))

    placements: dict[str, Slot] = {}
    for (bid, lane_id, z), var in y.items():
        if (var.value() or 0) > 0.5:
            placements[bid] = Slot(lane_id, z)
    milp = _sorted_plan(scenario, placements)

    best = _best_of(scenario, [milp, *seeds])
    return _sorted_plan(scenario, best.placements)
