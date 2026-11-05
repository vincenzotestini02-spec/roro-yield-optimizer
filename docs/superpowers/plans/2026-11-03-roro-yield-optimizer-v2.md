# RoRo Yield Optimizer v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second version of the app, on branch `v2` with its own link, that adds deck stability (lane × zone positions, heel, trim, ballast that eats deadweight) and a smart planner that decides without foresight by optimising over sampled futures.

**Architecture:** The engine (`roro_yield/`) gains a stability module, a slot-based deck state that depends on the `Vessel` only (never on future bookings), an extended MILP, and an advisor that receives a `PolicyView` object, which is the structural information boundary. The UI (`app/`) adds a placement toggle, an advisor toggle, stability visuals, a background job runner, and a 4-contender Reveal.

**Tech Stack:** Python 3.11, PuLP + HiGHS (`highspy`), numpy, pandas, plotly, streamlit, pytest. Run tests with `.venv/Scripts/python.exe -m pytest`.

**Spec:** `docs/superpowers/specs/2026-11-03-roro-yield-optimizer-v2-design.md` (builds on `docs/superpowers/specs/2026-11-02-roro-yield-optimizer-design.md`)

## Global Constraints

- All work on branch `v2`; `main` is tagged `v1.0` and never receives v2 commits. Push `v2` to `origin`. Do not create Streamlit apps: the owner does that.
- Scope-cut order if time runs short before 2026-11-08: (1) Lab smart planner, (2) Reveal advisor table, (3) manual placement. Stability and the in-game advisor are never cut.
- `roro_yield/` never imports `streamlit`.
- UI labels, exact: **"You"**, **"First come, first served"**, **"Smart planner (no foresight)"**, **"Best possible (perfect foresight)"**, toggles **"🤖 App places them"** / **"✋ I place them"**, **"💡 Advisor"**.
- 4 zones per lane, zone 0 = stern (ramp) … zone 3 = bow. Lab lane-length slider minimum is **70 m**.
- Score for every method = margin − shortfall_penalty × shortfall_m − ballast_cost_per_t × ballast_t. Ballast for any plan = closed-form minimum (Task 1).
- Feasible = per-zone length, cargo + ballast ≤ max DWT, reefers ≤ plugs, heel/trim within limits after ballast, ballast within tank capacity.
- Contract: public commitment `C = contract_floor_share × total lane-m`; realised floor `min(C, contract metres requested)` is used only for scoring.
- Advisor information set: current request, the history of past requests, its own deck state, "request k of n", `ScenarioParams`. Never the scenario's remaining bookings.
- Advisor defaults: K = 20 futures, rng seeded from `(seed, request index)`, accept iff mean gain > 0 and feasible. Lever floor K = 10. App reads K from env `RORO_ADVISOR_K` (default 20).
- Defaults: max heel 2.0°, max trim 0.5 m, ballast cost €5/t, vessel kept at 6 × 120 m, 1,100 t, 12 plugs, 0.5 m gap.
- Performance budgets: one advisor verdict ≤ 1.5 s target on Streamlit Cloud (≤ 3 s locally in the slow test); optimizer ≤ 3 s time limit; no UI wait > 5 s without a progress indicator.
- README states that the stability model is linear and simplified, not a class-approved loading computer, and that the advisor knows only the demand distribution.

## Review Focus

1. **Lab extremes with stability** (1 lane, tank capacity 0, max heel 0.5°, DWT 10 t, 200 requests on 16 lanes): every method returns a `check_plan`-clean plan and KPIs evaluate. Test: `test_extreme_scenarios_v2` (Task 4).
2. **Last request / late arrival**: `n_remaining = 0` or `after_frac ≥ 1` → `sample_future` returns `[]` and `advise` still returns a verdict. Tests in Task 5 and Task 6.
3. **Advisor on an infeasible request** → `Verdict(accept=False, feasible=False, reason=...)`, no LP is built. Test in Task 6.
4. **Manual mode, player switches toggle or rejects while a zone choice is pending** → pending accept cleared, nothing placed twice. Test: `test_pending_accept_cleared` (Task 8).
5. **New game started while an old background job runs** → results are keyed by seed and the old seed's results are never shown. Test: `test_jobs_keyed_by_seed` (Task 10).

---

### Task 1: Branch, geometry and stability primitives

