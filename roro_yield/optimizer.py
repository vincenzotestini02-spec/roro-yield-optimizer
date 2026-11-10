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

from dataclasses import dataclass
from typing import Sequence

import pulp

from .deck import DeckState, check_plan
from .fcfs import solve_fcfs
from .kpis import objective, plan_ballast
from .models import ZONES, Booking, Lane, Plan, Scenario, Slot, Vessel, customer_key

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


@dataclass
class StowageModel:
    """A built §5.2 model. `forced` is the fixed-slot variable of a forced booking, if any."""

    prob: pulp.LpProblem
    y: dict[tuple[str, str, int], pulp.LpVariable]
    shortfall: pulp.LpVariable
    ballast: dict[str, pulp.LpVariable]
    forced: pulp.LpVariable | None = None


def build_model(
    vessel: Vessel,
    bookings: Sequence[Booking],
    floor_m: float,
    penalty_per_m: float,
    *,
    relaxed: bool = False,
    deck: DeckState | None = None,
    forced: tuple[Booking, Slot] | None = None,
) -> StowageModel:
    """Build the §5.2 model over `bookings`, in time linear in the number of variables.

    relaxed: continuous y in [0, 1] (LP relaxation) instead of binaries.
    deck:    units already loaded are constants: remaining zone lengths, weight, plugs,
             moments and contract metres. Slots a booking cannot fit any more get no variable.
    forced:  one more booking with a single variable `forced` at the given slot; the caller
             fixes its bounds (1 = loaded there, 0 = rejected).
    The objective omits the (constant) margin of units already on the deck.
    """
    stab = vessel.stability
    gap = vessel.lashing_gap_m
    cat = "Continuous" if relaxed else "Binary"
    remaining = deck.remaining_m if deck is not None else {
        Slot(lane.id, z): vessel.zone_capacity_m(lane) for lane in vessel.lanes for z in range(ZONES)
    }
    base_weight = deck.weight_t if deck is not None else 0.0
    base_plugs = deck.plugs_used if deck is not None else 0
    base_mt, base_ml = deck.moments if deck is not None else (0.0, 0.0)
    base_contract = (
        sum(b.length_m for b, _ in deck.loads.values() if b.segment == "contract") if deck is not None else 0.0
    )

    prob = pulp.LpProblem("roro_yield", pulp.LpMaximize)
    y: dict[tuple[str, str, int], pulp.LpVariable] = {}
    obj, dwt, plugs, contract, m_t, m_l = [], [], [], [], [], []
    in_slot: dict[Slot, list] = {}

    def add_terms(b: Booking, var: pulp.LpVariable, slot: Slot, lane: Lane) -> None:
        obj.append((var, b.margin))
        dwt.append((var, b.weight_t))
        if b.is_reefer:
            plugs.append((var, 1.0))
        if b.segment == "contract":
            contract.append((var, b.length_m))
        m_t.append((var, b.weight_t * lane.y_m))
        m_l.append((var, b.weight_t * lane.zone_x_m(slot.zone)))
        in_slot.setdefault(slot, []).append((var, b.effective_length(gap)))

    one_each = []
    for b in bookings:
        length = b.effective_length(gap)
        mine = []
        for lane in vessel.lanes:
            if length > vessel.zone_capacity_m(lane) + 1e-9:
                continue
            for z in range(ZONES):
                slot = Slot(lane.id, z)
                if length > remaining[slot] + 1e-9:
                    continue
                var = prob.add_variable(f"y_{b.id}_{lane.id}_{z}", lowBound=0, upBound=1, cat=cat)
                y[b.id, lane.id, z] = var
                mine.append(var)
                add_terms(b, var, slot, lane)
        if len(mine) > 1:
            one_each.append(mine)

    forced_var = None
    if forced is not None:
        fb, fslot = forced
        forced_var = prob.add_variable("forced", lowBound=0, upBound=1)
        add_terms(fb, forced_var, fslot, vessel.lane(fslot.lane_id))

    shortfall = prob.add_variable("shortfall", lowBound=0)
    bal = {k: prob.add_variable(f"ballast_{k}", lowBound=0, upBound=stab.tank_cap_t)
           for k in ("port", "stbd", "fore", "aft")}
    bal_terms = [(v, 1.0) for v in bal.values()]

    prob += pulp.LpAffineExpression(
        obj + [(shortfall, -penalty_per_m)] + [(v, -stab.ballast_cost_per_t) for v in bal.values()]
    )
    for mine in one_each:
        prob += pulp.LpAffineExpression([(v, 1.0) for v in mine]) <= 1
    for slot, terms in in_slot.items():
        prob += pulp.LpAffineExpression(terms) <= remaining[slot]
    prob += pulp.LpAffineExpression(dwt + bal_terms) <= vessel.max_dwt_t - base_weight
    if plugs:
        prob += pulp.LpAffineExpression(plugs) <= vessel.reefer_plugs - base_plugs
    prob += pulp.LpAffineExpression(contract + [(shortfall, 1.0)]) >= floor_m - base_contract

    a_t, a_l = stab.side_tank_arm_m, stab.end_tank_arm_m
    heel = pulp.LpAffineExpression(m_t + [(bal["port"], -a_t), (bal["stbd"], a_t)])
    trim = pulp.LpAffineExpression(m_l + [(bal["fore"], a_l), (bal["aft"], -a_l)])
    prob += heel <= stab.heel_limit_tm - base_mt
    prob += heel >= -stab.heel_limit_tm - base_mt
    prob += trim <= stab.trim_limit_tm - base_ml
    prob += trim >= -stab.trim_limit_tm - base_ml

    if deck is not None and deck.reservations:
        # Loaded metres + reserved metres not used yet <= usable deck (see DeckState._reservations_allow).
        by_id = {b.id: b for b in bookings}
        total, by_customer = [], {}
        loads = [(by_id[bid], var) for (bid, _, _), var in y.items()]
        if forced is not None:
            loads.append((forced[0], forced_var))
        for b, var in loads:
            length = b.effective_length(gap)
            total.append((var, length))
            by_customer.setdefault(customer_key(b.customer), []).append((var, length))
        unused = []
        for i, (key, quota) in enumerate(deck._quota.items()):
            u = prob.add_variable(f"unused_reserved_{i}", lowBound=0)
            prob += pulp.LpAffineExpression(by_customer.get(key, []) + [(u, 1.0)]) >= quota - deck.used_by_customer.get(key, 0.0)
            unused.append((u, 1.0))
        prob += pulp.LpAffineExpression(total + unused) <= deck.capacity_m - deck.used_m
    return StowageModel(prob, y, shortfall, bal, forced_var)


