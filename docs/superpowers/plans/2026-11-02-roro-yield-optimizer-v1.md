# RoRo Yield Optimizer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Streamlit web app where a recruiter plays Ro-Ro booking planner (Game), sees their result vs FCFS vs a MILP optimizer (Reveal), then experiments with sliders (Lab) — built on a clean, tested, reusable Python engine.

**Architecture:** Pure-Python engine package `roro_yield/` (domain models, simulator, deck state, FCFS, MILP optimizer, KPIs, game session, explainer, manifest) with no Streamlit imports. Thin Streamlit UI in `app/` plus root entrypoint `streamlit_app.py`. All game logic lives in the engine (`GameSession`) so it is unit-tested; the UI only renders and calls it.

**Tech Stack:** Python 3.11, PuLP (bundled CBC), numpy, pandas, plotly, streamlit, pytest. Hosting: Streamlit Community Cloud from a public GitHub repo.

**Spec:** `docs/superpowers/specs/2026-11-02-roro-yield-optimizer-design.md` (and its source `docs/project_specification.md`)

## Global Constraints

- Python only; `roro_yield/` must never import `streamlit`.
- Free/open-source tooling only. Solver: PuLP + bundled CBC.
- All UI copy and README in English.
- Data is synthetic; the app states "Synthetic but realistic data — not DFDS data" on the landing area and the README says the same.
- Optimizer is labelled in UI exactly: **"Best possible (perfect foresight)"**. FCFS labelled **"First come, first served"**. Player labelled **"You"**.
- Contract floor is soft everywhere: objective = margin − `shortfall_penalty_per_m` × shortfall metres, same formula for all three plans.
- Every accepted unit is placed in exactly one lane; per-lane sum of (length + lashing gap) ≤ lane length; total weight ≤ max DWT; reefers ≤ plugs. Applies to You, FCFS and Optimizer.
- Optimizer solve on a default scenario must return in ≤ 10 s (CBC `timeLimit=10`, `gapRel=0.005`); if time limit hits, return best incumbent, never crash.
- Deadline: public link by 2026-11-08. Deploy a skeleton on day 1 (Task 1).

### Pinned values (builder's call within spec latitude)

| Item | Value |
|---|---|
| Unit types | `semi_trailer` 13.6 m, 10–30 t · `accompanied_truck` 16.5 m, 20–40 t · `mafi` 12.2 m, 25–60 t · `van` 6.5 m, 2–3.5 t · `car_batch` 4.8 m, 1.2–2 t |
| Type mix (prob.) | semi_trailer 0.50, accompanied_truck 0.20, mafi 0.10, van 0.12, car_batch 0.08 |
| Reefer | only `semi_trailer` / `accompanied_truck`, prob. 0.30 |
| Rates (EUR/m) | contract U(45, 60); spot U(75, 110) × (1 + 0.15·arrival_fraction) |
| Reefer plug fee | 150 EUR (spot), 80 EUR (contract) |
| Handling cost | 80 EUR/unit + 1.5 EUR/t |
| Default vessel (game) | "MV Nordic Bridge" (fictional), Esbjerg → Immingham, 6 lanes × 120 m = 720 lm, max cargo DWT 1,100 t, 12 reefer plugs, lashing gap 0.5 m |
| Default demand | 60 requests, contract share 0.45 |
| Arrival order | contract arrival fraction U(0, 0.7); spot U(0.2, 1.0); sort ascending |
| Contract floor | 35% of total lane-metres (nominal metres) |
| Shortfall penalty | 200 EUR/m (> best spot margin per metre, so optimizer meets floor when it can) |

Note to owner: the design mentioned a ~2,000 lm vessel; the game uses 720 lm so 60 requests overbook it (~1.2×) and the trade-off is felt in one minute. The Lab lets users scale to 16 lanes / 200 requests.

## Review Focus

