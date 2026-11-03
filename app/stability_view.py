"""Stability visuals: heel/trim/ballast gauges (Streamlit) and tilting ship pictures (Plotly)."""

from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from roro_yield.models import Stability
from roro_yield.stability import Ballast

VISUAL_EXAGGERATION = 4
TRIM_ARM_M = 30.0  # schematic arm turning trim metres into a drawn angle
HULL_FILL = "rgba(136, 136, 136, 0.85)"
HOUSE_FILL = "rgba(170, 170, 170, 0.9)"
WATER_LINE = "#58a6ff"
BALLAST_FILL = "rgba(102, 204, 204, 0.85)"
TANK_LINE = "rgba(128, 128, 128, 0.9)"

_METER_BG = (
    "linear-gradient(90deg,#d73a49 0 16.7%,#e3b341 16.7% 33.3%,#2da44e 33.3% 66.7%,"
    "#e3b341 66.7% 83.3%,#d73a49 83.3%)"
)


def _meter(value: float, limit: float) -> str:
    """Bar spanning +-1.5 x limit: green inside 50% of the limit, amber to 100%, red beyond."""
    frac = 0.5 if limit <= 0 else 0.5 + max(-1.0, min(1.0, value / (1.5 * limit))) * 0.5
    return (
        f'<div style="position:relative;height:14px;background:{_METER_BG};border-radius:7px;margin:4px 0 12px">'
        f'<div style="position:absolute;top:-3px;left:calc({frac * 100:.1f}% - 1.5px);width:3px;height:20px;'
        'background:#888;border:1px solid #fff"></div></div>'
    )


def stability_gauges(
    heel_deg: float, trim_m: float, ballast_t: float, stab: Stability, max_dwt_t: float
) -> None:
    heel_side = "to starboard" if heel_deg > 0 else "to port"
    trim_side = "by the bow" if trim_m > 0 else "by the stern"
    st.markdown(
        f"**Heel** (left/right): {abs(heel_deg):.1f}° {heel_side} (limit {stab.max_heel_deg:.1f}°)"
        + _meter(heel_deg, stab.max_heel_deg),
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**Trim** (bow/stern): {abs(trim_m):.2f} m {trim_side} (limit {stab.max_trim_m:.2f} m)"
        + _meter(trim_m, stab.max_trim_m),
        unsafe_allow_html=True,
    )
    share = 0.0 if max_dwt_t <= 0 else ballast_t / max_dwt_t
    st.markdown(f"**Ballast needed**: {ballast_t:.0f} t ({share:.1%} of sellable deadweight)")
    st.progress(max(0.0, min(1.0, share)))


def _rotate(pts: list[tuple[float, float]], deg: float, cx: float, cy: float) -> tuple[list[float], list[float]]:
    """Rotate points counter-clockwise by `deg` about (cx, cy); close the polygon."""
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    xs = [cx + (x - cx) * c - (y - cy) * s for x, y in pts]
    ys = [cy + (x - cx) * s + (y - cy) * c for x, y in pts]
    return xs + xs[:1], ys + ys[:1]


def _rect(x0: float, x1: float, y0: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def ship_figure(heel_deg: float, trim_m: float, ballast: Ballast, tank_cap_t: float = 300.0) -> go.Figure:
    """Astern view (heel) and side view (trim); starboard right / bow right. Angles drawn x4."""
    heel_rot = -heel_deg * VISUAL_EXAGGERATION  # starboard down = clockwise
    trim_rot = -math.degrees(math.atan(trim_m / TRIM_ARM_M)) * VISUAL_EXAGGERATION  # bow down = clockwise
    heel_txt = f"heel {abs(heel_deg):.1f}° " + ("to starboard" if heel_deg > 0 else "to port")
    trim_txt = f"trim {abs(trim_m):.2f} m " + ("by the bow" if trim_m > 0 else "by the stern")

    fig = make_subplots(rows=1, cols=2, column_widths=[0.45, 0.55], horizontal_spacing=0.06,
                        subplot_titles=(f"Seen from astern: {heel_txt}", f"Seen from the side: {trim_txt}"))

    def add_poly(pts, deg, pivot, col, name, fill, outline=False):
        xs, ys = _rotate(pts, deg, *pivot)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", fill="toself", name=name, fillcolor=fill, hoverinfo="skip",
            line=dict(color=TANK_LINE if outline else fill, width=1), showlegend=False,
        ), row=1, col=col)

    def tank(x0, x1, y0, y1, tonnes, deg, pivot, col, name):
        frac = 0.0 if tank_cap_t <= 0 else max(0.0, min(1.0, tonnes / tank_cap_t))
        add_poly(_rect(x0, x1, y0, y0 + (y1 - y0) * frac), deg, pivot, col, name, BALLAST_FILL)
        add_poly(_rect(x0, x1, y0, y1), deg, pivot, col, name + "-outline", "rgba(0,0,0,0)", outline=True)

    # astern view
    pivot_a = (0.0, -5.0)
    add_poly([(-40, 10), (40, 10), (30, -20), (-30, -20)], heel_rot, pivot_a, 1, "hull-astern", HULL_FILL)
    add_poly(_rect(-25, 25, 10, 25), heel_rot, pivot_a, 1, "house-astern", HOUSE_FILL)
    tank(-28, -12, -17, 6, ballast.port_t, heel_rot, pivot_a, 1, "tank-port")
    tank(12, 28, -17, 6, ballast.stbd_t, heel_rot, pivot_a, 1, "tank-stbd")
    # side view (stern left, bow right)
    pivot_s = (0.0, -5.0)
    add_poly([(-60, 10), (60, 10), (72, 0), (56, -20), (-56, -20)], trim_rot, pivot_s, 2, "hull-side", HULL_FILL)
    add_poly(_rect(-50, -15, 10, 22), trim_rot, pivot_s, 2, "house-side", HOUSE_FILL)
    tank(-52, -38, -17, 6, ballast.aft_t, trim_rot, pivot_s, 2, "tank-aft")
    tank(38, 52, -17, 6, ballast.fore_t, trim_rot, pivot_s, 2, "tank-fore")

    for col, half in ((1, 55), (2, 85)):
        fig.add_trace(go.Scatter(x=[-half, half], y=[0, 0], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color=WATER_LINE, width=2), name="waterline"), row=1, col=col)
    fig.update_xaxes(visible=False, range=[-55, 55], row=1, col=1)
    fig.update_xaxes(visible=False, range=[-85, 85], row=1, col=2)
    fig.update_yaxes(visible=False, range=[-35, 45], scaleanchor="x", scaleratio=1, row=1, col=1)
    fig.update_yaxes(visible=False, range=[-35, 45], scaleanchor="x2", scaleratio=1, row=1, col=2)
    fig.add_annotation(
        text=f"angles exaggerated ×{VISUAL_EXAGGERATION}; ballast tanks shown filling (light blue)",
        xref="paper", yref="paper", x=0.5, y=-0.02, showarrow=False, font=dict(size=11),
    )
    fig.update_layout(
        height=240, margin=dict(l=10, r=10, t=40, b=30),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
