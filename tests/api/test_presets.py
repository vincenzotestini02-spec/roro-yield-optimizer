import pytest

from roro_yield.simulator import ScenarioParams, generate_scenario
from server.lab_api import LIMITS
from server.presets import PRESETS


def requested_metres(values: dict) -> float:
    s = generate_scenario(ScenarioParams(**values))
    return sum(b.effective_length(s.vessel.lashing_gap_m) for b in s.bookings)


@pytest.fixture
def defaults(client):
    return client.get("/api/lab/defaults").json()["values"]


def test_presets_are_listed_with_the_note(client):
    d = client.get("/api/lab/defaults").json()
    assert set(d["presets"]) == {"demo", "ropax", "shortsea"} and "not a named ship" in d["note"]


@pytest.mark.parametrize("key", ["ropax", "shortsea"])
def test_large_presets_load_most_of_the_demand(client, defaults, key, wait):
    values = {**defaults, **PRESETS[key]["values"]}
    plans = wait(client, client.post("/api/lab/plans", json=values).json()["job_id"], timeout=180)["result"]
    deck = plans["fcfs"]["deck"]
    assert deck["used_m"] >= 0.8 * min(deck["usable_m"], requested_metres(values))


def test_every_preset_value_is_inside_the_limits():
    for preset in PRESETS.values():
        for name, value in preset["values"].items():
            low, high = LIMITS[name]
            assert low <= value <= high, name


def test_lost_space_reduces_usable_metres(client, defaults, wait):
    values = {**defaults, "broken_stowage_pct": 0.15}
    plans = wait(client, client.post("/api/lab/plans", json=values).json()["job_id"])["result"]
    assert plans["fcfs"]["deck"]["usable_m"] == pytest.approx(600 * 0.85)


def test_big_settings_warn_that_the_smart_plan_is_slow(client, defaults, wait):
    values = {**defaults, **PRESETS["shortsea"]["values"]}
    plans = wait(client, client.post("/api/lab/plans", json=values).json()["job_id"], timeout=180)["result"]
    assert plans["smart_may_be_slow"] is True


def test_demo_settings_do_not_warn(client, defaults, wait):
    plans = wait(client, client.post("/api/lab/plans", json=defaults).json()["job_id"])["result"]
    assert plans["smart_may_be_slow"] is False
