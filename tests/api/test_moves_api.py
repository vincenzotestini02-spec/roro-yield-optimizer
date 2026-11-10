from tests.api.tests_planner_helpers import planner_state


def state(client, decisions, seed=3):
    return client.post("/api/game/state", json={"seed": seed, "decisions": decisions})


def first_accept(client):
    s = state(client, []).json()
    accept = {"booking_id": s["current"]["id"], "action": "accept", "slot": None}
    after = state(client, [accept]).json()
    unit = after["deck"]["placements"][0]
    target = next(z for z, m in after["deck"]["remaining_m"].items() if m > 20 and z != unit["slot"])
    return accept, unit["booking_id"], target


def test_a_move_decision_moves_the_unit_and_costs_80(client):
    accept, bid, target = first_accept(client)
    after = state(client, [accept, {"booking_id": bid, "action": "move", "slot": target}]).json()
    assert after["deck"]["placements"][0]["slot"] == target
    assert after["moves"] == 1 and after["move_cost_eur"] == 80


def test_an_invalid_move_is_422_with_the_reason(client):
    accept, bid, _ = first_accept(client)
    r = state(client, [accept, {"booking_id": bid, "action": "move", "slot": "L9-Z0"}])
    assert r.status_code == 422 and r.json()["detail"]


def test_a_move_without_slot_is_422(client):
    accept, bid, _ = first_accept(client)
    r = state(client, [accept, {"booking_id": bid, "action": "move", "slot": None}])
    assert r.status_code == 422


def test_moves_survive_the_replay_of_a_shared_game(client):
    accept, bid, target = first_accept(client)
    decisions = [accept, {"booking_id": bid, "action": "move", "slot": target}]
    while True:
        s = state(client, decisions).json()
        if s["finished"]:
            break
        decisions.append({"booking_id": s["current"]["id"], "action": "reject", "slot": None})
    r = client.post("/api/reveal", json={"seed": 3, "decisions": decisions}).json()
    assert r["you"]["kpis"]["moves"] == 1 and r["you"]["kpis"]["move_cost"] == 80


def test_verdict_has_decision_range_and_moves(client, wait):
    job = client.post("/api/game/verdict", json={"seed": 3, "decisions": []}).json()
    v = wait(client, job["job_id"], timeout=60)["result"]
    assert v["decision"] in ("accept", "reject", "your_call")
    assert v["gain_low"] <= v["expected_gain_eur"] <= v["gain_high"] and v["moves"] == []


def test_reveal_says_the_smart_planner_knew_n(client, finished_game):
    r = client.post("/api/reveal", json=finished_game).json()
    assert any("knew how many requests" in n for n in r["notes"])


def test_planner_verdict_has_the_new_fields_and_no_moves(client, wait):
    body = planner_state(10)
    request = {"booking_id": "NEW1", "customer": "X", "unit_type": "van", "length_m": 6.5, "weight_t": 3,
               "discharge_port": "Imm", "segment": "spot", "rate_per_m": 95}
    job = client.post("/api/planner/advise", json={**body, "request": request, "demand": {"level": "normal"}}).json()
    v = wait(client, job["job_id"], timeout=60)["result"]
    assert v["decision"] in ("accept", "reject", "your_call") and v["moves"] == []