def _greedy_on(deck: DeckState, scenario: Scenario) -> Plan:
    """FCFS on top of a deck whose units stay put: the starting plan when some units are fixed."""
    trial = deck.copy()
    rejected = []
    for b in sorted(scenario.bookings, key=lambda b: b.arrival):
        if trial.why_not(b) is None:
            trial.place(b)
        else:
            rejected.append(b.id)
    fixed = set(deck.loads)
    return Plan("Greedy", {k: v for k, v in trial.placements.items() if k not in fixed}, rejected)


def solve_optimal(scenario: Scenario, time_limit_s: float = 3, candidates: Sequence[Plan] = (),
                  deck: DeckState | None = None, keep: dict[str, Slot] | None = None,
                  keep_bonus: float = 0.0) -> Plan:
    """Best plan by the common objective. With `deck`, its units are fixed and part of the result.

    With `keep` (deck mode only), each booking placed at its slot in `keep` earns `keep_bonus` in the
    model, so among equally good plans the one that moves fewest units wins.
    """
    if deck is not None:
        return _solve_on_deck(scenario, time_limit_s, candidates, deck, keep or {}, keep_bonus)
    vessel = scenario.vessel

    seeds = [solve_fcfs(scenario), *candidates]
    incumbent = _best_of(scenario, seeds)

    model = build_model(vessel, scenario.bookings, scenario.contract_floor_m, scenario.shortfall_penalty_per_m)
    prob, y = model.prob, model.y
    by_id = {b.id: b for b in scenario.bookings}

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


def _fits_on(deck: DeckState, plan: Plan, free: dict[str, Booking]) -> bool:
    """Whether the plan's free units all fit on `deck` (reservations included), in any order that works."""
    trial = deck.copy()
    pending = [(free[bid], slot) for bid, slot in plan.placements.items() if bid in free]
    while pending:
        left = [(b, slot) for b, slot in pending
                if not (slot in trial.remaining_m and slot in trial.feasible_slots(b) and trial.place(b, slot))]
        if len(left) == len(pending):
            return False
        pending = left
    return True


def _solve_on_deck(scenario: Scenario, time_limit_s: float, candidates: Sequence[Plan], deck: DeckState,
                   keep: dict[str, Slot], keep_bonus: float) -> Plan:
    fixed = dict(deck.placements)
    full = Scenario(scenario.vessel, tuple(b for b, _ in deck.loads.values()) + tuple(scenario.bookings),
                    scenario.contract_commitment_m, scenario.shortfall_penalty_per_m)
    free_ids = {b.id for b in scenario.bookings}

    def with_fixed(placements: dict[str, Slot]) -> Plan:
        merged = {**fixed, **{k: v for k, v in placements.items() if k in free_ids}}
        return Plan(OPTIMAL_LABEL, merged, [b.id for b in full.bookings if b.id not in merged])

    seeds = [with_fixed(_greedy_on(deck, scenario).placements), *(with_fixed(c.placements) for c in candidates)]
    free = {b.id: b for b in scenario.bookings}
    if deck.reservations:
        # A candidate (the previous plan, say) may predate the reservations: keep only plans that respect them.
        seeds = [seeds[0], *(s for s in seeds[1:] if _fits_on(deck, s, free))]
    incumbent = _best_of(full, seeds)

    model = build_model(scenario.vessel, scenario.bookings, scenario.contract_floor_m,
                        scenario.shortfall_penalty_per_m, deck=deck)
    prob, y = model.prob, model.y
    stay = [(y[(bid, slot.lane_id, slot.zone)], keep_bonus) for bid, slot in keep.items()
            if (bid, slot.lane_id, slot.zone) in y]
    if stay and keep_bonus > 0:
        prob.setObjective(prob.objective + pulp.LpAffineExpression(stay))
    start = {v.name: 0.0 for v in prob.variables()}
    for bid, slot in incumbent.placements.items():
        name = f"y_{bid}_{slot.lane_id}_{slot.zone}"
        if bid in free_ids and name in start:
            start[name] = 1.0
    prob.solve(_WarmHiGHS(msg=False, timeLimit=time_limit_s, gapRel=0.005, start=start))
    placements = {bid: Slot(lane_id, z) for (bid, lane_id, z), var in y.items() if (var.value() or 0) > 0.5}
    milp = with_fixed(placements)
    if deck.reservations and not _fits_on(deck, milp, free):
        milp = seeds[0]  # no feasible MILP answer (reservations beyond the free deck): keep the greedy plan
    best = _best_of(full, [milp, *seeds])
    return _sorted_plan(full, best.placements)
