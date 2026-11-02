# RoRo Yield Optimizer — Design (v1)

*Date: 2026-11-02 · Owner: Vincenzo Testini · Source spec: `docs/project_specification.md`*

## 1. Intent & why

A web app that a recruiter of the **DFDS Graduate Programme** opens from a link and immediately *plays with*. It must show that the author is a capable student with interesting ideas and initiative (owner's words).

It is also the **first version of a real product**: the owner wants to keep upgrading it and possibly turn it into a startup. So it is not a throwaway demo — the core engine must be clean, tested and reusable behind a different UI or an API later.

The business idea (from the source spec): Ro-Ro ferry space is perishable; accepting bookings first-come-first-served (FCFS) lets low-yield contract cargo crowd out high-yield spot cargo. An optimizer (MILP) that chooses which bookings to accept — respecting deck, weight, reefer-plug and contract-quota limits — earns more per lane-metre (RevPAL).

## 2. Goals, non-goals, anti-goals

**Goals (v1)**
- Public URL, opens instantly, no install, no login.
- Three-step experience (approved by owner on a mockup):
  1. **Game — "You are the planner."** ~60 booking requests arrive one at a time for a single sailing. The user accepts/rejects each. Live deck drawing fills up lane by lane; gauges show lane-metres, weight (DWT), reefer plugs, contract-quota progress, running margin.
  2. **Reveal — "How did you do?"** Side-by-side: FCFS vs. You vs. Optimizer (margin, RevPAL, utilisation, delta vs FCFS), three deck drawings, and "the 3–4 decisions that cost you the most" with a short plain-English reason each.
  3. **Lab — "Change the rules."** Sliders (spot demand level, contract share, reefer plugs, lashing gap, vessel capacity, etc.). Optimizer and FCFS re-run; deck and yield-vs-FCFS charts update. Button to download the loading manifest (CSV).
- Engine implements the source spec's model (Section 4 of `project_specification.md`) **plus lane assignment**: each accepted unit is assigned to a specific deck lane, so the deck drawing is real, not decorative.
- README that works as a shop window: what it is, link to live app, screenshot/GIF, the model in brief, academic grounding, roadmap.

**Non-goals (v1, explicitly postponed to roadmap)**
- Multiple decks, stability/trim/GM, axle loads, ramp/loading-order sequencing.
- Dynamic pricing, stochastic demand / booking-limit policies over time.
- Real DFDS data, user accounts, persistence, multi-sailing networks, API.

**Anti-goals (failure even if it "works")**
- Not having a working public link by day 6. Scope is cut before the deadline is risked.
- A recruiter getting confused or bored in the first minute (needs onboarding text, sensible defaults, fast solves).
- Claiming the data is real DFDS data. Data is synthetic but realistic, stated clearly.
- A tangled codebase where the math is mixed into UI code — blocks the startup path.

## 3. Constraints

- **Deadline:** application link needed in **6 days** (by 2026-11-08). Plan: days 1–4 build & deploy full v1; days 5–6 polish, README, buffer.
- **Owner skill level:** beginner in all languages; future work will likely be AI-assisted. Code must be simple, readable, one language, well-tested.
- **Cost:** free tooling and hosting only.
- **Public:** code goes in a public GitHub repo (owner has an account, agreed to public).
- **Language of the app and README:** English (DFDS works in English). *(Claude's call.)*

## 4. How — decisions made

*All of these are Claude's calls; the owner delegated technical choices ("scarso su tutto, fai tu").*

- **Python only.**
- **Structure:** an importable engine package (e.g. `roro_yield/`) separate from the UI (`app/`). Engine modules, roughly:
  - domain models (unit types, booking, vessel, sailing scenario),
  - demand simulator (seeded synthetic booking stream),
  - MILP optimizer (accept/reject + lane assignment),
  - FCFS baseline (same constraints, accept in arrival order if feasible),
  - KPIs (margin, RevPAL, deck utilisation, DWT saturation, yield delta vs FCFS),
  - "costly decisions" explainer for the Reveal,
  - manifest export.
- **Solver:** PuLP with the bundled CBC or HiGHS (free, open source). Must solve a ~60-booking instance in a couple of seconds on Streamlit Cloud.
- **UI:** Streamlit, deployed on Streamlit Community Cloud from the public GitHub repo. Deck drawn with Plotly (or SVG) — lanes as horizontal strips, units as coloured blocks by segment/type, rejected units shown aside.
- **Tests:** pytest on the engine (constraint compliance of every solution, optimizer ≥ FCFS on the same queue, simulator determinism with a seed, KPI formulas).
- **Data realism:** unit profiles from the spec (13.6 m semi-trailer, 16.5 m accompanied truck, 12.2 m mafi, vans/cars), realistic weights, a fictional-but-plausible North Sea route and vessel (~2,000 lane-metres), rates in EUR/m with spot premium and reefer plug fee.
- **Academic grounding:** the lane-assignment formulation takes inspiration from *RoRo stowage planning: a systematic study of mathematical formulations* and *Optimization of stowage plans for RoRo ships* (in `docs/papers/`); the builder reads these and adopts the simplest sound element. Other papers feed the README roadmap with citations (stability/multi-deck, slot allocation in revenue management, dynamic pricing).

### 4.1 Rules settled after builder review *(Claude's calls)*

- **Contract quota is soft, with a penalty, everywhere.** The optimizer, FCFS and the player are all scored on the same objective: margin minus a per-metre penalty for any shortfall below the Key Account floor. The penalty is set high enough that the optimizer meets the floor whenever it can. This keeps the comparison fair, means Lab sliders can never produce an infeasible model, and makes FCFS/player breaches visible ("contract shortfall: −€X"). The game shows quota progress live and warns when rejecting a contract unit puts the floor at risk. Rejecting a contract unit above the floor costs only its lost margin.
- **The optimizer has perfect hindsight.** It sees the whole booking queue and is labelled in the UI as *"Best possible (perfect foresight)"*, i.e. a benchmark, not an online decision tool. An online/rolling advisor (re-solve on each arrival, bid-price hints during the game) goes in the roadmap as the first product upgrade.
- **Every accept is checked per lane, not just on total metres.** A unit can be accepted (by player or FCFS) only if it fits in some single lane, plus weight and plug limits. The game and FCFS use the same simple placement rule (first lane with enough remaining length). The optimizer assigns lanes inside the MILP. So all three deck drawings are real stowage plans, and the compliance tests check per-lane length, DWT and plugs for all three.
- **Deploy early.** The plan includes a "hello world" deployed to Streamlit Cloud on day 1. The owner does the account steps (GitHub repo creation/auth, Streamlit Cloud sign-in and "New app") following click-by-click instructions. Claude does everything else.

## 5. Left to the builder

- Exact parameter values, rate levels, number of lanes and lane lengths, game length (~60 requests is a guide).
- How the "costly decisions" are computed (e.g. compare user's accept set with optimal and rank by margin impact), as long as each comes with a one-line human reason.
- Visual styling, colours, copy, onboarding text.
- Whether the game's capacity gauges block infeasible accepts (recommended: yes, with a message).
- Repo layout details, dependency management, CI.
