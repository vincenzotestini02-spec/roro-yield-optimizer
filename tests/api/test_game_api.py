from dataclasses import replace

import pytest

from roro_yield.game import GameSession
from roro_yield.simulator import generate_scenario
from server.config import GAME_PARAMS


def state(client, seed=3, decisions=()):
    return client.post("/api/game/state", json={"seed": seed, "decisions": list(decisions)})


def test_new_game_shows_first_request_only(client):
    s = state(client).json()
    assert s["index"] == 0 and s["n_total"] == 60 and not s["finished"]
    assert s["past"] == [] and s["current"]["id"]
    assert s["feasible_slots"] and s["best_slot"] in s["feasible_slots"]


def test_future_bookings_are_never_sent(client):
    body = state(client).text
    scenario = generate_scenario(replace(GAME_PARAMS, seed=3))
    first = state(client).json()["current"]["id"]
    for b in scenario.bookings:
        if b.id != first:
            assert f'"{b.id}"' not in body


def test_replay_matches_a_direct_game(client):
    params = replace(GAME_PARAMS, seed=3)
    direct = GameSession(generate_scenario(params), params)
    first = direct.current.id
    direct.accept(0)
    s = state(client, decisions=[{"booking_id": first, "action": "accept", "slot": None}]).json()
    assert s["index"] == 1
    assert {p["booking_id"]: p["slot"] for p in s["deck"]["placements"]} == {
        k: str(v) for k, v in direct.deck.placements.items()}
    assert [b["id"] for b in s["past"]] == [first]


def test_a_chosen_slot_is_respected(client):
    s = state(client).json()
    slot = s["feasible_slots"][-1]
    after = state(client, decisions=[
        {"booking_id": s["current"]["id"], "action": "accept", "slot": slot}]).json()
    assert after["deck"]["placements"][0]["slot"] == slot


@pytest.mark.parametrize("booking_id,slot", [("WRONG", None), ("FIRST", "L9-Z9"), ("FIRST", "nonsense")])
def test_bad_decision_is_422_with_a_reason(client, booking_id, slot):
    first = state(client).json()["current"]["id"]
    r = state(client, decisions=[{"booking_id": first if booking_id == "FIRST" else booking_id,
                                  "action": "accept", "slot": slot}])
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_decision_after_the_end_is_422(client, finished_game):
    extra = finished_game["decisions"] + [{"booking_id": "B001", "action": "reject", "slot": None}]
    r = state(client, decisions=extra)
    assert r.status_code == 422 and "finished" in r.json()["detail"]


def test_seed_out_of_range_is_422(client):
    assert state(client, seed=0).status_code == 422


def test_finished_game_has_no_current_request(client, finished_game):
    s = state(client, decisions=finished_game["decisions"]).json()
    assert s["finished"] and s["current"] is None and s["feasible_slots"] == []
