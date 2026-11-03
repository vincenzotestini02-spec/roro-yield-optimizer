"""Stage 3: change the rules and watch FCFS vs the optimizer."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.deck_chart import SEGMENT_COLORS, SEGMENT_NAMES, deck_figure
from app.state import (
    ADVISOR_K,
    benchmark_plans,
    get_jobs,
    lab_best_with_smart,
    lab_smart_key,
    lab_smart_result,
    submit_lab_smart,
)
from roro_yield.kpis import evaluate, yield_delta_pct
from roro_yield.manifest import manifest_csv
from roro_yield.simulator import ScenarioParams, generate_scenario


def _controls() -> ScenarioParams:
    d = ScenarioParams()
    st.markdown("**Demand**")
    n = st.slider("Booking requests", 30, 200, d.n_requests, key="lab_n_requests")
    share = st.slider("Contract share of requests", 0.0, 0.9, d.contract_share, 0.05, key="lab_contract_share")
    spot = st.slider("Spot price level (×)", 0.7, 1.5, d.spot_rate_multiplier, 0.05, key="lab_spot")
    floor = st.slider("Guaranteed contract metres (% of deck)", 0.0, 0.8, d.contract_floor_share, 0.05,
                      key="lab_floor")
    st.markdown("**Vessel**")
    lanes = st.slider("Lanes", 1, 16, d.n_lanes, key="lab_n_lanes")
    lane_len = st.slider("Lane length (m)", 70.0, 250.0, d.lane_length_m, 1.0, key="lab_lane_len")
    dwt = st.slider("Max cargo deadweight (t)", 10.0, 5000.0, d.max_dwt_t, 10.0, key="lab_dwt")
    plugs = st.slider("Reefer plugs", 0, 40, d.reefer_plugs, key="lab_plugs")
    gap = st.slider("Lashing gap between units (m)", 0.0, 1.5, d.lashing_gap_m, 0.1, key="lab_gap")
    st.markdown("**Stability**")
    heel = st.slider("Max heel (°)", 0.5, 5.0, d.max_heel_deg, 0.1, key="lab_heel")
    trim = st.slider("Max trim (m)", 0.1, 2.0, d.max_trim_m, 0.05, key="lab_trim")
    tank = st.slider("Ballast tank capacity (t per tank)", 0.0, 600.0, d.ballast_tank_cap_t, 10.0, key="lab_tank")
    ballast_cost = st.slider("Ballast cost (€/t)", 0.0, 30.0, d.ballast_cost_per_t, 0.5, key="lab_ballast_cost")
    seed = st.number_input("Random seed", 1, 10_000, d.seed, key="lab_seed")
    return ScenarioParams(
        n_requests=n, contract_share=share, n_lanes=lanes, lane_length_m=lane_len, max_dwt_t=dwt,
        reefer_plugs=plugs, lashing_gap_m=gap, contract_floor_share=floor, spot_rate_multiplier=spot,
        max_heel_deg=heel, max_trim_m=trim, ballast_tank_cap_t=tank, ballast_cost_per_t=ballast_cost,
        seed=int(seed),
    )


def _metres_by_segment(scenario, plans) -> go.Figure:
    fig = go.Figure()
    for seg in ("contract", "spot"):
        fig.add_trace(go.Bar(
            name=SEGMENT_NAMES[seg], x=[p.method for p in plans], marker_color=SEGMENT_COLORS[seg],
            y=[sum(scenario.booking(i).length_m for i in p.placements if scenario.booking(i).segment == seg)
               for p in plans],
            hovertemplate="%{x}<br>" + SEGMENT_NAMES[seg] + ": %{y:,.0f} m<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack", height=320, title="Lane-metres sold, by segment", yaxis_title="metres",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"), margin=dict(l=40, r=20, t=60, b=30),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


@st.fragment(run_every=1.0)
def _smart_progress(params: ScenarioParams) -> None:
    """Progress of the Lab's smart run; reruns the page once it is done, failed or dropped."""
    jobs = get_jobs()
    key = lab_smart_key(params)
    if jobs.result(key) is not None or jobs.error(key) is not None or not jobs.has(key):
        st.rerun()
    frac = jobs.progress(key)
    note = "" if frac else " (queued behind the game's background run)"
    st.progress(frac, text=f"The smart planner is playing this sailing… {frac:.0%}{note}")


def _smart_controls(params: ScenarioParams):
    """The smart plan if it has run for these parameters; otherwise its button or progress bar."""
    smart = lab_smart_result(params)
    if smart is not None:
        return smart
    jobs = get_jobs()
    key = lab_smart_key(params)
    if jobs.error(key) is not None:  # a known key can't be resubmitted
        st.warning("The smart planner failed on these settings. Change a setting to try again.")
    elif jobs.has(key):
        _smart_progress(params)
    else:
        st.button(f"Run the smart planner (K = {ADVISOR_K} futures per request)", key="lab_run_smart",
                  on_click=submit_lab_smart, args=(params,))
    return None


def render() -> None:
    st.subheader("③ The Lab: change the rules")
    st.markdown("Move the sliders and see how much an optimizer earns over first-come-first-served.")
    controls, results = st.columns([1, 3], gap="large")
    with controls:
        params = _controls()
    scenario = generate_scenario(params)
    with st.spinner("Optimising…"):
        fcfs, best = benchmark_plans(params)

    with results:
        smart = _smart_controls(params)
        if smart is not None:
            with st.spinner("Re-optimising with the smart plan as a starting point…"):
                best = lab_best_with_smart(params, smart)
        k_fcfs, k_best = evaluate(scenario, fcfs), evaluate(scenario, best)
        shown = [fcfs] + ([smart] if smart is not None else []) + [best]

        delta = yield_delta_pct(k_best.objective, k_fcfs.objective)
        c1, c2, c3 = st.columns(3)
        c1.metric("Optimizer gain vs FCFS", "n/a" if delta is None else f"{delta:+.1f}%")
        c2.metric("Extra margin per sailing", f"€{k_best.objective - k_fcfs.objective:,.0f}")
        c3.metric("RevPAL (best possible)", f"€{k_best.revpal:,.1f}/lm",
                  delta=f"{k_best.revpal - k_fcfs.revpal:+.1f} vs FCFS")

        table = pd.DataFrame({
            k.method: {
                "Score (margin − penalty − ballast), €": f"{k.objective:,.0f}",
                "Revenue, €": f"{k.revenue:,.0f}",
                "RevPAL, €/lm": f"{k.revpal:,.1f}",
                "Deck utilisation": f"{k.deck_util_pct:.0f}%",
                "Deadweight used": f"{k.dwt_pct:.0f}%",
                "Reefer plugs used": f"{k.plugs_used}",
                "Units loaded": f"{k.n_accepted}",
                "Contract shortfall, m": f"{k.shortfall_m:,.0f}",
                "Ballast, t": f"{k.ballast_t:,.0f}",
                "Heel, °": f"{k.heel_deg:+.1f}",
                "Trim, m": f"{k.trim_m:+.2f}",
            }
            for k in (evaluate(scenario, p) for p in shown)
        })
        st.dataframe(table, width="stretch")
        st.plotly_chart(deck_figure(scenario, best, title="Best possible deck"), key="lab_deck")
        st.plotly_chart(_metres_by_segment(scenario, shown), key="lab_bars")
        st.download_button(
            "Download loading manifest (CSV)", manifest_csv(scenario, best), "manifest.csv", "text/csv",
            key="manifest",
        )