**Files:**
- Modify: `roro_yield/models.py`, `roro_yield/simulator.py`
- Create: `roro_yield/stability.py`, `tests/test_stability.py`
- Modify: `tests/test_models.py`, `tests/test_simulator.py`

**Interfaces:**
- Produces (models):
  - `ZONES = 4`
  - `class Slot(NamedTuple): lane_id: str; zone: int`, with `__str__` giving `"L3-Z2"`.
  - `Lane(id: str, length_m: float, y_m: float = 0.0)`; `Lane.zone_length_m -> float`; `Lane.zone_x_m(zone: int) -> float`, the longitudinal centre from midships (aft negative) = `-L/2 + (zone + 0.5) * L/4`.
  - `@dataclass(frozen=True) Stability(displacement_t, gm_m, mtc_tm_per_cm, max_heel_deg, max_trim_m, side_tank_arm_m, end_tank_arm_m, tank_cap_t, ballast_cost_per_t)`, with properties `heel_limit_tm = Δ·GM·tan(max_heel)` and `trim_limit_tm = MTC·100·max_trim`.
  - `Vessel` gains a trailing field `stability: Stability = DEFAULT_STABILITY`. `Vessel.lane(lane_id) -> Lane` and `Vessel.slots -> tuple[Slot, ...]`.
  - `Booking` gains a trailing field `arrival_frac: float = 0.0`.
  - `Scenario.__init__(vessel, bookings, contract_commitment_m, shortfall_penalty_per_m)` (third positional field renamed). The property `contract_floor_m = min(commitment, Σ length of contract bookings)`.
  - `Plan.placements: dict[str, Slot]`.
- Produces (stability):
  - `@dataclass(frozen=True) Ballast(port_t, stbd_t, fore_t, aft_t)` with `.total_t`.
  - `moments(loads: Iterable[tuple[Booking, Slot]], vessel) -> tuple[float, float]` returns `(M_T, M_L)` in t·m.
  - `required_ballast(m_t, m_l, stab) -> Ballast`: port ballast if `M_T > H` (starboard-heavy), and so on; `(|M| − limit)/arm`, never negative.
  - `ballast_fits(b: Ballast, stab) -> bool`: each tank ≤ `tank_cap_t`.
  - `residual_heel_deg(m_t, b, stab) -> float` and `residual_trim_m(m_l, b, stab) -> float` give the signed values after ballast; positive = starboard / by the bow.
- Produces (simulator): `ScenarioParams` gains `max_heel_deg=2.0, max_trim_m=0.5, ballast_tank_cap_t=300.0, ballast_cost_per_t=5.0`; lanes get evenly spread `y_m` (odd count → middle lane at 0, single lane at 0; port negative, L1 is the port-most lane); each booking stores its `arrival_frac`.

- [ ] **Step 1: Confirm the branch**

Branch `v2` and tag `v1.0` (at `c837ff5`, the live v1) were created with this plan. Run: `git branch --show-current` → `v2`.

