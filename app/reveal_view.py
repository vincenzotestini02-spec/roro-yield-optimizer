"""Stage 2: how the player did against FCFS, the smart planner and the optimizer."""

from __future__ import annotations

import random

import pandas as pd
import streamlit as st

from app.deck_chart import deck_figure
from app.stability_view import ship_figure
from app.state import ADVISOR_K, get_jobs, get_session, new_game, reveal_best, set_stage
from roro_yield.advisor import SMART_LABEL, smart_plan
from roro_yield.explain import costly_decisions
from roro_yield.fcfs import FCFS_LABEL, solve_fcfs
from roro_yield.kpis import evaluate, plan_ballast, yield_delta_pct
from roro_yield.models import UNIT_LABELS
from roro_yield.optimizer import OPTIMAL_LABEL

POLL_S = 1.0  # how often the waiting fragments look at the background jobs
PENDING = "…"
TABLE_COLUMNS = ["#", "request", "you", "advisor", "futures", "expected gain", "✗"]


def _delta_label(value: float, baseline: float) -> str | None:
    d = yield_delta_pct(value, baseline)
    return None if d is None else f"{d:+.1f}% vs FCFS"


def _card(col, k, k_fcfs) -> None:
    with col.container(border=True):
        delta = None if k is k_fcfs else _delta_label(k.objective, k_fcfs.objective)
        st.metric(k.method, f"€{k.objective:,.0f}", delta=delta)
        st.caption(
            f"RevPAL €{k.revpal:,.1f}/lm · deck {k.deck_util_pct:.0f}% · "
            f"DWT {k.dwt_pct:.0f}% · {k.n_accepted} units"
            + (f" · contract shortfall {k.shortfall_m:,.0f} m (−€{k.penalty:,.0f})" if k.shortfall_m else "")
            + f" · ballast {k.ballast_t:,.0f} t (−€{k.ballast_cost:,.0f}) · heel {k.heel_deg:+.1f}° · "
            f"trim {k.trim_m:+.2f} m"
        )


def _waiting_card(col, label: str, note: str) -> None:
    with col.container(border=True):
        st.markdown(f"**{label}**")
        st.caption(note)


@st.fragment(run_every=POLL_S)
def _smart_progress(seed: int) -> None:
    """Shows the smart run's progress; reruns the whole page once it is done (or failed)."""
    jobs = get_jobs()
    key = ("smart", seed)
    if jobs.result(key) is not None or jobs.error(key) is not None or not jobs.has(key):
        st.rerun()
    frac = jobs.progress(key)
    st.progress(frac, text=f"The smart planner is playing the same requests without foresight… {frac:.0%}")


def _advisor_rows(game, seed: int) -> tuple[list[list], int]:
    jobs = get_jobs()
    actions = {booking_id: action for booking_id, action, _ in game.log}
    rows, pending = [], 0
    for i, b in enumerate(game.queue):
        you = {"accepted": "accept", "rejected": "reject"}.get(actions.get(b.id), "—")
        key = ("verdict", seed, i)
        v = jobs.result(key)
        if v is None and jobs.has(key) and jobs.error(key) is None:
            pending += 1
            advisor = futures = gain = PENDING
            mark = ""
        elif v is None:
            advisor, futures, gain, mark = "n/a", "", "", ""
        else:
            advisor = ("accept" if v.accept else "reject") + ("" if v.feasible else " (doesn't fit)")
            futures = f"{v.n_pays_off}/{v.k}" if v.feasible else ""
            gain = f"€{v.expected_gain_eur:,.0f}" if v.feasible else ""
            mark = "✗" if you in ("accept", "reject") and you != advisor.split()[0] else ""
        request = (f"{b.customer} · {UNIT_LABELS.get(b.unit_type, b.unit_type)} {b.length_m:.1f} m · "
                   f"€{b.rate_per_m:.0f}/m")
        rows.append([i + 1, request, you, advisor, futures, gain, mark])
    return rows, pending


