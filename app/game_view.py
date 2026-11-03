"""Stage 1: the player is the booking planner."""

from __future__ import annotations

import time

import streamlit as st

from app.deck_chart import SEGMENT_COLORS, deck_figure
from app.stability_view import ship_figure, stability_gauges
from app.state import (
    ADVISOR_TOGGLE_LABEL,
    PLACEMENT_MODES,
    get_session,
    init_toggles,
    set_stage,
    submit_verdict,
    verdict_now,
)
from roro_yield.models import UNIT_LABELS, ZONES, Slot

ZONE_NAMES = ("stern", "aft-mid", "fore-mid", "bow")


def _manual() -> bool:
    return st.session_state.get("placement_mode") == "manual"


def _after_decision(game, msg: str | None) -> None:
    st.session_state["game_msg"] = msg
    if game.is_finished:
        set_stage("reveal")


def _accept(expected_index: int) -> None:
    game = get_session()
    submit_verdict(game)  # before the decision: the verdict depends on the deck as it is now
    if _manual():
        _after_decision(game, game.request_accept(expected_index))
    else:
        _after_decision(game, game.accept(expected_index))


def _reject(expected_index: int) -> None:
    game = get_session()
    submit_verdict(game)
    game.reject(expected_index)
    _after_decision(game, None)


def _confirm(expected_index: int, slot: Slot) -> None:
    game = get_session()
    submit_verdict(game)
    _after_decision(game, game.confirm_slot(expected_index, slot))


def _cancel() -> None:
    get_session().cancel_pending()
    st.session_state["game_msg"] = None


def _mode_changed() -> None:
    _cancel()  # a zone choice pending under the old mode is dropped; nothing gets placed


def _parse_slot(slot_id) -> Slot | None:
    lane_id, sep, zone = str(slot_id).rpartition("-Z")
    if not sep or not zone.isdigit():
        return None
    return Slot(lane_id, int(zone))


def _chart_pick(expected_index: int, chart_key: str) -> None:
    """on_select callback of the deck chart: confirm the first clicked point that is a zone."""
    state = st.session_state.get(chart_key)
    try:
        points = state["selection"]["points"]
    except (KeyError, TypeError):
        return
    for point in points:
        custom = point.get("customdata")
        if isinstance(custom, (list, tuple)):
            custom = custom[0] if custom else None
        slot = _parse_slot(custom) if custom else None  # unit / legend points carry no customdata
        if slot is not None:
            _confirm(expected_index, slot)
            return


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
        if st.session_state.get("advisor_on"):
            started = time.perf_counter()
            with st.spinner("💡 The advisor is playing out possible futures…"):
                verdict = verdict_now(game)
            st.session_state["advisor_last_s"] = time.perf_counter() - started
            st.markdown(f"💡 **Advisor:** {verdict.text}")
        if game.pending_index == game.index:
            st.markdown("**Pick a green zone** on the deck, or use the zone buttons under it.")
            c, r = st.columns(2)
            c.button("Cancel", key="cancel_pending", width="stretch", on_click=_cancel)
        else:
            a, r = st.columns(2)
            a.button("✓ Accept → pick a zone" if _manual() else "✓ Accept", key="accept", type="primary",
                     width="stretch", on_click=_accept, args=(game.index,))
        r.button("✗ Reject", key="reject", width="stretch", on_click=_reject, args=(game.index,))

    msg = st.session_state.get("game_msg")
    if msg:
        st.warning(f"Can't load it: {msg}. Reject it to continue.")
    if game.contract_floor_at_risk():
        penalty = game.scenario.shortfall_penalty_per_m
        st.info(f"Contract guarantee at risk: every missing contract metre costs a €{penalty:,.0f}/m penalty.")


def _zone_buttons(game, slots: list[Slot]) -> None:
    """Fallback for chart clicks: one small button per feasible zone, keys slot_<lane>_<zone>."""
    feasible = set(slots)
    st.caption("Or pick a zone here:")
    for lane in sorted(game.scenario.vessel.lanes, key=lambda lane: lane.y_m):  # port first, like the chart
        zones = [z for z in range(ZONES) if Slot(lane.id, z) in feasible]
        if not zones:
            continue
        cols = st.columns([1] + [2] * ZONES)
        cols[0].markdown(f"**{lane.id}**")
        for z in zones:
            cols[z + 1].button(ZONE_NAMES[z] if z < len(ZONE_NAMES) else f"Z{z}",
                               key=f"slot_{lane.id}_{z}", width="stretch",
                               on_click=_confirm, args=(game.index, Slot(lane.id, z)))


def _deck(game) -> None:
    s = game.scenario
    if game.pending_index == game.index and not game.is_finished:
        slots = game.deck.feasible_slots(game.current)
        index = game.index
        chart_key = f"game_deck_pick_{index}"  # a fresh key per request: no stale selection carries over
        st.plotly_chart(
            deck_figure(s, game.to_plan(), highlight=slots), key=chart_key,
            on_select=lambda: _chart_pick(index, chart_key), selection_mode="points",
        )
        st.caption("Green zones = where this unit fits. Click one to load it there.")
        _zone_buttons(game, slots)
    else:
        st.plotly_chart(deck_figure(s, game.to_plan()), key="game_deck")


def _stability(game) -> None:
    v = game.scenario.vessel
    deck = game.deck
    ballast = deck.ballast
    st.markdown("#### Stability")
    a, b = st.columns([1, 2], gap="medium")
    with a:
        stability_gauges(deck.heel_deg, deck.trim_m, ballast.total_t, v.stability, v.max_dwt_t)
    b.plotly_chart(ship_figure(deck.heel_deg, deck.trim_m, ballast, tank_cap_t=v.stability.tank_cap_t),
                   key="game_ship")


def _toggles() -> None:
    a, b = st.columns([3, 1])
    a.radio("Placement", options=list(PLACEMENT_MODES), format_func=PLACEMENT_MODES.get,
            key="placement_mode", horizontal=True, label_visibility="collapsed", on_change=_mode_changed)
    b.toggle(ADVISOR_TOGGLE_LABEL, key="advisor_on")


def render() -> None:
    game = get_session()
    init_toggles()
    s = game.scenario
    st.subheader(f"① You are the planner · {s.vessel.name}, {s.vessel.route}")
    st.markdown(
        f"{len(game.queue)} booking requests arrive one by one for tomorrow's sailing. "
        "Accept or reject each one. Contract cargo pays less but is guaranteed to key accounts; "
        "spot cargo pays more but arrives later. The ship can't hold everything."
    )
    _toggles()
    left, right = st.columns([2, 1], gap="large")
    with left:
        _gauges(game)
        _deck(game)
        _stability(game)
    with right:
        _request_card(game)
