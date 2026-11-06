import threading

import pytest

from server import jobs_api
from server.jobs import QueueFull
from server.runtime import get_jobs


def start(client, seed=3):
    return client.post("/api/game/verdict", json={"seed": seed, "decisions": []})


def test_verdict_job_completes(client, wait):
    job = wait(client, start(client).json()["job_id"], timeout=30)
    assert job["status"] == "done" and "text" in job["result"] and job["progress"] == 1.0


def test_same_request_reuses_the_job(client):
    assert start(client).json() == start(client).json()


def test_verdict_after_the_end_is_409(client, finished_game):
    assert client.post("/api/game/verdict", json=finished_game).status_code == 409


def test_unknown_job_is_404_with_message(client):
    r = client.get("/api/jobs/deadbeef")
    assert r.status_code == 404 and r.json()["detail"]


def test_full_queue_is_429(client, monkeypatch):
    def full(*_):
        raise QueueFull
    monkeypatch.setattr(get_jobs(), "submit", full)
    r = start(client, seed=11)
    assert r.status_code == 429 and "busy" in r.json()["detail"]


def test_cancel_removes_the_job(client):
    release = threading.Event()
    job_id = jobs_api.submit(("test-slow",), release.wait)
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    release.set()


def test_failed_job_reports_a_safe_message(client, wait):
    def boom():
        raise ValueError("internal path C:/secret")
    job = wait(client, jobs_api.submit(("test-boom",), boom), timeout=5)
    assert job["status"] == "failed" and "secret" not in job["error"]