def _advisor_table(rows: list[list]) -> None:
    st.dataframe(pd.DataFrame(rows, columns=TABLE_COLUMNS), hide_index=True, width="stretch")
    st.caption(f"✗ = you and the advisor disagreed · verdicts use K = {ADVISOR_K} sampled futures, "
               "knowing only the demand distribution, never the requests still to come.")


@st.fragment(run_every=POLL_S)
def _advisor_waiting(seed: int) -> None:
    rows, pending = _advisor_rows(get_session(), seed)
    if not pending:
        st.rerun()  # done: redraw the page without the polling fragment
    n = len(rows)
    st.progress((n - pending) / n if n else 1.0,
                text=f"The advisor is judging your decisions: {n - pending} of {n} verdicts ready")
    _advisor_table(rows)


def _advisor_section(game, seed: int) -> None:
    st.markdown("#### You vs the advisor, request by request")
    rows, pending = _advisor_rows(game, seed)
    if pending:
        _advisor_waiting(seed)
    else:
        _advisor_table(rows)


def render() -> None:
    game = get_session()
    s = game.scenario
    seed = st.session_state["seed"]
    jobs = get_jobs()
    smart_key = ("smart", seed)
    jobs.submit(smart_key, smart_plan, s, game.params, ADVISOR_K)  # no-op unless it was lost
    fcfs, you = solve_fcfs(s), game.to_plan()
    k_fcfs, k_you = evaluate(s, fcfs), evaluate(s, you)
    smart_result = jobs.result(smart_key)
    smart_failed = smart_result is None and jobs.error(smart_key) is not None

    st.subheader("② The ship has sailed. How did you do?")
    st.caption("Score = margin − contract-shortfall penalty − ballast cost. "
               "Same rules and same requests for all four.")
    cols = st.columns(4)
    _card(cols[0], k_fcfs, k_fcfs)
    _card(cols[1], k_you, k_fcfs)
    plans = [fcfs, you]
    best = None
    if smart_result is None and not smart_failed:
        _waiting_card(cols[2], SMART_LABEL, "Playing the sailing…")
        _waiting_card(cols[3], OPTIMAL_LABEL, "Waits for the smart planner.")
        _smart_progress(seed)
    else:
        smart = None if smart_failed else smart_result[0]
        with st.spinner("Computing the best possible plan…"):
            best = reveal_best(seed, s, smart)
        k_best = evaluate(s, best)
        if smart is None:
            _waiting_card(cols[2], SMART_LABEL, "Unavailable for this sailing.")
        else:
            _card(cols[2], evaluate(s, smart), k_fcfs)
            plans.append(smart)
        _card(cols[3], k_best, k_fcfs)
        plans.append(best)
    if yield_delta_pct(k_fcfs.objective, k_fcfs.objective) is None:
        st.caption("FCFS made no positive margin on this sailing, so % deltas are n/a.")

    tab_names = {FCFS_LABEL: "First come, first served deck", you.method: "Your deck",
                 SMART_LABEL: "Smart planner deck", OPTIMAL_LABEL: "Best possible deck"}
    tabs = st.tabs([tab_names.get(p.method, p.method) for p in plans])
    for i, (tab, plan) in enumerate(zip(tabs, plans)):
        with tab:
            st.plotly_chart(deck_figure(s, plan), key=f"reveal_deck_{i}")
            k = evaluate(s, plan)
            ballast, _ = plan_ballast(s, plan)
            st.plotly_chart(ship_figure(k.heel_deg, k.trim_m, ballast, tank_cap_t=s.vessel.stability.tank_cap_t),
                            key=f"reveal_ship_{i}")

    _advisor_section(game, seed)

    if best is not None:
        st.markdown("#### Where you lost the most")
        decisions = costly_decisions(s, you, best)
        if not decisions:
            st.success("You matched the best possible plan. Impressive!")
        for d in decisions:
            st.markdown(f"- **{d.booking_id}** · {d.reason}" if d.booking_id else f"- {d.reason}")

    a, b = st.columns(2)
    a.button("↻ Play another sailing", key="play_again", width="stretch",
             on_click=lambda: new_game(random.randint(1, 10_000)))
    b.button("Open the Lab →", key="to_lab", type="primary", width="stretch",
             on_click=set_stage, args=("lab",))
