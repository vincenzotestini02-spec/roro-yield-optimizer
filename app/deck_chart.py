"""Plotly drawing of the vehicle deck: lanes as strips, units as blocks (stern left, bow right)."""

from __future__ import annotations

import plotly.graph_objects as go

from typing import Sequence

from roro_yield.models import UNIT_LABELS, ZONES, Lane, Plan, Scenario, Slot

# Validated categorical slots 1-2 (blue, orange) from the dataviz reference palette.
SEGMENT_COLORS = {"contract": "#2a78d6", "spot": "#eb6834"}
SEGMENT_NAMES = {"contract": "Contract", "spot": "Spot"}
LANE_FILL = "rgba(128, 128, 128, 0.12)"
LANE_LINE = "rgba(128, 128, 128, 0.45)"
LANE_HEIGHT = 0.8
UNIT_HEIGHT = 0.56


HIGHLIGHT_FILL = "rgba(45, 164, 78, 0.28)"
HIGHLIGHT_LINE = "#2da44e"
ZONE_LINE = "rgba(128, 128, 128, 0.7)"


def _lane_label(lane: Lane) -> str:
    if abs(lane.y_m) < 1e-9:
        return f"{lane.id} C"
    return f"{lane.id} {'P' if lane.y_m < 0 else 'S'}"


def deck_figure(
    scenario: Scenario, plan: Plan, title: str = "", highlight: Sequence[Slot] = ()
) -> go.Figure:
    vessel = scenario.vessel
    gap = vessel.lashing_gap_m
    lanes = sorted(vessel.lanes, key=lambda lane: lane.y_m)  # port (top) -> starboard (bottom)
    max_len = max((lane.length_m for lane in lanes), default=1.0)
    y_of = {lane.id: len(lanes) - i for i, lane in enumerate(lanes)}

    fig = go.Figure()
    shapes = []
    for lane in lanes:
        y = y_of[lane.id]
        shapes.append(dict(
            type="rect", name=f"lane:{lane.id}", layer="below",
            x0=0, x1=lane.length_m, y0=y - LANE_HEIGHT / 2, y1=y + LANE_HEIGHT / 2,
            fillcolor=LANE_FILL, line=dict(color=LANE_LINE, width=1),
        ))
        for z in range(1, ZONES):
            x = z * lane.zone_length_m
            shapes.append(dict(
                type="line", name=f"zone:{lane.id}-Z{z}", layer="below",
                x0=x, x1=x, y0=y - LANE_HEIGHT / 2, y1=y + LANE_HEIGHT / 2,
                line=dict(color=ZONE_LINE, width=1, dash="dash"),
            ))

    hl_x, hl_y, hl_id = [], [], []
    for slot in highlight:
        lane = vessel.lane(slot.lane_id)
        y = y_of[lane.id]
        x0 = slot.zone * lane.zone_length_m
        shapes.append(dict(
            type="rect", name=f"highlight:{slot}", layer="below",
            x0=x0, x1=x0 + lane.zone_length_m, y0=y - LANE_HEIGHT / 2, y1=y + LANE_HEIGHT / 2,
            fillcolor=HIGHLIGHT_FILL, line=dict(color=HIGHLIGHT_LINE, width=2),
        ))
        hl_x.append(x0 + lane.zone_length_m / 2)
        hl_y.append(y)
        hl_id.append(str(slot))

    cursor = {slot: slot.zone * vessel.lane(slot.lane_id).zone_length_m for slot in vessel.slots}
    hover = {seg: {"x": [], "y": [], "text": [], "label": []} for seg in SEGMENT_COLORS}
    for booking_id, slot in plan.placements.items():
        b = scenario.booking(booking_id)
        x0 = cursor[slot]
        x1 = x0 + b.length_m
        cursor[slot] = x0 + b.effective_length(gap)
        y = y_of[slot.lane_id]
        shapes.append(dict(
            type="rect", name=f"unit:{b.id}@{slot}", layer="below",
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
        # Invisible markers carry the hover text and reefer labels; the legend gets a solid swatch.
        fig.add_trace(go.Scatter(
            x=h["x"], y=h["y"], mode="markers+text", name=SEGMENT_NAMES[seg], legendgroup=seg,
            text=h["label"], textfont=dict(color="white", size=13), hovertext=h["text"], hoverinfo="text",
            marker=dict(size=18, color="rgba(0,0,0,0)", symbol="square"), showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=SEGMENT_NAMES[seg], legendgroup=seg,
            marker=dict(size=12, color=SEGMENT_COLORS[seg], symbol="square"), hoverinfo="skip",
        ))

    if hl_x:
        # One invisible clickable marker per highlighted slot; customdata is the slot id ("L3-Z2").
        fig.add_trace(go.Scatter(
            x=hl_x, y=hl_y, mode="markers", name="Free zones", showlegend=False,
            customdata=hl_id, hoverinfo="none",
            marker=dict(size=34, color="rgba(0,0,0,0)", symbol="square"),
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
        ))

    fig.update_layout(
        title=dict(text=title),
        shapes=shapes,
        height=60 * len(lanes) + 80,
        margin=dict(l=40, r=20, t=40 if title else 10, b=30),
        xaxis=dict(range=[-1, max_len + 1], title="metres from stern → bow", showgrid=False, zeroline=False),
        yaxis=dict(
            range=[0.4, len(lanes) + 0.6], showgrid=False, zeroline=False,
            tickvals=list(y_of.values()), ticktext=[_lane_label(lane) for lane in lanes],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title_text="❄ = reefer  "),
        hoverlabel=dict(align="left"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