- [ ] **Step 2: Write the failing tests** in `tests/test_stability.py`:
  - `test_zone_centres`: a 120 m lane → `zone_x_m(0) == -45`, `zone_x_m(3) == 45`, `zone_length_m == 30`.
  - `test_lane_offsets_symmetric`: for `n_lanes` in (1, 5, 6), the `y_m` values sum to 0; for 1 lane `y_m == 0`; for 5 lanes the middle one is 0; L1 has the most negative `y_m`.
  - `test_no_ballast_within_limits`: `required_ballast(0.5*H, -0.5*T, stab).total_t == 0`.
  - `test_ballast_closed_form`: `M_T = H + 900`, `side arm 9` → `port_t == 100`, `stbd_t == 0`; `M_L = -(T + 500)`, `end arm 50` → `fore_t == 10`; residual heel equals the limit to within 1e-9 degrees.
  - `test_ballast_fits_cap`: a tank over `tank_cap_t` → False.
  - `test_default_scenario_unchanged_floor`: for seeds 1–10, `generate_scenario(...).contract_floor_m` equals v1's formula `min(0.35*720, contract metres)`.
  - Update `tests/test_models.py` and `tests/test_simulator.py` for `Slot` placements and the new fields.

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stability.py -v` → FAIL (import errors).

- [ ] **Step 4: Implement** the interfaces above. The default physical constants (`DEFAULT_STABILITY`, lane width 3.2 m) live in `roro_yield/models.py` and are calibrated in Task 2.

- [ ] **Step 5: Run** `tests/test_stability.py tests/test_models.py tests/test_simulator.py` → PASS. Other test files may fail until Task 2–4; record which ones.

- [ ] **Step 6: Commit** `feat(v2): slots, stability model and ballast`.

### Task 2: Slot-based deck state, checker and FCFS

**Files:** Modify `roro_yield/deck.py`, `roro_yield/fcfs.py`, `tests/test_deck.py`, `tests/test_fcfs.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `DeckState(vessel: Vessel)`: no `Scenario` (this is the information boundary). Attributes: `remaining_m: dict[Slot, float]`, `loads: dict[str, tuple[Booking, Slot]]`, `weight_t`, `plugs_used`. Properties: `placements -> dict[str, Slot]`, `moments -> (M_T, M_L)`, `ballast -> Ballast`, `heel_deg`, `trim_m`.
  - `feasible_slots(b) -> list[Slot]`; `best_slot(b) -> Slot | None` picks the minimum resulting `ballast.total_t`, ties going to the lower zone, then to lane order.
  - `why_not(b) -> str | None`, with reasons in this order: `"doesn't fit any lane"`, `"no lane has enough space left"`, `"no reefer plug available"`, `"would exceed max deadweight"` (when cargo alone exceeds it), `"would exceed max deadweight once ballast is added"`, `"would unbalance the ship beyond what ballast can correct"`.
  - `place(b, slot: Slot | None = None) -> Slot`: `None` → `best_slot`; raises `ValueError` if the slot is infeasible.
  - `copy() -> DeckState`.
  - `check_plan(scenario, plan) -> list[str]`, which adds zone length, DWT including ballast, tank capacity and "unknown slot" checks.
  - `solve_fcfs(scenario)` uses `DeckState(scenario.vessel)` with auto placement.

- [ ] **Step 1: Write the failing tests:**
  - `test_best_slot_balances`: the second heavy unit goes to the opposite side of the first.
  - `test_ties_prefer_stern_then_lane_order`: on an empty symmetric 2-lane deck, light cargo → `Slot("L1", 0)`.
  - `test_unbalance_reason`: tank capacity 0 and a tight heel limit on a 1-lane offset deck → the stability reason.
  - `test_dwt_with_ballast_reason`.
  - `test_place_rejects_infeasible_manual_slot`.
  - `test_check_plan_catches_heel_and_tank`.
  - Keep the v1 reason tests, adapted to slots.
  - `test_calibration_default`: on the default scenario (seeds 1–5), the FCFS plan's ballast ≤ 5% of max DWT, while a plan putting the same FCFS units stern-first in port lanes only needs > 15%.

- [ ] **Step 2: Run** `tests/test_deck.py tests/test_fcfs.py` → FAIL.

- [ ] **Step 3: Implement**, then tune `DEFAULT_STABILITY` (starting values: Δ 8,000 t, GM 1.5 m, MTC 100 t·m/cm, side arm 9 m, end arm 0.4 × lane length, tank capacity 300 t) until `test_calibration_default` passes.

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(v2): slot deck state, stability-aware checker and FCFS`.

### Task 3: KPIs, manifest and explainer

**Files:** Modify `roro_yield/kpis.py`, `roro_yield/manifest.py`, `roro_yield/explain.py` and their tests.

**Interfaces:**
- Produces:
  - `Kpis` gains `ballast_t`, `ballast_cost`, `heel_deg`, `trim_m`. `objective = margin − penalty − ballast_cost`. `dwt_pct` counts cargo + ballast.
  - `MANIFEST_COLUMNS = ["lane", "zone", "position", "booking_id", "customer", "segment", "unit_type", "length_m", "weight_t", "reefer"]`, plus one row per non-zero ballast tank with `lane="BALLAST"`, `unit_type` in {"port tank", "starboard tank", "fore tank", "aft tank"} and `weight_t` = tonnes.
  - `Decision.booking_id: str | None` and a new kind `"ballast"`. `costly_decisions(scenario, user, optimal, top_n=4)` adds one ballast decision when user ballast exceeds optimal ballast by > 10 t, with impact = the extra ballast cost and reason `"Your placement needed {x:.0f} t of ballast ({y:.0f} t more than the best plan): €{c:,.0f} of cost and deadweight you couldn't sell."`

- [ ] **Step 1: Failing tests:**
  - `test_objective_includes_ballast_cost`: a hand-built unbalanced plan → `objective == margin − 5 × ballast_t`.
  - `test_manifest_has_zone_and_ballast_rows`.
  - `test_ballast_decision_appears`.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run all engine tests except the optimizer** → PASS. **Step 5: Commit** `feat(v2): ballast in KPIs, manifest and explainer`.

### Task 4: Optimizer with zones, ballast and honest guard

**Files:** Modify `roro_yield/optimizer.py`, `tests/test_optimizer.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `solve_optimal(scenario, time_limit_s: float = 3, candidates: Sequence[Plan] = ()) -> Plan`. Model per spec §5.2: binary `y[i, slot]`, 4 continuous ballast variables bounded by `tank_cap_t`, heel/trim constraints as two-sided linear bounds, DWT includes ballast, objective includes ballast cost. It returns the best by `objective` of {MILP, FCFS, *candidates*}, relabelled `OPTIMAL_LABEL`. Warm-start the MILP from that best plan if PuLP's HiGHS interface accepts `warmStart=True`; otherwise skip it (the guard is mandatory, the warm start is not). Update the module docstring with the new formulation and the Thomsen et al. citation.

