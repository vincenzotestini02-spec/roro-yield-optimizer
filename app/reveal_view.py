"""Stage 2: how the player did against FCFS and the optimizer."""

from __future__ import annotations

import random

import streamlit as st

from app.deck_chart import deck_figure
from app.state import benchmark_plans, get_session, new_game, set_stage
from roro_yield.explain import costly_decisions
from roro_yield.kpis import evaluate, yield_delta_pct
from roro_yield.simulator import ScenarioParams


def _delta_label(value: float, baseline: float) -> str | None:
    d = yield_delta_pct(value, baseline)
    return None if d is None else f"{d:+.1f}% vs FCFS"


def render() -> None:
    game = get_session()
    s = game.scenario
    seed = st.session_state["seed"]
    with st.spinner("Computing the best possible plan…"):
        fcfs, best = benchmark_plans(ScenarioParams(seed=seed))
    you = game.to_plan()
    k_fcfs, k_you, k_best = (evaluate(s, p) for p in (fcfs, you, best))

    st.subheader("② The ship has sailed. How did you do?")
    st.caption("Score = margin − contract-shortfall penalty. Same rules and same requests for all three.")
    cols = st.columns(3)
    for col, k in zip(cols, (k_fcfs, k_you, k_best)):
        with col.container(border=True):
            delta = None if k is k_fcfs else _delta_label(k.objective, k_fcfs.objective)
            st.metric(k.method, f"€{k.objective:,.0f}", delta=delta if delta else None)
            st.caption(
                f"RevPAL €{k.revpal:,.1f}/lm · deck {k.deck_util_pct:.0f}% · "
                f"DWT {k.dwt_pct:.0f}% · {k.n_accepted} units"
                + (f" · contract shortfall {k.shortfall_m:,.0f} m (−€{k.penalty:,.0f})" if k.shortfall_m else "")
            )
    if yield_delta_pct(k_fcfs.objective, k_fcfs.objective) is None:
        st.caption("FCFS made no positive margin on this sailing, so % deltas are n/a.")

    tabs = st.tabs(["Your deck", "Best possible deck", "First come, first served deck"])
    for tab, plan, key in zip(tabs, (you, best, fcfs), ("deck_you", "deck_best", "deck_fcfs")):
        with tab:
            st.plotly_chart(deck_figure(s, plan), key=key)

    st.markdown("#### Where you lost the most")
    decisions = costly_decisions(s, you, best)
    if not decisions:
        st.success("You matched the best possible plan. Impressive!")
    for d in decisions:
        st.markdown(f"- **{d.booking_id}** · {d.reason}")

    a, b = st.columns(2)
    a.button("↻ Play another sailing", key="play_again", width="stretch",
             on_click=lambda: new_game(random.randint(1, 10_000)))
    b.button("Open the Lab →", key="to_lab", type="primary", width="stretch",
             on_click=set_stage, args=("lab",))