1. **Extreme Lab sliders** (1 lane, 0 plugs, tiny DWT, 200 requests): app must still render, optimizer returns a plan, KPIs don't divide by zero → test `test_extreme_scenarios_solve_and_evaluate` (Task 6/7).
2. **FCFS margin ≤ 0 makes "yield delta vs FCFS" undefined** → `yield_delta_pct` returns `None` and UI shows "n/a" → test in Task 6 (KPIs).
3. **Unit longer than any lane** (e.g. 16.5 m truck when lane length slider is 12 m) → never placeable, rejected with reason "doesn't fit any lane" → test in Task 4.
4. **Streamlit reruns / browser refresh mid-game** must not double-apply an accept or skip a booking → `GameSession.accept/reject` are idempotent per index (take `expected_index`) → test in Task 8.
5. **No contract bookings in scenario** (contract share slider 0) → floor becomes 0, no penalty, no crash → test in Task 3.

---

### Task 1: Repo skeleton + day-1 deploy

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `streamlit_app.py`, `roro_yield/__init__.py`, `app/__init__.py`, `tests/test_smoke.py`, `docs/deploy.md`, `README.md` (stub)

**Interfaces:**
- Produces: importable package `roro_yield` with `__version__ = "0.1.0"`; `streamlit_app.py` renders a title page.

- [ ] **Step 1:** `git init -b main` in repo root. `.gitignore`: `__pycache__/`, `.venv/`, `.pytest_cache/`, `.superpowers/`, `*.egg-info/`.
- [ ] **Step 2:** `requirements.txt`: `streamlit>=1.38`, `pulp>=2.8`, `numpy>=1.26`, `pandas>=2.1`, `plotly>=5.22`. `pyproject.toml`: project `roro-yield`, python `>=3.11`, pytest config `testpaths=["tests"]`, dev dep `pytest>=8`.
- [ ] **Step 3:** Create venv and install: `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest`.
- [ ] **Step 4:** Write `tests/test_smoke.py`: `import roro_yield; assert roro_yield.__version__ == "0.1.0"`. Run `.venv/Scripts/python -m pytest -v` → FAIL, then add `__init__.py` → PASS.
- [ ] **Step 5:** `streamlit_app.py`: `st.set_page_config(page_title="RoRo Yield Optimizer", page_icon="🚢", layout="wide")`, title, one-line pitch, "Coming soon". Check: `.venv/Scripts/streamlit run streamlit_app.py --server.headless true` starts without error.
- [ ] **Step 6:** Write `docs/deploy.md` — click-by-click for the owner: create public GitHub repo `roro-yield-optimizer` (no README), `git remote add origin … && git push -u origin main` (or GitHub Desktop), then share.streamlit.io → sign in with GitHub → New app → repo, branch `main`, file `streamlit_app.py`, Python 3.11 → Deploy. Owner sends back the URL.
- [ ] **Step 7:** Commit `chore: project skeleton and deploy guide`. **Pause for owner to deploy**; continue with Task 2 meanwhile.

### Task 2: Domain models

**Files:** Create `roro_yield/models.py`; Test `tests/test_models.py`

**Interfaces:**
- Produces:
  - `Segment = Literal["contract", "spot"]`
  - `@dataclass(frozen=True) UnitType(name: str, length_m: float, weight_range_t: tuple[float, float], can_be_reefer: bool)` and `UNIT_TYPES: dict[str, UnitType]` (values from Pinned table)
  - `@dataclass(frozen=True) Booking(id: str, arrival: int, segment: Segment, customer: str, unit_type: str, length_m: float, weight_t: float, is_reefer: bool, rate_per_m: float, reefer_fee: float, handling_cost: float)` with properties `revenue` (= length·rate + reefer_fee if reefer else 0) and `margin` (= revenue − handling_cost), method `effective_length(gap_m: float) -> float`
  - `@dataclass(frozen=True) Lane(id: str, length_m: float)`
  - `@dataclass(frozen=True) Vessel(name: str, route: str, lanes: tuple[Lane, ...], max_dwt_t: float, reefer_plugs: int, lashing_gap_m: float)` with property `total_lane_m`
  - `@dataclass(frozen=True) Scenario(vessel: Vessel, bookings: tuple[Booking, ...], contract_floor_m: float, shortfall_penalty_per_m: float)` with `booking(id) -> Booking`
  - `@dataclass Plan(method: str, placements: dict[str, str], rejected: list[str])` — `placements` maps booking id → lane id; property `accepted_ids`

