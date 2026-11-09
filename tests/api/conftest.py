import time

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def wait():
    return wait_job


def wait_job(client, job_id, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.fixture
def finished_game(client):
    """All requests of seed 3 rejected, in the replay format."""
    decisions = []
    while True:
        state = client.post("/api/game/state", json={"seed": 3, "decisions": decisions}).json()
        if state["finished"]:
            return {"seed": 3, "decisions": decisions}
        decisions.append({"booking_id": state["current"]["id"], "action": "reject", "slot": None})


@pytest.fixture
def lab_values(client):
    return client.get("/api/lab/defaults").json()["values"]
