import time

import pytest

from roro_yield.simulator import ScenarioParams, generate_scenario


def planner_bookings(n: int, seed: int = 7, prices: bool = True) -> list[dict]:
    s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=n, seed=seed))
    return [{
        "booking_id": b.id, "customer": b.customer, "unit_type": b.unit_type, "length_m": b.length_m,
        "weight_t": b.weight_t, "discharge_port": "Immingham", "segment": b.segment, "is_reefer": b.is_reefer,
        "rate_per_m": round(b.rate_per_m, 2) if prices else None,
    } for b in s.bookings]


def state(n=30, placements=None, prices=True, **vessel):
    return {"vessel": {"preset": "demo", **vessel}, "bookings": planner_bookings(n, prices=prices),
            "placements": placements or {}}


def plan(client, wait, body, timeout=60):
    job = client.post("/api/planner/plan", json=body)
    assert job.status_code == 200, job.text
    result = wait(client, job.json()["job_id"], timeout=timeout)
    assert result["status"] == "done", result
    return result["result"]


DEMAND = {"level": "high", "contract_share": 0.45, "spot_rate_multiplier": 1.0, "window_days": 14,
          "hours_to_departure": 72}
REQUEST = {"booking_id": "NEW1", "customer": "Spot haulier", "unit_type": "van", "length_m": 6.5,
           "weight_t": 3.0, "discharge_port": "Immingham", "segment": "spot", "rate_per_m": 95.0}


def test_plan_places_every_booking_that_fits(client, wait):
    # 20 zones of 25.5 m after 15% lost space: 15 bookings leave room for every big unit
    result = plan(client, wait, state(15))
    assert result["excluded"] == [] and len(result["placements"]) == 15


def test_overbooked_plan_lists_exclusions_with_reasons(client, wait):
    result = plan(client, wait, state(90), timeout=120)
    assert result["excluded"] and all(e["reason"] for e in result["excluded"])


def test_first_plan_of_60_bookings_takes_under_30_seconds(client, wait):
    start = time.perf_counter()
    plan(client, wait, state(60))
    assert time.perf_counter() - start < 30


def test_default_lost_space_is_15_percent(client, wait):
    result = plan(client, wait, state(10))
    assert result["deck"]["broken_stowage_pct"] == pytest.approx(0.15)


def test_on_board_unit_in_a_zone_that_no_longer_exists_is_422(client):
    body = state(5, placements={"B001": "L6-Z0"})
    body["bookings"][0]["on_board"] = True
    r = client.post("/api/planner/plan", json=body)
    assert r.status_code == 422 and "L6-Z0" in r.json()["detail"]


def test_bad_slot_text_is_422(client):
    r = client.post("/api/planner/plan", json=state(5, placements={"B001": "nowhere"}))
    assert r.status_code == 422


def test_move_respects_constraints(client, wait):
    result = plan(client, wait, state(30))
    sizes = {b["booking_id"]: b["length_m"] for b in planner_bookings(30)}
    unit = min(result["placements"], key=lambda k: sizes[k])
    free = next(s for s, m in result["deck"]["remaining_m"].items()
                if m >= sizes[unit] + 0.5 and s != result["placements"][unit])
    moved = client.post("/api/planner/move", json={**state(30, placements=result["placements"]),
                                                   "booking_id": unit, "slot": free})
    assert moved.status_code == 200 and moved.json()["placements"][unit] == free
    refused = client.post("/api/planner/move", json={**state(30, placements=result["placements"]),
                                                     "booking_id": unit, "slot": "L9-Z9"})
    assert refused.status_code == 422 and refused.json()["detail"]


def test_on_board_unit_cannot_move(client, wait):
    result = plan(client, wait, state(30))
    body = state(30, placements=result["placements"])
    unit = next(iter(result["placements"]))
    for b in body["bookings"]:
        b["on_board"] = b["booking_id"] == unit
    r = client.post("/api/planner/move", json={**body, "booking_id": unit, "slot": "L1-Z0"})
    assert r.status_code == 422 and "on board" in r.json()["detail"]


def test_advise_returns_verdict_and_assumption(client, wait):
    result = plan(client, wait, state(30))
    job = client.post("/api/planner/advise", json={**state(30, placements=result["placements"]),
                                                   "request": REQUEST, "demand": DEMAND}).json()
    verdict = wait(client, job["job_id"], timeout=60)["result"]
    assert verdict["text"] and verdict["assumption"] == "Assumption: high demand, 45% contract"


def test_advise_without_price_is_422(client):
    r = client.post("/api/planner/advise", json={**state(5), "request": {**REQUEST, "rate_per_m": None},
                                                 "demand": DEMAND})
    assert r.status_code == 422


def test_advise_with_duplicate_id_is_422(client):
    r = client.post("/api/planner/advise", json={**state(5), "request": {**REQUEST, "booking_id": "B001"},
                                                 "demand": DEMAND})
    assert r.status_code == 422 and "B001" in r.json()["detail"]


def test_revenue_known_is_false_without_prices(client, wait):
    assert plan(client, wait, state(10, prices=False))["revenue_known"] is False
    assert plan(client, wait, state(10))["revenue_known"] is True


def test_planner_pdf_export(client, wait):
    result = plan(client, wait, state(30))
    r = client.post("/api/export/pdf", json={"source": "planner", "plan_key": "planner",
                                             "state": state(30, placements=result["placements"])})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_more_than_500_bookings_is_422(client):
    body = state(5)
    body["bookings"] = body["bookings"] * 101
    assert client.post("/api/planner/plan", json=body).status_code == 422
