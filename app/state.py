"""Session state helpers: the current game and which stage (game / reveal / lab) is shown."""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

from roro_yield.fcfs import solve_fcfs
from roro_yield.game import GameSession
from roro_yield.models import Plan
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams, generate_scenario

GAME_PARAMS = ScenarioParams()
STAGES = ("game", "reveal", "lab")


def new_game(seed: int) -> None:
    st.session_state["seed"] = seed
    params = replace(GAME_PARAMS, seed=seed)
    st.session_state["game"] = GameSession(generate_scenario(params), params)
    st.session_state["game_msg"] = None
    st.session_state["stage"] = "game"


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