- [ ] **Step 1: Failing tests:**
```python
def test_booking_revenue_and_margin():
    b = Booking("B1", 0, "spot", "Haulier A", "semi_trailer", 13.6, 20.0, True, 100.0, 150.0, 110.0)
    assert b.revenue == pytest.approx(13.6 * 100 + 150)
    assert b.margin == pytest.approx(1360 + 150 - 110)
    assert b.effective_length(0.5) == pytest.approx(14.1)

def test_non_reefer_gets_no_fee():
    b = Booking("B2", 0, "contract", "KA", "mafi", 12.2, 40.0, False, 50.0, 80.0, 140.0)
    assert b.revenue == pytest.approx(610.0)

def test_vessel_total_lane_m():
    v = Vessel("V", "A→B", tuple(Lane(f"L{i}", 120) for i in range(6)), 1100, 12, 0.5)
    assert v.total_lane_m == 720
```
- [ ] **Step 2:** Run `pytest tests/test_models.py -v` → FAIL (ImportError).
- [ ] **Step 3:** Implement `roro_yield/models.py`.
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat: domain models`.

### Task 3: Demand simulator

**Files:** Create `roro_yield/simulator.py`; Test `tests/test_simulator.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces: `@dataclass(frozen=True) ScenarioParams(n_requests=60, contract_share=0.45, n_lanes=6, lane_length_m=120.0, max_dwt_t=1100.0, reefer_plugs=12, lashing_gap_m=0.5, contract_floor_share=0.35, shortfall_penalty_per_m=200.0, spot_rate_multiplier=1.0, seed=42)`; `generate_scenario(params: ScenarioParams) -> Scenario`. Booking ids `"B001"…`, lane ids `"L1"…`, `arrival` = 0..n-1 after sorting. Customers: contract from 4 fictional key accounts ("Nordfreight", "Baltic Logistics", "Humber Forwarding", "Jutland Cargo"); spot "Spot haulier #k". `spot_rate_multiplier` scales spot rates (Lab "spot demand/price" slider).
- Contract floor = `min(contract_floor_share × total_lane_m, sum of contract nominal lengths)`.

- [ ] **Step 1: Failing tests:** `test_same_seed_same_scenario` (equal tuples), `test_different_seed_differs`, `test_counts_and_shares` (len == 60; contract count within 0.45·60 ± 10 for seed 42), `test_values_within_pinned_ranges` (lengths ∈ UNIT_TYPES lengths, weights in range, reefers only on reefer-capable types, contract rates 45–60, spot rates 75–110·1.15), `test_contracts_arrive_earlier_on_average`, `test_no_contracts_means_zero_floor` (contract_share=0 → contract_floor_m == 0), `test_demand_exceeds_capacity_by_default` (sum effective lengths > 720).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with `numpy.random.default_rng(seed)`, values from Pinned table. **Step 4:** PASS. **Step 5:** Commit `feat: synthetic demand simulator`.

### Task 4: Deck state + feasibility checker

**Files:** Create `roro_yield/deck.py`; Test `tests/test_deck.py`

**Interfaces:**
- Produces:
  - `class DeckState`: `__init__(self, scenario: Scenario)`; `remaining_m: dict[str, float]`; `weight_t: float`; `plugs_used: int`; `placements: dict[str, str]`; `why_not(self, b: Booking) -> str | None` (None if placeable; else one of exact strings `"doesn't fit any lane"`, `"no lane has enough space left"`, `"would exceed max deadweight"`, `"no reefer plug available"`); `place(self, b: Booking) -> str` (first-fit lane in lane order, raises `ValueError` if `why_not` is not None) returns lane id.
  - `check_plan(scenario: Scenario, plan: Plan) -> list[str]` — list of violation messages (empty = feasible): per-lane length incl. gap, DWT, plugs, unknown ids, booking both placed and rejected.
- `"doesn't fit any lane"` = effective length > every lane's full length (checked first).

