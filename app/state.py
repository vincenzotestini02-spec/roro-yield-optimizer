"""Session state helpers: the current game and which stage (game / reveal / lab) is shown."""

from __future__ import annotations

import os
from dataclasses import replace

import streamlit as st

from app.jobs import JobRunner
from roro_yield.advisor import Verdict, advise, smart_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.game import GameSession
from roro_yield.models import Plan
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams, generate_scenario

GAME_PARAMS = ScenarioParams()
STAGES = ("game", "reveal", "lab")
ADVISOR_K = int(os.environ.get("RORO_ADVISOR_K", 20))
PLACEMENT_MODES = {"auto": "🤖 App places them", "manual": "✋ I place them"}
ADVISOR_TOGGLE_LABEL = "💡 Advisor"


def get_jobs() -> JobRunner:
    if "jobs" not in st.session_state:
        st.session_state["jobs"] = JobRunner()
    return st.session_state["jobs"]


# Streamlit drops a widget's state on a run where the widget isn't drawn (e.g. the Reveal), so the
# player's choices are mirrored in plain session keys and restored from there.
_TOGGLE_DEFAULTS = {"placement_mode": "auto", "advisor_on": False}


def _pref_key(key: str) -> str:
    return f"pref_{key}"


def init_toggles() -> None:
    for key, default in _TOGGLE_DEFAULTS.items():
        st.session_state.setdefault(key, st.session_state.get(_pref_key(key), default))


def remember_toggles() -> None:
    """Call after the toggle widgets are drawn: keeps the choices for the next game."""
    for key in _TOGGLE_DEFAULTS:
        if key in st.session_state:
            st.session_state[_pref_key(key)] = st.session_state[key]


def new_game(seed: int) -> None:
    st.session_state["seed"] = seed
    params = replace(GAME_PARAMS, seed=seed)
    scenario = generate_scenario(params)
    st.session_state["game"] = GameSession(scenario, params)
    st.session_state["game_msg"] = None
    st.session_state["stage"] = "game"
    init_toggles()
    jobs = get_jobs()
    # Drops other seeds' jobs, every verdict (verdicts depend on the old game's deck) and any Lab
    # smart run still queued or running; finished Lab runs survive in `lab_smart_results`.
    jobs.forget_except(("smart", seed))
    jobs.submit(("smart", seed), smart_plan, scenario, params, ADVISOR_K)


def verdict_for(seed: int, index: int) -> Verdict | None:
    """The advisor's verdict on request `index` of the game with `seed`, None if not ready."""
    return get_jobs().result(("verdict", seed, index))


def submit_verdict(game: GameSession) -> None:
    """Queue the verdict on the current request; call it before the decision changes the deck."""
    if game.is_finished:
        return
    get_jobs().submit(("verdict", st.session_state["seed"], game.index), advise,
                      game.view_at_current(), ADVISOR_K)


def verdict_now(game: GameSession) -> Verdict:
    """The verdict on the current request, computed here if the background one isn't ready."""
    seed = st.session_state["seed"]
    verdict = verdict_for(seed, game.index)
    if verdict is None:
        with get_jobs().paused():  # don't share the CPU with the background smart run
            verdict = advise(game.view_at_current(), ADVISOR_K)
        get_jobs().put(("verdict", seed, game.index), verdict)
    return verdict


def get_session() -> GameSession:
    if "game" not in st.session_state:
        new_game(GAME_PARAMS.seed)
    return st.session_state["game"]


def get_stage() -> str:
    get_session()
    return st.session_state["stage"]


def set_stage(stage: str) -> None:
    st.session_state["stage"] = stage


@st.cache_data(show_spinner=False)
def benchmark_plans(params: ScenarioParams) -> tuple[Plan, Plan]:
    """FCFS and optimal plans for a scenario, cached by its parameters."""
    scenario = generate_scenario(params)
    return solve_fcfs(scenario), solve_optimal(scenario)


def reveal_best(seed: int, scenario, smart: Plan | None) -> Plan:
    """Best possible plan for the game of `seed`, seeded with the smart plan; cached by seed."""
    cache = st.session_state.setdefault("reveal_best", {})
    key = (seed, smart is not None)
    if key not in cache:
        cache[key] = solve_optimal(scenario, candidates=() if smart is None else (smart,))
    return cache[key]


def lab_smart_key(params: ScenarioParams) -> tuple:
    return ("lab_smart", params)


def lab_smart_result(params: ScenarioParams) -> Plan | None:
    """The Lab's smart plan for `params` once its job is done (kept across new games), else None."""
    done = st.session_state.setdefault("lab_smart_results", {})
    if params not in done:
        result = get_jobs().result(lab_smart_key(params))
        if result is None:
            return None
        done[params] = result[0]
    return done[params]


def submit_lab_smart(params: ScenarioParams) -> None:
    get_jobs().submit(lab_smart_key(params), smart_plan, generate_scenario(params), params, ADVISOR_K)


def lab_best_with_smart(params: ScenarioParams, smart: Plan) -> Plan:
    """The Lab's Best once the smart plan exists: the optimizer warm-started from it too."""
    cache = st.session_state.setdefault("lab_best_smart", {})
    if params not in cache:
        cache[params] = solve_optimal(generate_scenario(params), candidates=(smart,))
    return cache[params]