- [ ] **Step 1: Failing tests:**
  - The existing feasibility/≥ FCFS tests for seeds 1–10 (now including stability).
  - `test_balances_when_cheaper`: two heavy units and two lanes → opposite sides.
  - `test_candidate_guard`: a hand-made candidate plan with a higher score than the MILP's (MILP time limit 0.01) → returned plan has the candidate's placements.
  - `test_solves_default_under_5s`.
  - `test_extreme_scenarios_v2`: params `n_lanes=1`, `ballast_tank_cap_t=0`, `max_heel_deg=0.5`, `max_dwt_t=10`, `n_requests=200 & n_lanes=16`, `contract_share=0` → `check_plan == []` for FCFS and the optimizer.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run the full engine suite** → PASS and record the solve time of the default scenario in the commit message. **Step 5: Commit** `feat(v2): MILP with zones and ballast`.

### Task 5: Demand sampling for the advisor

**Files:** Modify `roro_yield/simulator.py`, `tests/test_simulator.py`

**Interfaces:**
- Produces:
  - `sample_future(params: ScenarioParams, after_frac: float, n_remaining: int, rng: np.random.Generator) -> list[Booking]`: draws with the same recipe as `generate_scenario` (factor the single-request draw into `_draw_request(rng, params)`), keeps only draws with `arrival_frac > after_frac` (rejection sampling, at most 10,000 attempts), sorted by arrival, ids `F001…`. Returns `[]` when `n_remaining == 0` or `after_frac >= 1`.
  - `expected_contract_m(params, after_frac, n_remaining, n_samples=200, seed=0) -> float`: the mean contract metres among `n_remaining` sampled requests.