- [ ] **Step 1: Failing tests:** place until lane L1 full then next goes to L2; `why_not` returns each of the four messages on crafted tiny scenarios; 16.5 m truck with 12 m lanes → `"doesn't fit any lane"`; `check_plan` catches an over-full lane, DWT breach, plug breach; empty plan is feasible.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: deck state and plan feasibility checker`.

### Task 5: FCFS baseline

**Files:** Create `roro_yield/fcfs.py`; Test `tests/test_fcfs.py`

**Interfaces:**
- Consumes: `DeckState`, `check_plan`.
- Produces: `solve_fcfs(scenario: Scenario) -> Plan` with `method="First come, first served"`. Iterate bookings by `arrival`, accept iff `why_not is None`.

- [ ] **Step 1: Failing tests:** `check_plan(s, solve_fcfs(s)) == []` for seeds 1..20; every rejected booking had a non-None `why_not` at its turn (replay); accepts in arrival order on a hand-made scenario.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: FCFS baseline`.

### Task 7: MILP optimizer (execute after Task 6)

**Files:** Create `roro_yield/optimizer.py`; Test `tests/test_optimizer.py`

**Interfaces:**
- Consumes: models, `check_plan`, `solve_fcfs` (tests only).
- Produces: `solve_optimal(scenario: Scenario, time_limit_s: int = 10) -> Plan` with `method="Best possible (perfect foresight)"`.

Formulation (multiple-knapsack with side constraints):
```
y[i,l] ∈ {0,1}  booking i in lane l   (only create y for lanes where eff_len_i ≤ len_l)
s ≥ 0           contract shortfall (m)
max  Σ margin_i · Σ_l y[i,l]  −  penalty · s
s.t. Σ_l y[i,l] ≤ 1                                   ∀i
     Σ_i eff_len_i · y[i,l] ≤ len_l                    ∀l
     Σ_i weight_i · Σ_l y[i,l] ≤ max_dwt
     Σ_{i reefer} Σ_l y[i,l] ≤ plugs
     s ≥ floor − Σ_{i contract} length_i · Σ_l y[i,l]
```
Symmetry note: lanes of equal length are interchangeable; acceptable at this size. Solve with `pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_s, gapRel=0.005)`. If status is not Optimal but a solution exists, use it; if none, return FCFS-like empty plan with all rejected (must still be valid).

- [ ] **Step 0:** Skim `docs/papers/RoRo stowage planning_ a systematic study of mathematical formulations.pdf` and `docs/papers/Optimization of stowage plans for RoRo ships.pdf` for their lane-assignment formulation; put a 2–3 line citation + how ours relates (simplified 1-D lane assignment, no ramps/stability) in the module docstring. Keep the formulation above unless a paper shows a clearly simpler sound variant.
- [ ] **Step 1: Failing tests:**
```python
@pytest.mark.parametrize("seed", range(1, 11))
def test_optimal_is_feasible_and_beats_fcfs(seed):
    s = generate_scenario(ScenarioParams(seed=seed))
    opt, fcfs = solve_optimal(s), solve_fcfs(s)
    assert check_plan(s, opt) == []
    assert objective(s, opt) >= objective(s, fcfs) - 1e-6   # objective from Task 6 (KPIs)

def test_prefers_high_margin_when_capacity_binds(): ...  # 1 lane 15 m, two 13.6 m units, margins 500 vs 900 → picks 900
def test_meets_contract_floor_when_possible(): ...       # hand-made: floor met although spot is richer
def test_solves_default_scenario_under_10s(): ...
def test_extreme_scenarios_solve_and_evaluate():          # Review Focus 1
    for p in [ScenarioParams(n_lanes=1), ScenarioParams(reefer_plugs=0), ScenarioParams(max_dwt_t=10),
              ScenarioParams(n_requests=200, n_lanes=16), ScenarioParams(lane_length_m=12.0)]:
        s = generate_scenario(p); plan = solve_optimal(s)
        assert check_plan(s, plan) == []; evaluate(s, plan)
```
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS (`pytest tests/test_optimizer.py -v`, note runtime). **Step 5:** Commit `feat: MILP optimizer with lane assignment`.

### Task 6: KPIs (execute before Task 7)

