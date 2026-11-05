"""Background jobs for the UI: one worker thread, results keyed by tuples. Pure Python, no Streamlit.

Keys are tuples such as ("smart", seed) or ("verdict", seed, index).

- `submit(key, fn, *args)` runs `fn(*args)` on the worker; a no-op if `key` is already known.
  If `fn` has an `on_progress` parameter, it gets a callback `on_progress(done, total)` (or
  `on_progress(fraction)`) that feeds `progress(key)`. Functions without it (e.g. `advise`) are
  called with `*args` only.
- `result(key)` is None while the job is queued or running, unknown, or failed. A failure never
  raises into the UI: it is logged once and kept in `error(key)`.
- `forget_except(prefix)` drops every job whose key does not start with `prefix`. The app calls
  `forget_except(("smart", seed))` on a new game: the old seeds' jobs are dropped, and so are all
  verdict jobs (even of the same seed), because a verdict depends on the player's deck and a new
  game starts a new deck. Only the deterministic smart run of `seed` survives. Queued jobs are
  cancelled; a running job that reports progress is aborted at its next progress call, so a new
  seed's smart run is never stuck behind an old one.
- `forget(prefix)` is the opposite: it drops every job whose key DOES start with `prefix`, with the
  same cancel/abort rules. The Lab calls `forget(("lab_smart",))` before a new Lab smart run, so
  a run for old slider settings never blocks the one just asked for.
- `with paused():` holds progress-reporting jobs at their next progress call, so a verdict the UI
  computes synchronously does not share the CPU (and the GIL) with the background smart run.
"""

from __future__ import annotations

import inspect
import logging
import threading
from contextlib import contextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)


class _Forgotten(Exception):
    """Raised inside a job's progress callback once its key has been forgotten."""


class _Job:
    def __init__(self, future: Future):
        self.future = future
        self.progress = 0.0
        self.forgotten = threading.Event()
        self.logged = False


def _accepts_on_progress(fn: Callable) -> bool:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return "on_progress" in params


class JobRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="roro-job")
        self._jobs: dict[tuple, _Job] = {}
        self._lock = threading.Lock()
        self._running = threading.Event()  # cleared while paused
        self._running.set()
        self._pauses = 0

    def has(self, key: tuple) -> bool:
        with self._lock:
            return key in self._jobs

    def submit(self, key: tuple, fn: Callable, *args: Any) -> None:
        with self._lock:
            if key in self._jobs:
                return
            future: Future = Future()  # placeholder until the executor's future exists
            job = _Job(future)
            self._jobs[key] = job

            def on_progress(done: float, total: float | None = None) -> None:
                if job.forgotten.is_set():
                    raise _Forgotten(key)
                while not self._running.wait(0.05):  # paused: wait, but stay abortable
                    if job.forgotten.is_set():
                        raise _Forgotten(key)
                frac = done if total is None else (done / total if total else 1.0)
                job.progress = max(0.0, min(1.0, float(frac)))

            def run() -> Any:
                if job.forgotten.is_set():
                    raise _Forgotten(key)
                if _accepts_on_progress(fn):
                    return fn(*args, on_progress=on_progress)
                return fn(*args)

            job.future = self._executor.submit(run)

    @contextmanager
    def paused(self):
        with self._lock:
            self._pauses += 1
            self._running.clear()
        try:
            yield
        finally:
            with self._lock:
                self._pauses -= 1
                if self._pauses == 0:
                    self._running.set()

    def put(self, key: tuple, value: Any) -> None:
        """Store a result computed elsewhere (e.g. synchronously); replaces a queued job."""
        future: Future = Future()
        future.set_result(value)
        job = _Job(future)
        job.progress = 1.0
        with self._lock:
            old = self._jobs.get(key)
            if old is not None:
                old.forgotten.set()
                old.future.cancel()
            self._jobs[key] = job

    def _done_job(self, key: tuple) -> _Job | None:
        with self._lock:
            job = self._jobs.get(key)
        if job is None or not job.future.done() or job.future.cancelled():
            return None
        return job

    def error(self, key: tuple) -> BaseException | None:
        job = self._done_job(key)
        return None if job is None else job.future.exception()

    def result(self, key: tuple) -> Any | None:
        job = self._done_job(key)
        if job is None:
            return None
        exc = job.future.exception()
        if exc is not None:
            if not job.logged:
                job.logged = True
                log.error("background job %r failed", key, exc_info=exc)
            return None
        return job.future.result()

    def progress(self, key: tuple) -> float:
        with self._lock:
            job = self._jobs.get(key)
        if job is None:
            return 0.0
        if job.future.done() and not job.future.cancelled() and job.future.exception() is None:
            return 1.0
        return job.progress

    def _drop_where(self, condition: Callable[[tuple], bool]) -> None:
        with self._lock:
            for k in [k for k in self._jobs if condition(k)]:
                job = self._jobs.pop(k)
                job.forgotten.set()  # a running progress job aborts at its next progress call
                job.future.cancel()  # a queued job never starts

    def forget_except(self, prefix: tuple) -> None:
        n, prefix = len(prefix), tuple(prefix)
        self._drop_where(lambda k: tuple(k[:n]) != prefix)

    def forget(self, prefix: tuple) -> None:
        n, prefix = len(prefix), tuple(prefix)
        self._drop_where(lambda k: tuple(k[:n]) == prefix)
