"""Terminal loading manifest: what goes in which lane, in loading order."""

from __future__ import annotations

import pandas as pd

from .models import Plan, Scenario

MANIFEST_COLUMNS = [
    "lane", "position", "booking_id", "customer", "segment", "unit_type", "length_m", "weight_t", "reefer",
]


def manifest_dataframe(scenario: Scenario, plan: Plan) -> pd.DataFrame:
    lane_order = {lane.id: i for i, lane in enumerate(scenario.vessel.lanes)}
    rows = []
    position: dict[str, int] = {}
    for booking_id, lane_id in plan.placements.items():
        b = scenario.booking(booking_id)
        position[lane_id] = position.get(lane_id, 0) + 1
        rows.append([lane_id, position[lane_id], b.id, b.customer, b.segment, b.unit_type,
                     b.length_m, b.weight_t, b.is_reefer])
    df = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    if df.empty:
        return df
    df = df.sort_values(["lane", "position"], key=lambda col: col.map(lane_order) if col.name == "lane" else col)
    return df.reset_index(drop=True)


def manifest_csv(scenario: Scenario, plan: Plan) -> bytes:
    return manifest_dataframe(scenario, plan).to_csv(index=False).encode("utf-8")
