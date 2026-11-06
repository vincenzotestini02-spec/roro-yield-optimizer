"""Finished smart runs shared by every visitor of this process."""

from __future__ import annotations

import threading
from collections import OrderedDict

from roro_yield.simulator import ScenarioParams


class SmartCache:
    """Results keyed by (params, K): the smart run is deterministic in them.

    Thread-safe; keeps the newest `max_entries` results. Cached plans are shared: callers must
    not mutate them.
    """

    def __init__(self, max_entries: int = 256):
        self._lock = threading.Lock()
        self._results: OrderedDict[tuple, tuple] = OrderedDict()
        self._max = max_entries

    def get(self, params: ScenarioParams, k: int) -> tuple | None:
        with self._lock:
            return self._results.get((params, k))

    def put(self, params: ScenarioParams, k: int, result: tuple) -> None:
        with self._lock:
            self._results[(params, k)] = result
            self._results.move_to_end((params, k))
            while len(self._results) > self._max:
                self._results.popitem(last=False)
