"""Stage 3: change the rules and watch FCFS vs the optimizer."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.deck_chart import SEGMENT_COLORS, SEGMENT_NAMES, deck_figure
from app.state import benchmark_plans
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
    lane_len = st.slider("Lane length (m)", 12.0, 250.0, d.lane_length_m, 1.0, key="lab_lane_len")
    dwt = st.slider("Max cargo deadweight (t)", 10.0, 5000.0, d.max_dwt_t, 10.0, key="lab_dwt")
    plugs = st.slider("Reefer plugs", 0, 40, d.reefer_plugs, key="lab_plugs")
    gap = st.slider("Lashing gap between units (m)", 0.0, 1.5, d.lashing_gap_m, 0.1, key="lab_gap")
    seed = st.number_input("Random seed", 1, 10_000, d.seed, key="lab_seed")
    return ScenarioParams(
        n_requests=n, contract_share=share, n_lanes=lanes, lane_length_m=lane_len, max_dwt_t=dwt,
        reefer_plugs=plugs, lashing_gap_m=gap, contract_floor_share=floor, spot_rate_multiplier=spot,
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


def render() -> None:
    st.subheader("③ The Lab: change the rules")
    st.markdown("Move the sliders and see how much an optimizer earns over first-come-first-served.")
    controls, results = st.columns([1, 3], gap="large")
    with controls:
        params = _controls()
    scenario = generate_scenario(params)
    with st.spinner("Optimising…"):
        fcfs, best = benchmark_plans(params)
    k_fcfs, k_best = evaluate(scenario, fcfs), evaluate(scenario, best)

    with results:
        delta = yield_delta_pct(k_best.objective, k_fcfs.objective)
        c1, c2, c3 = st.columns(3)
        c1.metric("Optimizer gain vs FCFS", "n/a" if delta is None else f"{delta:+.1f}%")
        c2.metric("Extra margin per sailing", f"€{k_best.objective - k_fcfs.objective:,.0f}")
        c3.metric("RevPAL (best possible)", f"€{k_best.revpal:,.1f}/lm",
                  delta=f"{k_best.revpal - k_fcfs.revpal:+.1f} vs FCFS")

        table = pd.DataFrame({
            k.method: {
                "Score (margin − penalty), €": f"{k.objective:,.0f}",
                "Revenue, €": f"{k.revenue:,.0f}",
                "RevPAL, €/lm": f"{k.revpal:,.1f}",
                "Deck utilisation": f"{k.deck_util_pct:.0f}%",
                "Deadweight used": f"{k.dwt_pct:.0f}%",
                "Reefer plugs used": f"{k.plugs_used}",
                "Units loaded": f"{k.n_accepted}",
                "Contract shortfall, m": f"{k.shortfall_m:,.0f}",
            }
            for k in (k_fcfs, k_best)
        })
        st.dataframe(table, width="stretch")
        st.plotly_chart(deck_figure(scenario, best, title="Best possible deck"), key="lab_deck")
        st.plotly_chart(_metres_by_segment(scenario, (fcfs, best)), key="lab_bars")
        st.download_button(
            "Download loading manifest (CSV)", manifest_csv(scenario, best), "manifest.csv", "text/csv",
            key="manifest",
        )
