"""Regression tests for the stage 2 review findings."""

import io
import time

from openpyxl import Workbook

from tests.api.tests_planner_helpers import planner_state


def stale(state):
    return {**state, "vessel": {"preset": "custom", "n_lanes": 4}, "placements": {"B001": "L8-Z0"}}


def test_move_with_placements_from_another_vessel_is_409_not_500(client):
    body = {**stale(planner_state(5)), "booking_id": "B002", "slot": "L1-Z0"}
    r = client.post("/api/planner/move", json=body)
    assert r.status_code == 409 and "plan again" in r.json()["detail"].lower()


def test_advise_with_stale_placements_is_409_not_500(client):
    request = {"booking_id": "NEW1", "customer": "X", "unit_type": "van", "length_m": 6.5, "weight_t": 3,
               "discharge_port": "Imm", "rate_per_m": 90}
    body = {**stale(planner_state(5)), "request": request, "demand": {"level": "normal"}}
    assert client.post("/api/planner/advise", json=body).status_code == 409


def test_export_with_stale_placements_is_409_not_500(client):
    r = client.post("/api/export/csv", json={"source": "planner", "plan_key": "planner", "state": stale(planner_state(5))})
    assert r.status_code == 409


def test_on_board_from_excel_without_a_zone_is_planned_with_a_warning(client, wait):
    state = planner_state(5)
    state["bookings"][0]["on_board"] = True
    job = client.post("/api/planner/plan", json=state)
    assert job.status_code == 200, job.text
    result = wait(client, job.json()["job_id"], timeout=60)["result"]
    assert "B001" in result["placements"]
    assert any("B001" in w and "no zone" in w for w in result["warnings"])


def test_a_huge_sparse_sheet_is_refused_quickly(client):
    wb = Workbook()
    ws = wb.active
    ws.append(["booking_id", "customer", "unit_type", "length_m", "weight_t", "discharge_port"])
    ws.cell(row=1_000_000, column=16_000, value="x")
    out = io.BytesIO()
    wb.save(out)
    start = time.perf_counter()
    r = client.post("/api/planner/import", files={"file": ("big.xlsx", out.getvalue())})
    assert r.status_code == 200 and r.json()["errors"][0]["row"] == 0
    assert time.perf_counter() - start < 10
