"""Unit tests for the app's process-wide smart cache and the Reveal's best-plan candidates."""

import threading
import time
from dataclasses import replace

import pytest

import app.state as state
from app.jobs import JobRunner
from roro_yield.models import Plan, Slot
from roro_yield.simulator import ScenarioParams, generate_scenario


def _wait(jobs, key, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = jobs.result(key)
        if value is not None or jobs.error(key) is not None:
            return value
        time.sleep(0.01)
    raise AssertionError(f"job {key} did not finish")


def test_smart_cache_keys_on_full_params_and_k():
    cache = state.SmartCache()
    p = ScenarioParams(seed=4)
    cache.put(p, 10, ("plan", []))
    assert cache.get(p, 10) == ("plan", [])
    assert cache.get(p, 20) is None  # K is part of the key
    assert cache.get(replace(p, n_lanes=5), 10) is None  # so is every other parameter
    assert cache.get(replace(p, seed=5), 10) is None


def test_smart_cache_is_bounded_and_thread_safe():
    cache = state.SmartCache(max_entries=50)

    def writer(base):
        for i in range(100):
            cache.put(ScenarioParams(seed=base + i), 3, (i, []))

    threads = [threading.Thread(target=writer, args=(1000 * t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(cache._results) == 50


def test_second_session_reuses_the_cached_smart_run(monkeypatch):
    calls = []

    def fake_smart_plan(scenario, params, k, on_progress=None):
        calls.append((params, k))
        return (Plan("smart", {}, [b.id for b in scenario.bookings]), [])

    monkeypatch.setattr(state, "smart_plan", fake_smart_plan)
    cache = state.SmartCache()
    params = ScenarioParams(seed=12, n_requests=5)
    scenario = generate_scenario(params)

    first = JobRunner()  # session 1: nothing cached, so the run is submitted and stored on completion
    assert state.start_smart(first, ("smart", 12), scenario, params, 3, cache) is False
    result = _wait(first, ("smart", 12))
    assert cache.get(params, 3) is result and calls == [(params, 3)]

    second = JobRunner()  # session 2, same seed and K: served from the cache, nothing submitted
    monkeypatch.setattr(second, "submit", lambda *a, **kw: pytest.fail("submitted despite cache hit"))
    assert state.start_smart(second, ("smart", 12), scenario, params, 3, cache) is True
    assert second.result(("smart", 12)) is result
    assert calls == [(params, 3)]


def test_reveal_best_is_warm_started_from_the_players_plan(monkeypatch):
    seen = []

    def fake_solve_optimal(scenario, candidates=()):
        seen.append(candidates)
        return Plan("best", {}, [])

    monkeypatch.setattr(state, "solve_optimal", fake_solve_optimal)
    monkeypatch.setattr(state.st, "session_state", {})
    you = Plan("You", {"B001": Slot("L1", 0)}, [])
    other_you = Plan("You", {"B001": Slot("L2", 1)}, [])
    smart = Plan("smart", {}, ["B001"])
    state.reveal_best(1, None, you, smart)
    assert seen[-1] == (you, smart)
    state.reveal_best(1, None, you, None)
    assert seen[-1] == (you,)
    state.reveal_best(1, None, other_you, smart)  # a different player plan is a different cache entry
    assert seen[-1] == (other_you, smart) and len(seen) == 3
    state.reveal_best(1, None, you, smart)  # cached
    assert len(seen) == 3