**Files:** Create `roro_yield/kpis.py`; Test `tests/test_kpis.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Kpis(method: str, n_accepted: int, revenue: float, margin: float, shortfall_m: float, penalty: float, objective: float, revpal: float, deck_util_pct: float, dwt_pct: float, plugs_used: int, contract_m: float)`
  - `evaluate(scenario: Scenario, plan: Plan) -> Kpis`; `objective(scenario, plan) -> float` (= margin − penalty)
  - `yield_delta_pct(value: float, baseline: float) -> float | None` — `None` if baseline ≤ 0
- Definitions: RevPAL = revenue / total_lane_m; deck_util_pct = Σ effective length / total_lane_m × 100; dwt_pct = Σ weight / max_dwt × 100 (0 if max_dwt is 0); shortfall = max(0, floor − contract nominal metres).

- [ ] **Step 1: Failing tests:** hand-computed values on a 2-booking scenario; `yield_delta_pct(110, 100) == 10`; `yield_delta_pct(5, 0) is None`; `yield_delta_pct(5, -3) is None` (Review Focus 2); empty plan → all zeros, shortfall = floor.
- [ ] **Step 2–5:** FAIL → implement → PASS → commit `feat: KPIs`.

### Task 8: Game session

**Files:** Create `roro_yield/game.py`; Test `tests/test_game.py`

**Interfaces:**
- Consumes: `DeckState`, `Plan`.
- Produces: `class GameSession`: `__init__(self, scenario)`; `index: int`; `current: Booking | None`; `is_finished: bool`; `deck: DeckState`; `log: list[tuple[str, str]]` (booking id, "accepted"/"rejected"); `accept(self, expected_index: int) -> str | None` (returns `None` on success or the `why_not` reason, in which case nothing changes and the booking stays current); `reject(self, expected_index: int) -> None`; both no-op if `expected_index != index` (Review Focus 4); `contract_floor_at_risk(self) -> bool` (contract metres accepted + remaining contract metres still to arrive < floor); `to_plan(self) -> Plan` with `method="You"`.

- [ ] **Step 1: Failing tests:** accept places & advances; infeasible accept returns reason and does not advance; reject advances; double `accept(expected_index=3)` only applies once; finished after last; `to_plan` feasible per `check_plan`; floor-at-risk flips true after rejecting enough contracts.
- [ ] **Step 2–5:** FAIL → implement → PASS → commit `feat: game session engine`.

### Task 9: Costly-decisions explainer + manifest

**Files:** Create `roro_yield/explain.py`, `roro_yield/manifest.py`; Test `tests/test_explain.py`, `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Decision(booking_id: str, kind: Literal["accepted_not_optimal","rejected_optimal"], impact_eur: float, reason: str)`
  - `costly_decisions(scenario, user: Plan, optimal: Plan, top_n: int = 4) -> list[Decision]` — bookings where user and optimal differ, `impact_eur` = |booking.margin| (+ penalty·length for contract bookings when the user plan has shortfall), sorted desc. Reason copy (exact templates):
    - accepted_not_optimal: `"You accepted {customer}'s {type} at €{rate:.0f}/m. Its {eff:.1f} m were worth more to higher-yield cargo."`
    - rejected_optimal: `"You turned down {customer}'s {type} at €{rate:.0f}/m — €{margin:,.0f} of margin left on the quay."`
  - `manifest_dataframe(scenario, plan) -> pandas.DataFrame` columns `["lane","position","booking_id","customer","segment","unit_type","length_m","weight_t","reefer"]`, sorted by lane then position (order in lane); `manifest_csv(scenario, plan) -> bytes` (UTF-8).
- [ ] **Step 1: Failing tests:** identical plans → `[]`; crafted diff yields both kinds with correct copy and order; `top_n` respected; manifest rows == accepted count, columns exact, CSV decodes and has header.
- [ ] **Step 2–5:** FAIL → implement → PASS → commit `feat: decision explainer and loading manifest`.

### Task 10: Deck drawing

**Files:** Create `app/deck_chart.py`; Test `tests/test_deck_chart.py`

