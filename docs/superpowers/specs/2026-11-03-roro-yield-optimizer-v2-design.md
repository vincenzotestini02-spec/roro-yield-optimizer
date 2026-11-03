# RoRo Yield Optimizer — Design (v2: stability + smart planner)

*Date: 2026-11-03 · Owner: Vincenzo Testini · Builds on: `2026-11-02-roro-yield-optimizer-design.md` (v1, shipped)*

## 1. Intent & why

v1 is live: a Streamlit game (Game → Reveal → Lab) where the player accepts/rejects 60 booking requests for one Ro-Ro sailing and is compared with FCFS and a MILP optimizer. v2 is a **second, separate version** with its own public link, so the owner can choose which one to send to the DFDS Graduate Programme by **2026-11-08**. v1 stays untouched.

v2 answers the two objections an expert reader of the literature in `docs/papers/` would raise:

1. **"Your optimizer cheats."** v1's benchmark sees all future requests. No DFDS planner has that. v2 adds a **smart planner without foresight**: at each request it samples plausible futures and decides whether accepting pays off. It knows the demand *distribution* (the simulator's recipe), never the actual requests. Grounding: booking-control / bid-price ideas in Zurheide & Fischer, *A revenue management slot allocation model for liner shipping networks* (2012); uncertain cargo arrivals in Main, *Optimizing RoRo Stowage Planning* (DTU PhD, 2024).
2. **"Your ship has no physics."** v1's lanes are 1-D strips with no stability. v2 gives every unit a **position on deck** (lane × zone), computes heel and trim, and corrects imbalance with **ballast water that consumes sellable deadweight**, so stability becomes a commercial cost. Grounding: simplified "simple stability with centre-of-gravity limits and ballast adjustments" from Thomsen, Levinsen, Pacino & Reinhardt (DTU / **DFDS A/S**), *RoRo stowage planning: a systematic study of mathematical formulations* (2026).

## 2. Goals, non-goals, anti-goals

**Goals (v2)**
- Everything in v1 keeps working (game, reveal, lab, manifest, tests).
- **Stability (owner chose "option 2C": longitudinal + transverse).**
  - Each lane is split into **4 zones** from stern (ramp) to bow. Each accepted unit occupies one zone of one lane.
  - Heel (port/starboard) and trim (bow/stern) are computed from cargo + ballast moments; ballast tanks can correct them, and ballast tonnes count against max deadweight.
  - A load that cannot be corrected within ballast-tank capacity and the deadweight limit is refused with a reason ("would heel the ship beyond 2° even with full ballast").
