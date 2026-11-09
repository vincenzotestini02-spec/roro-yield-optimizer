"""A plan as a PDF report. The CSV is the loading manifest from `roro_yield.manifest`."""

from __future__ import annotations

import io

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from roro_yield.kpis import evaluate
from roro_yield.manifest import manifest_dataframe
from roro_yield.models import ZONES, Plan, Scenario

DISCLAIMERS = ("Planning estimate, not a loading computer.", "Synthetic data, not DFDS data.")
SEGMENT_COLOURS = {"contract": colors.HexColor("#2563a8"), "spot": colors.HexColor("#c7681a")}
LANE_HEIGHT = 12
DECK_WIDTH = 250 * mm


def _deck_drawing(scenario: Scenario, plan: Plan) -> Drawing:
    vessel = scenario.vessel
    lanes = sorted(vessel.lanes, key=lambda lane: lane.y_m)
    longest = max(lane.length_m for lane in lanes)
    left = 24
    scale = (DECK_WIDTH - left) / longest
    height = len(lanes) * (LANE_HEIGHT + 3) + 14
    drawing = Drawing(DECK_WIDTH, height)
    drawing.add(String(left, height - 9, "Stern", fontSize=7))
    drawing.add(String(DECK_WIDTH - 20, height - 9, "Bow", fontSize=7))
    y_of = {}
    for i, lane in enumerate(lanes):
        y = height - 14 - (i + 1) * (LANE_HEIGHT + 3)
        y_of[lane.id] = y
        drawing.add(String(0, y + 3, lane.id, fontSize=7))
        drawing.add(Rect(left, y, lane.length_m * scale, LANE_HEIGHT, fillColor=colors.HexColor("#e9edef"),
                         strokeColor=colors.HexColor("#cfd8dc")))
        for z in range(1, ZONES):
            x = left + z * lane.zone_length_m * scale
            drawing.add(Line(x, y, x, y + LANE_HEIGHT, strokeColor=colors.HexColor("#9aa7ad"), strokeDashArray=[2, 2]))
    used: dict = {}
    for booking_id, slot in plan.placements.items():
        b = scenario.booking(booking_id)
        lane = vessel.lane(slot.lane_id)
        offset = used.get(slot, 0.0)
        used[slot] = offset + b.effective_length(vessel.lashing_gap_m)
        x = left + (slot.zone * lane.zone_length_m + offset) * scale
        drawing.add(Rect(x, y_of[slot.lane_id] + 2, b.length_m * scale, LANE_HEIGHT - 4,
                         fillColor=SEGMENT_COLOURS[b.segment], strokeColor=colors.white, strokeWidth=0.3))
    return drawing


def plan_pdf(scenario: Scenario, plan: Plan, title: str, assumptions: list[str]) -> bytes:
    styles = getSampleStyleSheet()
    k = evaluate(scenario, plan)
    vessel = scenario.vessel
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    kpis = [
        ["Score (margin − penalty − ballast)", f"€{k.objective:,.0f}", "Units loaded", str(k.n_accepted)],
        ["Revenue", f"€{k.revenue:,.0f}", "Deck utilisation", f"{k.deck_util_pct:.0f}%"],
        ["RevPAL", f"€{k.revpal:,.1f}/lm", "Deadweight used", f"{k.dwt_pct:.0f}%"],
        ["Contract shortfall", f"{k.shortfall_m:,.0f} m", "Ballast", f"{k.ballast_t:,.0f} t"],
        ["Heel", f"{k.heel_deg:+.1f}°", "Trim", f"{k.trim_m:+.2f} m"],
    ]
    kpi_table = Table(kpis, hAlign="LEFT")
    kpi_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9),
                                   ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                                   ("TEXTCOLOR", (2, 0), (2, -1), colors.grey)]))
    manifest = manifest_dataframe(scenario, plan).astype(object).fillna("")  # ballast rows have blank zones
    rows = [list(manifest.columns)] + [[str(v) for v in row] for row in manifest.itertuples(index=False)]
    manifest_table = Table(rows, repeatRows=1, hAlign="LEFT")
    manifest_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7),
                                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edef")),
                                        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfd8dc"))]))
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"{vessel.name} · {vessel.route} · {plan.method}", styles["Normal"]),
        Spacer(1, 4 * mm), kpi_table, Spacer(1, 4 * mm),
        _deck_drawing(scenario, plan),
        Paragraph("Blue = contract, orange = spot.", styles["Italic"]),
        Spacer(1, 3 * mm),
        Paragraph("Assumptions", styles["Heading3"]),
        *[Paragraph(f"• {line}", styles["Normal"]) for line in assumptions],
        *[Paragraph(f"<b>{line}</b>", styles["Normal"]) for line in DISCLAIMERS],
        Spacer(1, 4 * mm),
        Paragraph("Loading manifest", styles["Heading3"]),
        manifest_table,
    ]
    doc.build(story)
    return buffer.getvalue()
