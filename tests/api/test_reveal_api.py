import pytest


def test_reveal_before_the_end_is_409(client):
    assert client.post("/api/reveal", json={"seed": 3, "decisions": []}).status_code == 409


def test_reveal_returns_you_and_fcfs_at_once(client, finished_game):
    r = client.post("/api/reveal", json=finished_game).json()
    assert r["you"]["kpis"]["method"] == "You" and r["fcfs"]["kpis"]["objective"] > 0
    assert r["smart_job"] and len(r["you"]["rejected"]) == 60 and r["you"]["deck"]["placements"] == []


def test_best_before_smart_is_finished_is_409(client, finished_game):
    r = client.post("/api/reveal/best", json={**finished_game, "smart_job": "deadbeef"})
    assert r.status_code == 409


@pytest.mark.slow
def test_best_plan_is_at_least_every_other_plan(client, finished_game, wait):
    r = client.post("/api/reveal", json=finished_game).json()
    smart = wait(client, r["smart_job"], timeout=400)
    assert smart["status"] == "done"
    job = client.post("/api/reveal/best", json={**finished_game, "smart_job": r["smart_job"]}).json()
    best = wait(client, job["job_id"], timeout=60)["result"]
    assert best["plan"]["kpis"]["objective"] >= max(
        r["you"]["kpis"]["objective"], r["fcfs"]["kpis"]["objective"],
        smart["result"]["kpis"]["objective"]) - 1e-6
    assert best["costly"]
