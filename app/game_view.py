"""Stage 1: the player is the booking planner."""

from __future__ import annotations

import streamlit as st

from app.deck_chart import SEGMENT_COLORS, deck_figure
from app.state import get_session, set_stage
from roro_yield.models import UNIT_LABELS


def _accept(expected_index: int) -> None:
    game = get_session()
    st.session_state["game_msg"] = game.accept(expected_index)
    if game.is_finished:
        set_stage("reveal")


def _reject(expected_index: int) -> None:
    game = get_session()
    st.session_state["game_msg"] = None
    game.reject(expected_index)
    if game.is_finished:
        set_stage("reveal")


def _gauges(game) -> None:
    s = game.scenario
    v = s.vessel
    used_m = v.total_lane_m - sum(game.deck.remaining_m.values())
    contract_m = sum(s.booking(i).length_m for i in game.deck.placements if s.booking(i).segment == "contract")
    margin = sum(s.booking(i).margin for i in game.deck.placements)

    c1, c2, c3 = st.columns(3)
    c1.metric("Lane-metres used", f"{used_m:,.0f} / {v.total_lane_m:,.0f} m")
    c1.progress(min(used_m / v.total_lane_m, 1.0) if v.total_lane_m else 0.0)
    c2.metric("Deadweight", f"{game.deck.weight_t:,.0f} / {v.max_dwt_t:,.0f} t")
    c2.progress(min(game.deck.weight_t / v.max_dwt_t, 1.0) if v.max_dwt_t else 0.0)
    c3.metric("Reefer plugs", f"{game.deck.plugs_used} / {v.reefer_plugs}")
    c3.progress(min(game.deck.plugs_used / v.reefer_plugs, 1.0) if v.reefer_plugs else 0.0)

    c4, c5 = st.columns(2)
    c4.metric("Contract metres loaded", f"{contract_m:,.0f} / {s.contract_floor_m:,.0f} m guaranteed")
    c5.metric("Your margin so far", f"€{margin:,.0f}")


def _request_card(game) -> None:
    b = game.current
    n = len(game.queue)
    st.markdown(f"**Request {game.index + 1} of {n}**")
    st.progress(game.index / n)
    with st.container(border=True):
        color = SEGMENT_COLORS[b.segment]
        st.markdown(
            f"<span style='background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em'>"
            f"{'CONTRACT' if b.segment == 'contract' else 'SPOT'}</span> &nbsp; **{b.customer}**",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"### {UNIT_LABELS.get(b.unit_type, b.unit_type).capitalize()}{' ❄' if b.is_reefer else ''}\n"
            f"{b.length_m:.1f} m · {b.weight_t:.1f} t{' · needs a reefer plug' if b.is_reefer else ''}"
        )
        fee = f" + €{b.reefer_fee:.0f} plug fee" if b.is_reefer else ""
        st.markdown(f"Rate **€{b.rate_per_m:.0f}/m**{fee}  \nMargin if loaded: **€{b.margin:,.0f}**")
        a, r = st.columns(2)
        a.button("✓ Accept", key="accept", type="primary", width="stretch",
                 on_click=_accept, args=(game.index,))
        r.button("✗ Reject", key="reject", width="stretch", on_click=_reject, args=(game.index,))

    msg = st.session_state.get("game_msg")
    if msg:
        st.warning(f"Can't load it: {msg}. Reject it to continue.")
    if game.contract_floor_at_risk():
        penalty = game.scenario.shortfall_penalty_per_m
        st.info(f"Contract guarantee at risk: every missing contract metre costs a €{penalty:,.0f}/m penalty.")


def render() -> None:
    game = get_session()
    s = game.scenario
    st.subheader(f"① You are the planner · {s.vessel.name}, {s.vessel.route}")
    st.markdown(
        f"{len(game.queue)} booking requests arrive one by one for tomorrow's sailing. "
        "Accept or reject each one. Contract cargo pays less but is guaranteed to key accounts; "
        "spot cargo pays more but arrives later. The ship can't hold everything."
    )
    left, right = st.columns([2, 1], gap="large")
    with left:
        _gauges(game)
        st.plotly_chart(deck_figure(s, game.to_plan()), key="game_deck")
    with right:
        _request_card(game)
