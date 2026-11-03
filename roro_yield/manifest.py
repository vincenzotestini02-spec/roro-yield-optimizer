"""Terminal loading manifest: what goes in which lane, in loading order."""

from __future__ import annotations

import pandas as pd

from .kpis import plan_ballast
from .models import Plan, Scenario

MANIFEST_COLUMNS = [
    "lane", "zone", "position", "booking_id", "customer", "segment", "unit_type", "length_m", "weight_t", "reefer",
]


def manifest_dataframe(scenario: Scenario, plan: Plan) -> pd.DataFrame:
    lane_order = {lane.id: i for i, lane in enumerate(scenario.vessel.lanes)}
    rows = []
    position: dict[str, int] = {}
    for booking_id, slot in plan.placements.items():
        lane_id = slot.lane_id
        b = scenario.booking(booking_id)
        position[lane_id] = position.get(lane_id, 0) + 1
        rows.append([lane_id, slot.zone, position[lane_id], b.id, b.customer, b.segment, b.unit_type,
                     b.length_m, b.weight_t, b.is_reefer])
    df = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    if not df.empty:
        df = df.sort_values(["lane", "position"], key=lambda col: col.map(lane_order) if col.name == "lane" else col)
    ballast, _ = plan_ballast(scenario, plan)
    tanks = [("port tank", ballast.port_t), ("starboard tank", ballast.stbd_t),
             ("fore tank", ballast.fore_t), ("aft tank", ballast.aft_t)]
    extra = [["BALLAST", None, None, "", "", "", name, 0.0, t, False] for name, t in tanks if t > 0]
    if extra:
        df = pd.concat([df, pd.DataFrame(extra, columns=MANIFEST_COLUMNS)], ignore_index=True)
    df = df.astype({"zone": "Int64", "position": "Int64"})  # ballast rows are blank, not 0.0
    return df.reset_index(drop=True)


def manifest_csv(scenario: Scenario, plan: Plan) -> bytes:
    return manifest_dataframe(scenario, plan).to_csv(index=False).encode("utf-8")
