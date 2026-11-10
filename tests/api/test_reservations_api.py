import io

from pypdf import PdfReader

from tests.api.tests_planner_helpers import planner_state


def plan(client, wait, body):
    job = client.post("/api/planner/plan", json=body)
    assert job.status_code == 200, job.text
    result = wait(client, job.json()["job_id"], timeout=120)
    assert result["status"] == "done", result
    return result["result"]


def test_plan_with_a_reservation_reports_its_use(client, wait):
    body = {**planner_state(20), "reservations": [{"customer": "Nordfreight", "metres": 50}]}
    result = plan(client, wait, body)
    status = result["reservations"]
    assert status[0]["customer"] == "Nordfreight" and status[0]["metres"] == 50
    assert status[0]["used"] + status[0]["left"] == 50


def test_reservation_larger_than_the_deck_is_422(client):
    body = {**planner_state(5), "reservations": [{"customer": "Nordfreight", "metres": 5000}]}
    r = client.post("/api/planner/plan", json=body)
    assert r.status_code == 422 and "usable deck" in r.json()["detail"]


def test_the_same_customer_reserved_twice_is_422(client):
    body = {**planner_state(5), "reservations": [{"customer": "Nordfreight", "metres": 20},
                                                 {"customer": " nordfreight ", "metres": 10}]}
    r = client.post("/api/planner/plan", json=body)
    assert r.status_code == 422 and "reserved twice" in r.json()["detail"]


def test_advise_respects_reservations(client, wait):
    body = {**planner_state(3), "reservations": [{"customer": "Nordfreight", "metres": 505}]}  # 510 m usable
    request = {"booking_id": "NEW1", "customer": "Other", "unit_type": "semi_trailer", "length_m": 13.6,
               "weight_t": 20, "discharge_port": "Imm", "segment": "spot", "rate_per_m": 95}
    job = client.post("/api/planner/advise", json={**body, "request": request, "demand": {"level": "normal"}}).json()
    v = wait(client, job["job_id"], timeout=60)["result"]
    assert not v["feasible"] and "reserved for Nordfreight" in v["reason"]


def test_an_on_board_unit_is_never_pushed_out_by_a_reservation(client, wait):
    body = planner_state(5)
    first = plan(client, wait, body)
    unit = next(iter(first["placements"]))
    for b in body["bookings"]:
        b["on_board"] = b["booking_id"] == unit
    body = {**body, "placements": first["placements"], "reservations": [{"customer": "Somebody", "metres": 500}]}
    again = plan(client, wait, body)
    assert again["placements"][unit] == first["placements"][unit]


def test_planner_pdf_lists_reservations(client, wait):
    body = {**planner_state(10), "reservations": [{"customer": "Nordfreight", "metres": 40}]}
    result = plan(client, wait, body)
    r = client.post("/api/export/pdf", json={"source": "planner", "plan_key": "planner",
                                             "state": {**body, "placements": result["placements"]}})
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
    assert r.status_code == 200 and "Nordfreight" in text and "40" in text


def test_state_without_reservations_still_works(client, wait):
    result = plan(client, wait, planner_state(5))
    assert result["reservations"] == []
