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


def init_toggles() -> None:
    st.session_state.setdefault("placement_mode", "auto")
    st.session_state.setdefault("advisor_on", False)


def new_game(seed: int) -> None:
    st.session_state["seed"] = seed
    params = replace(GAME_PARAMS, seed=seed)
    scenario = generate_scenario(params)
    st.session_state["game"] = GameSession(scenario, params)
    st.session_state["game_msg"] = None
    st.session_state["stage"] = "game"
    init_toggles()
    jobs = get_jobs()
    # Drops other seeds' jobs and every verdict (verdicts depend on the old game's deck).
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
