"""Plotly drawing of the vehicle deck: lanes as strips, units as blocks (stern left, bow right)."""

from __future__ import annotations

import plotly.graph_objects as go

from roro_yield.models import UNIT_LABELS, Plan, Scenario

# Validated categorical slots 1-2 (blue, orange) from the dataviz reference palette.
SEGMENT_COLORS = {"contract": "#2a78d6", "spot": "#eb6834"}
SEGMENT_NAMES = {"contract": "Contract", "spot": "Spot"}
LANE_FILL = "rgba(128, 128, 128, 0.12)"
LANE_LINE = "rgba(128, 128, 128, 0.45)"
LANE_HEIGHT = 0.8
UNIT_HEIGHT = 0.56


def deck_figure(scenario: Scenario, plan: Plan, title: str = "") -> go.Figure:
    vessel = scenario.vessel
    gap = vessel.lashing_gap_m
    lanes = vessel.lanes
    max_len = max((lane.length_m for lane in lanes), default=1.0)
    y_of = {lane.id: len(lanes) - i for i, lane in enumerate(lanes)}  # L1 on top

    fig = go.Figure()
    shapes = []
    for lane in lanes:
        y = y_of[lane.id]
        shapes.append(dict(
            type="rect", name=f"lane:{lane.id}", layer="below",
            x0=0, x1=lane.length_m, y0=y - LANE_HEIGHT / 2, y1=y + LANE_HEIGHT / 2,
            fillcolor=LANE_FILL, line=dict(color=LANE_LINE, width=1),
        ))

    cursor = {lane.id: 0.0 for lane in lanes}
    hover = {seg: {"x": [], "y": [], "text": [], "label": []} for seg in SEGMENT_COLORS}
    for booking_id, lane_id in plan.placements.items():
        b = scenario.booking(booking_id)
        x0 = cursor[lane_id]
        x1 = x0 + b.length_m
        cursor[lane_id] = x0 + b.effective_length(gap)
        y = y_of[lane_id]
        shapes.append(dict(
            type="rect", name=f"unit:{b.id}@{lane_id}",
            x0=x0, x1=x1, y0=y - UNIT_HEIGHT / 2, y1=y + UNIT_HEIGHT / 2,
            fillcolor=SEGMENT_COLORS[b.segment], line=dict(width=0),
        ))
        h = hover[b.segment]
        h["x"].append((x0 + x1) / 2)
        h["y"].append(y)
        h["label"].append("❄" if b.is_reefer else "")
        h["text"].append(
            f"<b>{b.id}</b> · {b.customer}<br>{UNIT_LABELS.get(b.unit_type, b.unit_type)}, "
            f"{b.length_m:.1f} m, {b.weight_t:.1f} t{' · reefer' if b.is_reefer else ''}"
            f"<br>€{b.rate_per_m:.0f}/m · margin €{b.margin:,.0f}"
        )

    for seg, h in hover.items():
        if not h["x"]:
            continue
        fig.add_trace(go.Scatter(
            x=h["x"], y=h["y"], mode="markers+text", name=SEGMENT_NAMES[seg],
            text=h["label"], textfont=dict(color="white", size=12), hovertext=h["text"], hoverinfo="text",
            marker=dict(size=14, color=SEGMENT_COLORS[seg], opacity=0, symbol="square"),
            showlegend=True,
        ))

    fig.update_layout(
        title=dict(text=title),
        shapes=shapes,
        height=60 * len(lanes) + 80,
        margin=dict(l=40, r=20, t=40 if title else 10, b=30),
        xaxis=dict(range=[-1, max_len + 1], title="metres from stern → bow", showgrid=False, zeroline=False),
        yaxis=dict(
            range=[0.4, len(lanes) + 0.6], showgrid=False, zeroline=False,
            tickvals=list(y_of.values()), ticktext=list(y_of.keys()),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title_text="❄ = reefer  "),
        hoverlabel=dict(align="left"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