- **Placement toggle in the game (owner's request):** a button switches between **"🤖 App places them"** (default) and **"✋ I place them"**. In manual mode, after Accept, the player clicks one of the highlighted zones where the unit fits.
- **Stability panel in the game (owner chose both):** (A) gauges for heel, trim and ballast needed (with "% of sellable deadweight eaten"), and (B) two small ship pictures that actually tilt: seen from astern (heel) and from the side (trim). Mockup: `.superpowers/brainstorm/1918-1793712985/content/game-stability.html`.
- **Smart planner (owner chose "option 1C": optimise over sampled futures).**
  - **Advisor toggle in the game (owner's request):** a "💡 Advisor" button, **off by default**. When on, every request shows the advisor's verdict, e.g. *"Accept — pays off in 16 of 20 futures, expected gain +€420"*.
  - **Reveal:** a 4th contender, *"Smart planner (no foresight)"*, next to FCFS, You and *Best possible (perfect foresight)*, with its deck, stability and KPIs.
  - **Reveal:** a per-request table, "what the advisor would have said vs what you did", highlighting disagreements. *(Claude's reading of the owner's "consigliere ad ogni richiesta".)*
- Separate deployment: branch `v2`, second Streamlit Community Cloud app, own URL. v1 is tagged `v1.0` on `main` and its app keeps running.

**Non-goals (v2)**
- Shear force / bending moment ("full stability"), vertical centre of gravity / GM changing with load, free-surface effects.
- Loading/discharge sequence, ramp blocking, re-handling, multiple ports, multiple decks.
- Hazardous-cargo segregation, per-zone reefer plugs (plugs stay a global count).
- Dynamic pricing, multi-sailing network (roadmap items 5 and 6).
- A non-Streamlit web app (React/FastAPI): planned as **v3**, the startup path.

**Anti-goals**
- Breaking or changing the live v1 link.
- A recruiter confused in the first minute: defaults are auto placement and advisor off, so v2 plays like v1 until the player opts in.
- An advisor that secretly uses the real future requests. Its information set must be provably limited (enforced by tests).
- The game freezing: no user-facing wait over ~2 s per request without a visible spinner; nothing over ~5 s.
- Overstating the physics: the README states that stability is a linear, simplified model and not a class-approved loading computer.

## 3. Constraints

- **Deadline:** 2026-11-08 for the owner's choice of link. v2 is optional; if it isn't solid by then, the owner sends v1. Scope-cut order if time runs short (Claude's call): (1) drop the smart planner from the Lab, (2) drop the per-request advisor table in the Reveal, (3) drop manual placement. Stability and the in-game advisor are the core and are not cut.
- **Owner skill:** beginner; everything stays Python, readable, tested. The engine (`roro_yield/`) stays free of Streamlit imports.
- **Cost:** free hosting first (Streamlit Community Cloud, ~1 GB RAM, shared CPU). If measured speed is unacceptable there, Claude proposes a paid host (e.g. Hugging Face Spaces CPU upgrade) **and asks the owner before any spend**.
- **Language:** app, README and code in English; conversation with the owner in Italian.

## 4. Approaches considered

**Smart planner**
- A. Bid price from one deterministic LP re-solved at each request: fast, standard RM, but approximate.
- B. Static booking limits (Zurheide & Fischer): simplest and easy to explain, but rigid, and it counts metres only.
- **C. Optimise over sampled futures (chosen by the owner, "the most detailed one").** At each request, sample K plausible futures, solve "accept now" vs "reject now" for each, and decide on the expected value. It is the most faithful to the real decision. The price is compute, which is managed by solving the sampled problems as LP relaxations (§5.3).

**Stability**
- A. Hard transverse limit only.
- B. Transverse with ballast that eats deadweight (Claude's original recommendation).
- **C. Longitudinal + transverse with ballast (chosen by the owner).** Needs a position along the lane, hence the lane × zone grid. It is a simplified cousin of Thomsen et al.'s grid / hybrid-slot representations, which their study finds stronger than the pure lane model v1 uses.

**Platform:** Streamlit kept (owner agreed); real web app deferred to v3.

## 5. How: decisions made

All Claude's calls unless marked as the owner's.

### 5.1 Vessel geometry and stability model

- `Lane` gains a transverse offset `y_m` from the centreline (port negative, starboard positive). Lanes are spread evenly across the beam for any lane count from the Lab slider (1–16): with an odd count the middle lane sits on the centreline, and a single lane has `y = 0`. Default: 6 lanes, 3 per side.
- Each lane has **4 zones** of length `lane_length / 4`, each with a longitudinal centre `x_m` from midships (aft negative). A unit's moment arm is its zone centre. Within a zone, units are stacked bow-wards in loading order, for drawing only.
- The Lab's lane-length slider minimum rises to **70 m**, so a zone (≥ 17.5 m) always fits the longest unit (16.5 m + lashing gap).
- Moments: `M_T = Σ w_i · y_lane(i)`, `M_L = Σ w_i · x_zone(i)` over loaded cargo. The light ship is assumed balanced.
- Allowed imbalance without ballast: `|M_T| ≤ H` and `|M_L| ≤ T`, with `H = Δ · GM · tan(θ_max)` and `T = MTC · 100 · trim_max`. Δ, GM, MTC, θ_max (default 2°) and trim_max (default 0.5 m) are plausible constants **scaled to the current default vessel** (6 × 120 m = 720 lane-metres, 1,100 t cargo deadweight), chosen by the builder and shown in the Lab. The vessel is *not* resized, so v1's game balance is kept.
- Ballast: **four tanks**. Port and starboard sit at midships (`x = 0`, `y = ±a_T`); fore and aft sit on the centreline (`y = 0`, `x = ±a_L`). Each has a capacity. Because the tank arms are decoupled, the **minimum ballast is closed-form**: `B_T = max(0, |M_T| − H) / a_T` on the opposite side, and likewise `B_L` fore/aft. A load is feasible iff `B_T` and `B_L` fit their tanks and `cargo_weight + B_T + B_L ≤ max_dwt`. The game, FCFS and the checker use this exact formula, and the MILP encodes the same model linearly. Ballast also carries a small cost (default €5/t, for pumping and extra fuel) so that it is never free.
- Display: heel `θ = atan(residual M_T / (Δ · GM))` in degrees, trim `= residual M_L / (MTC · 100)` in metres, where residual means after ballast. With ballast correcting to the limit, the residual sits at most at the limit.

### 5.2 Optimizer (perfect-foresight benchmark), extended

- Binary `y[i, l, z]`; per-zone length capacity; one placement per booking; deadweight now `Σ w·taken + Σ ballast ≤ max_dwt`; reefer plugs and the soft contract floor as in v1.
- Continuous ballast `b_k ∈ [0, cap_k]` for the 4 tanks; linear constraints `−H ≤ M_T + Σ b_k y_k ≤ H` and `−T ≤ M_L + Σ b_k x_k ≤ T`.
- Objective: margin − contract-shortfall penalty − ballast cost. Every method (You, FCFS, Smart, Best) is scored on this same objective; KPIs gain ballast tonnes, heel and trim.
- **Contract floor (information-set fix).** Today the floor is `min(share · deck, contract metres actually drawn)`, which leaks how much contract cargo is still to come. v2 splits it into a **public commitment** `C = share · deck`, which is known to everyone (player, advisor, all methods), and a realised floor `min(C, contract metres actually requested)`, which is used **only for scoring at the end**. This matches real Key Account contracts: the guarantee covers cargo the customer actually books. In each sampled future the advisor computes its own floor `min(C, contract metres in that future)`. The game's "contract guarantee at risk" warning stops reading the real queue. It fires when the contract metres loaded, plus the *expected* contract metres still to come (from the demand distribution and the number of requests left), fall below `C`.
- **"Best possible" stays the best shown plan.** The existing guard is extended: Best = the best of {MILP result, FCFS plan, Smart-planner plan}, and the MILP is warm-started from the best of these. Then Smart ≤ Best holds by construction, even when the time limit stops HiGHS early, and the label stays honest.
- Size is about 60 × 6 × 4 = 1,440 binaries. Keep HiGHS with a time limit and the existing "never worse than FCFS" guard. Lanes are no longer symmetric, which should help the solver. The builder measures the time and tunes the limit (target ≤ 3 s on Streamlit Cloud).

### 5.3 Smart planner (sampled futures)

- `Booking` gains `arrival_frac` (0–1 position in the booking window; the simulator already draws it). The policy may see: the current request, the bookings already decided, the current deck state, the public count "request k of n", and the simulator's `ScenarioParams`. It must **not** see the scenario's remaining bookings. Enforce this structurally: the policy function receives a "view" object, not the `Scenario`.
- The simulator gains `sample_future(params, after_frac, n_remaining, rng)`: it draws the remaining requests with the same recipe, conditioned on arriving after `after_frac`.
- Decision per request: draw **K = 20** futures (deterministic rng seeded from `(seed, request index)`). For each future, solve the **LP relaxation** of the §5.2 model with the existing placements fixed. The current booking is forced in (placed in the zone it would go to) or forced out. Compute `gain_f = V_accept,f − V_reject,f`. Recommend **Accept iff mean gain > 0** and the load is feasible. Report "pays off in N of K futures" (count of `gain_f > 0`) and the mean gain in €.
- Placement when the smart planner accepts: the auto-placement rule (§5.4). The planner decides *whether* to accept, not where. "Feasible" means *some* zone is feasible; the forced-in LP uses the zone the auto rule would pick.
- **Advisor-vs-you table** judges each request against **the player's own deck at that moment**, so it compares like with like. If the advisor toggle was on, the verdicts already exist. If it was off, each verdict is computed in the background right after the player's decision, queued behind the Smart-planner run. The Reveal shows the table when it is ready, with a progress bar for any remainder, and never blocks the score cards. If combined compute misses the budget, the table's verdicts may use a lower K than the live advisor; the table says which K it used.
- Performance targets: one advisor verdict ≤ ~1.5 s on Streamlit Cloud (40 LPs). The full Smart-planner game (60 verdicts) runs in a **background thread** started when a game begins, cached by seed, and is ready by the Reveal (the spinner only covers any remainder). In the Lab the smart planner runs only on a "Run smart planner" button, with a progress bar, because slider changes would otherwise trigger ~1 min of compute.
- If the measured times miss the targets, the levers in order are: lower K (min 10); aggregate zones in the futures' LP; then a paid host (ask the owner first).

### 5.4 Placement rule (game auto mode and FCFS)

Among the (lane, zone) slots where the unit fits and the result is feasible, choose the one that **minimises the required ballast after loading**. Ties go to the zone nearest the stern ramp, then the lowest lane id. FCFS uses the same rule, so the comparison stays fair; the old "first lane with space" rule is retired.

### 5.5 UI (Streamlit)

- **Stability-blocked requests:** if no zone is feasible once ballast and deadweight are counted, Accept is refused with the reason, exactly like v1's "doesn't fit". In manual mode Accept is a two-step action: (1) Accept, then (2) pick one of the highlighted *feasible* zones, with a Cancel option. Infeasible zones are never clickable, so a manual player can choose a costlier-but-feasible zone, never an infeasible one.
- **Game:** a placement toggle and an advisor toggle at the top. The deck chart shows a 6 × 4 zone grid. In manual mode, feasible zones are highlighted after Accept and the player clicks one; Plotly selection events are preferred, and the builder may fall back to a compact button grid if click handling is unreliable on Streamlit Cloud. The stability panel shows the gauges (A) and the two tilting ship drawings (B), both updating live. A refusal message names the binding limit.
- **Reveal:** four contender cards (FCFS, You, Smart planner, Best possible), each with score, KPIs, ballast, heel and trim; deck tabs for all four; the advisor-vs-you table (request, your action, advisor verdict, N/K, expected gain, a ✗ mark on disagreements); costly decisions may now include placement reasons ("placed to port: required 30 t of ballast").
- **Lab:** new sliders for max heel, max trim, ballast tank capacity and ballast cost; the smart planner behind a button; the manifest CSV gains lane, zone, position and a ballast summary.

### 5.6 Testing

- Compliance: every plan from every method passes the extended `check_plan`: zone lengths, deadweight including ballast, plugs, heel and trim limits after ballast, and tank capacities.
- The closed-form ballast matches the MILP's ballast on fixed placements.
- Information-set test: the advisor's verdicts don't change when the scenario's *future* bookings are replaced by different ones. This is possible because of the public-commitment floor in §5.2.
- Determinism: same seed → same verdicts and same smart-planner plan.
- Ordering: on every tested seed, Smart ≤ Best possible (guaranteed by the §5.2 guard). Across a fixed set of ~10 seeds, Smart's mean score ≥ FCFS's mean. A per-seed win is not required: no-foresight policies can lose on one bad draw, and the Reveal copy must not promise otherwise.
- Timing test (marked slow): one advisor verdict under a budget on the default instance.
- The existing v1 tests are updated where the model changed (zones, placement rule), never deleted to make them pass.

### 5.7 Delivery

- Tag the current `main` as `v1.0`. Develop on branch `v2`, pushed to the same GitHub repo. The owner creates a second Streamlit Cloud app from branch `v2` (click-by-click steps in `docs/deploy.md`, updated).
- README on `v2`: new sections "Stability" and "Smart planner (no foresight)" with the formulation, the information-set statement and citations. The roadmap moves stability and the online advisor to "done in v2" and adds v3 (web app) and the remaining items.

## 6. Left to the builder

- Exact physical constants (Δ, GM, MTC, tank arms and capacities, lane offsets) within plausible ranges, chosen so that on the default scenario stability **matters but doesn't dominate**: careless placement should cost noticeable ballast, while sensible placement needs little.
- The visual style of the tilting-ship drawings and gauges (follow the mockup's spirit).
- Thread / caching mechanics for the background smart-planner run in Streamlit.
- Exact advisor copy, table styling, colours.
- Whether to store `arrival_frac` on `Booking` or alongside it, provided the information-set boundary holds.
