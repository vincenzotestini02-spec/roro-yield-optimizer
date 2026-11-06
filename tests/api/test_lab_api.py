import pytest


@pytest.fixture
def values(client):
    return client.get("/api/lab/defaults").json()["values"]


def test_defaults_are_the_game_deck(client):
    d = client.get("/api/lab/defaults").json()
    assert d["values"]["n_lanes"] == 5 and d["limits"]["n_lanes"] == [1, 16]


def test_every_field_has_limits_and_a_default(client):
    d = client.get("/api/lab/defaults").json()
    assert set(d["values"]) == set(d["limits"])


def test_lab_plans_compare_fcfs_and_optimal(client, values, wait):
    job = client.post("/api/lab/plans", json=values).json()
    r = wait(client, job["job_id"], timeout=30)["result"]
    assert r["optimal"]["kpis"]["objective"] >= r["fcfs"]["kpis"]["objective"]


def test_out_of_range_value_is_422(client, values):
    assert client.post("/api/lab/plans", json={**values, "n_lanes": 99}).status_code == 422


def test_unknown_field_is_422(client, values):
    assert client.post("/api/lab/plans", json={**values, "extra": 1}).status_code == 422


def test_smart_run_on_extreme_values_can_be_cancelled(client, values):
    job = client.post("/api/lab/smart", json={**values, "n_requests": 200, "n_lanes": 16}).json()
    assert client.delete(f"/api/jobs/{job['job_id']}").status_code == 204


def test_manifest_csv_download(client, values, wait):
    job = client.post("/api/lab/plans", json=values).json()
    wait(client, job["job_id"], timeout=30)
    r = client.post("/api/manifest.csv", json={"params": values, "plan_key": "optimal"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("lane,zone,position")


def test_manifest_without_a_finished_plan_is_409(client, values):
    r = client.post("/api/manifest.csv", json={"params": {**values, "seed": 9999}, "plan_key": "smart"})
    assert r.status_code == 409
