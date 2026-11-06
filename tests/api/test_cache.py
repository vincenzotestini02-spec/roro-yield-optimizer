from roro_yield.simulator import ScenarioParams
from server.cache import SmartCache


def test_smart_cache_keeps_newest_entries():
    cache = SmartCache(max_entries=1)
    a, b = ScenarioParams(seed=1), ScenarioParams(seed=2)
    cache.put(a, 20, ("a",))
    cache.put(b, 20, ("b",))
    assert cache.get(a, 20) is None and cache.get(b, 20) == ("b",)