**Interfaces:**
- Produces: `deck_figure(scenario: Scenario, plan: Plan, title: str = "") -> plotly.graph_objects.Figure` — lanes as horizontal grey strips (bow on the right, lanes top-to-bottom L1..Ln), each placed unit a rectangle sized by length, colour by segment (contract = blue `#3B6FD4`, spot = green `#2FA67C`), reefer units with a ❄ text label, hover shows booking id, customer, type, weight, rate. Fixed height ≈ 60 px/lane + 80.
- [ ] **Step 1: Failing test:** number of unit shapes == accepted count; figure has n_lanes lane shapes; empty plan renders.
- [ ] **Step 2–5:** FAIL → implement → PASS → commit `feat: plotly deck drawing`.

### Task 11: Streamlit app — Game, Reveal, Lab

**Files:** Create `app/game_view.py`, `app/reveal_view.py`, `app/lab_view.py`, `app/state.py`; Modify `streamlit_app.py`; Test `tests/test_app_smoke.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `app/state.py`: `get_session() -> GameSession` stored in `st.session_state["game"]`, `new_game(seed: int)`; stage in `st.session_state["stage"] ∈ {"game","reveal","lab"}`. Each view exposes `render() -> None`.

Behaviour:
- **Landing (top of Game):** title, 2-sentence pitch, "Synthetic but realistic data — not DFDS data", 3-step progress indicator (Play → Reveal → Lab). "Skip to the Lab" link for impatient visitors.
- **Game:** left: `deck_figure` of current deck + gauges (lane-m %, DWT %, plugs x/y, contract metres vs floor, running margin). Right: request card (n of N, segment badge, type, length, weight, reefer, rate, fee, margin) + Accept / Reject buttons passing `expected_index`. Accept failure shows reason as `st.warning`. Floor-at-risk shows `st.info("Rejecting more contract cargo risks the €200/m shortfall penalty")`. On finish → stage "reveal".
- **Reveal:** three `st.metric` columns (FCFS / You / Best possible) for objective with delta vs FCFS (`yield_delta_pct`, "n/a" if None), RevPAL, utilisation; three deck figures in tabs; "Where you lost the most" list from `costly_decisions`. Buttons "Play again" (new seed) and "Open the Lab →".
- **Lab:** sliders bound to `ScenarioParams` (requests 30–200, contract share 0–0.9, spot price ×0.7–1.5, lanes 1–16, lane length 12–250 m, DWT 10–5000 t, plugs 0–40, lashing gap 0–1.5 m, seed). Run both solvers inside `st.spinner`, cache by params with `st.cache_data`. Show KPI table (FCFS vs Best possible), optimal deck figure, bar chart of accepted metres by segment for each method, `st.download_button("Download loading manifest (CSV)", manifest_csv(...), "manifest.csv")`.

- [ ] **Step 1: Failing test** with `streamlit.testing.v1.AppTest`: `AppTest.from_file("streamlit_app.py").run()` has no exception; clicking Accept/Reject 60 times reaches stage "reveal" without exception; switching to lab runs without exception.
- [ ] **Step 2:** FAIL. **Step 3:** Implement views. **Step 4:** PASS + manual run `streamlit run streamlit_app.py`, play one full game in the browser, check all three stages. **Step 5:** Commit `feat: game, reveal and lab UI`; push; confirm the public URL updates.

### Task 12: README shop window + final deploy

**Files:** Modify `README.md`; Create `docs/img/` (screenshot/GIF)

- [ ] **Step 1:** README sections: one-line pitch + **live app link** at top; GIF/screenshot; "The problem" (Ops vs Commercial tension, 4 lines); "How to play"; "The model" (formulation from Task 7 in LaTeX, KPIs table); "Academic grounding" (the two stowage papers + how ours simplifies them); "Roadmap" with citations from `docs/papers/`: online booking advisor / bid prices (*A revenue management slot allocation*; *A Dynamic Pricing Model for a Maritime Transportation Service Provider*), multi-deck & stability (*RoRo Ships Stowage Planning: Using a Novel MIP Model and Stability Constraints*; *A Two-Phase Stowage Approach for Passenger-Cargo RoRo Ship…*), fleet & network (*Combined maritime fleet deployment and inventory management…*); "Run locally"; "Synthetic data" disclaimer; author line.
- [ ] **Step 2:** Verify: `pytest -v` all green; live URL loads in a private window, full game playable, Lab manifest downloads.
- [ ] **Step 3:** Commit `docs: README and roadmap`; push.