- [ ] **Step 1: Failing tests:**
  - `test_sample_future_respects_after_frac`.
  - `test_sample_future_late_has_no_contract`: `after_frac=0.75` → no contract.
  - `test_sample_future_empty_cases`.
  - `test_sample_future_deterministic`.
  - `test_expected_contract_monotone`: decreases as `after_frac` grows.
  - `test_generate_scenario_unchanged`: the seed-42 scenario has the same booking ids, rates and weights as before the refactor (snapshot a few values taken from `main` before refactoring).

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat(v2): sample plausible futures`.

### Task 6: Advisor (one verdict)

**Files:** Create `roro_yield/advisor.py`, `tests/test_advisor.py`

**Interfaces:**
- Consumes: `DeckState` (Task 2), `sample_future` (Task 5), stability (Task 1).
- Produces:
  - `@dataclass(frozen=True) PolicyView(params: ScenarioParams, vessel: Vessel, commitment_m: float, penalty_per_m: float, deck: DeckState, history: tuple[Booking, ...], current: Booking, index: int, n_total: int, seed: int)`. `deck` is a copy; `history` holds every past request, accepted or not.
  - `@dataclass(frozen=True) Verdict(booking_id: str, accept: bool, feasible: bool, n_pays_off: int, k: int, expected_gain_eur: float, reason: str | None)`, with `.text` giving e.g. `"Accept — pays off in 16 of 20 futures, expected gain +€420"` / `"Reject — pays off in only 4 of 20 futures, expected gain −€310"` / `"Can't load: {reason}"`.
  - `advise(view: PolicyView, k: int = 20) -> Verdict`. Algorithm (spec §5.3): if `deck.why_not(current)` → infeasible verdict, no LP. Otherwise `rng = np.random.default_rng([seed, index])`; for each of the `k` futures `F = sample_future(params, current.arrival_frac, n_total − index − 1, rng)`, solve two **LP relaxations** of the §5.2 model over F, with the deck's existing loads fixed (remaining zone lengths, weight, plugs and moments as constants): (a) current placed at `deck.best_slot(current)`, (b) current rejected. Each future's floor = `min(commitment, contract m in history + current + F)`. Value = margin of the units in the LP (plus the current one's margin in (a)) − penalty × shortfall − ballast cost × ballast. `gain = V_a − V_b`. Use HiGHS with `msg=False`.

- [ ] **Step 1: Failing tests:**
  - `test_information_set`: build two scenarios with identical first 10 bookings but different remaining bookings → for index 0–9 the verdicts are identical. Construct views via a helper `view_from(scenario, params, deck, index)`, defined in the test, that slices history.
  - `test_infeasible_verdict`.
  - `test_last_request`: `n_remaining = 0` → accept iff margin > 0 and feasible.
  - `test_rejects_cheap_contract_early_when_spot_rich`: a hand-tuned params case (spot multiplier 1.5, contract share 0.3, a nearly full deck) → the early low-rate contract unit above the floor is rejected.
  - `test_deterministic`.
  - `@pytest.mark.slow test_verdict_time`: default scenario, index 10, k = 20 → < 3 s.
  - Register the `slow` marker in `pyproject.toml`.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; note the measured verdict time in the commit. If it is > 3 s, apply the spec levers in order (lower K → aggregate zones in the LP) and record which one. **Step 5: Commit** `feat(v2): sampled-futures advisor`.

### Task 7: Smart planner (full game without foresight)

**Files:** Modify `roro_yield/advisor.py`, `tests/test_advisor.py`

**Interfaces:**
- Produces:
  - `SMART_LABEL = "Smart planner (no foresight)"`.
  - `view_for(scenario, params, deck, index) -> PolicyView`, the public builder that the game and the tests use. Its history is `scenario.bookings[:index]` in arrival order and it never passes later bookings.
  - `smart_plan(scenario, params, k=20, on_progress: Callable[[int, int], None] | None = None) -> tuple[Plan, list[Verdict]]`: plays every request in order with its own `DeckState`, placing accepted units at `best_slot`.

- [ ] **Step 1: Failing tests:**
  - `test_smart_plan_feasible` (seeds 1–3, k = 5).
  - `test_smart_le_best`: `solve_optimal(s, candidates=(smart,))` ≥ smart.
  - `@pytest.mark.slow test_smart_mean_beats_fcfs`: seeds 1–10, k = 10 → mean smart score ≥ mean FCFS score.
  - `test_progress_callback_called`.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; record full smart-plan time at k = 20. **Step 5: Commit** `feat(v2): smart planner`.

### Task 8: Game session v2

**Files:** Modify `roro_yield/game.py`, `tests/test_game.py`

**Interfaces:**
- Produces:
  - `GameSession(scenario, params)`.
  - `deck: DeckState(scenario.vessel)`.
  - `accept(expected_index, slot: Slot | None = None) -> str | None`.
  - `request_accept(expected_index) -> str | None`: manual mode; stores `pending_index` and returns a reason if infeasible.
  - `confirm_slot(expected_index, slot) -> str | None`.
  - `cancel_pending()`.
  - `reject` clears `pending_index`.
  - `view_at_current() -> PolicyView`, via `view_for`.
  - `contract_floor_at_risk()` now uses `loaded_contract_m + expected_contract_m(params, current.arrival_frac, remaining) < commitment`.
  - `log` entries become `(booking_id, action, slot | None)`.

- [ ] **Step 1: Failing tests:**
  - `test_manual_flow`: request → confirm with a feasible slot → placed there.
  - `test_confirm_infeasible_slot_returns_reason`.
  - `test_pending_accept_cleared`: request → reject → nothing placed, index advanced once; request → cancel → same index.
  - `test_stale_index_ignored` (kept from v1).
  - `test_floor_risk_uses_expectation_not_queue`: changing the future bookings doesn't change the warning.

- [ ] **Step 2–4:** Run → FAIL, implement, run → PASS. **Step 5: Commit** `feat(v2): game session with manual placement`.

### Task 9: Deck chart and stability visuals

**Files:** Modify `app/deck_chart.py`, `tests/test_deck_chart.py`; Create `app/stability_view.py`, `tests/test_stability_view.py`

**Interfaces:**
- Produces:
  - `deck_figure(scenario, plan, title="", highlight: Sequence[Slot] = ()) -> go.Figure`: lanes ordered port (top) to starboard, labelled `"L1 P"` / `"L4 S"` (`"C"` when `y = 0`); dashed zone dividers; units stacked from each zone's stern edge; highlighted slots drawn green with an invisible clickable marker per slot carrying `customdata=str(slot)`.
  - `stability_gauges(heel_deg, trim_m, ballast_t, stab, max_dwt_t) -> None` (Streamlit; mockup option A): heel and trim meters with green/amber/red bands at 50% / 100% of the limit, and ballast with "% of sellable deadweight".
  - `ship_figure(heel_deg, trim_m, ballast: Ballast) -> go.Figure` (mockup option B): two subplots, astern view and side view; hull polygons rotated by the angle × `VISUAL_EXAGGERATION = 4`, captioned "angles exaggerated ×4"; tank fill proportional to tonnes.

- [ ] **Step 1: Failing tests:**
  - `test_zone_dividers_and_lane_labels`.
  - `test_highlight_markers_have_slot_customdata`.
  - `test_ship_figure_rotates_with_heel`: hull polygon x-coordinates differ between heel 0 and heel 2.

- [ ] **Step 2–4:** Run → FAIL, implement, run → PASS. **Step 5: Commit** `feat(v2): zone deck chart and stability visuals`.

### Task 10: Background jobs and game view

**Files:** Create `app/jobs.py`, `tests/test_jobs.py`; Modify `app/state.py`, `app/game_view.py`, `tests/test_app_smoke.py`

**Interfaces:**
- Produces:
  - `app/jobs.py`: `class JobRunner` (one worker thread, `concurrent.futures.ThreadPoolExecutor(max_workers=1)`), with `submit(key: tuple, fn, *args) -> None` (no-op if the key exists), `result(key) -> Any | None` (None while running), `progress(key) -> float` (0–1, set through a callback passed to `fn` as `on_progress`) and `forget_except(prefix: tuple)`. Pure Python: no Streamlit inside.
  - `app/state.py`:
    - `ADVISOR_K = int(os.environ.get("RORO_ADVISOR_K", 20))`.
    - `get_jobs() -> JobRunner`, stored in `st.session_state`.
    - `new_game(seed)` submits `("smart", seed)` → `smart_plan(scenario, params, ADVISOR_K, ...)` and forgets the jobs of other seeds.
    - Session keys `placement_mode` ("auto"/"manual", default "auto") and `advisor_on` (default False).
    - `verdict_for(seed, index) -> Verdict | None`, which reads the `("verdict", seed, index)` job.
  - `app/game_view.py`:
    - Toggles: a segmented control or radio, key `placement_mode`, with the exact labels; a toggle, key `advisor_on`.
    - Before applying any decision, submit `("verdict", seed, index)` → `advise(game.view_at_current(), ADVISOR_K)`. If the advisor is on, compute it synchronously under a spinner and show `verdict.text` in the request card.
    - Manual mode: Accept → `request_accept`; the deck shows `highlight=feasible_slots`; a zone click (`st.plotly_chart(on_select="rerun", selection_mode="points")`, or, if selection proves unreliable, a compact button grid with keys `slot_<lane>_<zone>`) → `confirm_slot`; and a Cancel button.
    - Stability panel: `stability_gauges` + `ship_figure`, live.

- [ ] **Step 1: Failing tests:**
  - `test_jobs_keyed_by_seed`: submit seed 1 and seed 2 jobs, `forget_except(("smart", 2))` → seed 1 result gone.
  - `test_job_progress`.
  - Smoke tests with env `RORO_ADVISOR_K=3`: the full auto game reaches the Reveal; `test_manual_game_places_in_chosen_zone`; `test_advisor_toggle_shows_verdict` (a markdown containing "futures").

- [ ] **Step 2–4:** Run → FAIL, implement, run → PASS. **Step 5: Commit** `feat(v2): game view with placement and advisor toggles`.

### Task 11: Reveal and Lab v2

**Files:** Modify `app/reveal_view.py`, `app/lab_view.py`, `app/state.py`, `tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `JobRunner`, `smart_plan`, `solve_optimal(..., candidates=)`, `costly_decisions`.
- Produces:
  - **Reveal:** waits on `("smart", seed)` with `st.progress(jobs.progress(...))` and reruns until it is done; `best = solve_optimal(s, candidates=(smart,))` (cache by seed); 4 cards in the order FCFS, You, Smart, Best, each with heel/trim/ballast in the caption; 4 deck tabs plus `ship_figure` per tab; the advisor-vs-you table (columns: #, request, you, advisor, futures, expected gain, ✗ on disagreements) built from the `("verdict", seed, i)` jobs, with a progress bar while incomplete and "verdicts use K = {k}" in the caption; costly decisions render `booking_id=None` as a plain bullet.
  - **Lab:** sliders `lab_heel` (0.5–5.0°, default 2.0), `lab_trim` (0.1–2.0 m, 0.5), `lab_tank` (0–600 t, 300), `lab_ballast_cost` (0–30 €/t, 5); lane-length minimum 70; the table gains Ballast/Heel/Trim rows; a button `lab_run_smart` runs `smart_plan` through the job runner keyed by params, with a progress bar, and adds a Smart column when done.
  - `benchmark_plans(params)` is unchanged in signature and still returns `(fcfs, best)`, where Best has no smart candidate in the Lab until smart has run.

- [ ] **Step 1: Failing smoke tests:**
  - The Reveal shows all 4 labels as metrics.
  - The advisor table exists with as many rows as requests.
  - The Lab heel slider changes without exception.
  - `lab_run_smart` then shows "Smart planner (no foresight)" in the table.

- [ ] **Step 2–4:** Run → FAIL, implement, run → PASS. Then run the full suite including slow tests: `.venv/Scripts/python.exe -m pytest -v` → all PASS. **Step 5: Commit** `feat(v2): four-way reveal, advisor table, stability Lab`.

### Task 12: README, deploy guide, push

**Files:** Modify `README.md`, `docs/deploy.md`, `streamlit_app.py` (intro copy: mention stability and the smart planner; keep the disclaimer)

- [ ] **Step 1:** README on `v2`:
  - A "v2" badge line under the title linking back to v1 (`/tree/v1.0`).
  - New sections "Stability" (model, limits, closed-form ballast, the linear/simplified disclaimer, Thomsen et al. citation) and "Smart planner (no foresight)" (information set, K futures, LP relaxation, accept rule, Zurheide & Fischer and Main citations, the honest note that it can lose to FCFS on a single unlucky sailing).
  - KPI table gains ballast/heel/trim.
  - Roadmap: stability and the online advisor marked done; v3 = web app (FastAPI + React); then multi-deck/hazardous, no-shows/overbooking, dynamic pricing, network.
  - New screenshots `docs/img/v2-game.png`, `v2-reveal.png`, taken by running the app locally (Kaleido is already in the venv).
- [ ] **Step 2:** `docs/deploy.md`: a section "Second app for v2": share.streamlit.io → Create app → same repo, **branch `v2`**, main file `streamlit_app.py`, Python 3.11, suggested URL `roro-yield-optimizer-v2.streamlit.app`. Add a note that after the first load the owner sends the URL back so it can be timed.
- [ ] **Step 3:** Verify: `.venv/Scripts/python.exe -m pytest -v` → all green; `streamlit run streamlit_app.py` locally, play one auto game and one manual game with the advisor on, and confirm the Reveal shows 4 contenders.
- [ ] **Step 4:** Commit `docs(v2): README, deploy guide, screenshots`; `git push -u origin v2`.
- [ ] **Step 5:** Owner deploys. Claude times one advisor verdict and the Reveal wait on the live URL. If over budget, report the numbers to the owner with the options (lower K / paid host) **before any spend**.
