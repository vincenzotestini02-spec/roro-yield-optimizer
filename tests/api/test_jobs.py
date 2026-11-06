import threading
import pytest
import time

from server.jobs import JobRunner, QueueFull


def _wait(jobs, key, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = jobs.result(key)
        if value is not None or jobs.error(key) is not None:
            return value
        time.sleep(0.01)
    raise AssertionError(f"job {key} did not finish")


def _plain(x):
    return x * 2


def _with_progress(n, on_progress=None):
    for i in range(n):
        if on_progress is not None:
            on_progress(i + 1, n)
    return "done"


def test_submit_and_result_without_progress_arg():
    jobs = JobRunner()
    jobs.submit(("verdict", 1, 0), _plain, 21)  # _plain has no on_progress: must not get one
    assert _wait(jobs, ("verdict", 1, 0)) == 42
    assert jobs.progress(("verdict", 1, 0)) == 1.0


def test_submit_is_noop_when_key_exists():
    jobs = JobRunner()
    calls = []
    jobs.submit(("a",), lambda: calls.append(1) or "first")
    _wait(jobs, ("a",))
    jobs.submit(("a",), lambda: calls.append(2) or "second")
    time.sleep(0.05)
    assert jobs.result(("a",)) == "first"
    assert calls == [1]


def test_jobs_keyed_by_seed():
    jobs = JobRunner()
    jobs.submit(("smart", 1), _plain, 1)
    jobs.submit(("verdict", 1, 0), _plain, 10)
    jobs.submit(("smart", 2), _plain, 2)
    jobs.submit(("verdict", 2, 0), _plain, 20)
    _wait(jobs, ("verdict", 2, 0))
    jobs.forget_except(("smart", 2))
    assert jobs.result(("smart", 1)) is None
    assert jobs.result(("verdict", 1, 0)) is None
    # Verdicts depend on the player's deck, so even same-seed verdicts are stale in a new game.
    assert jobs.result(("verdict", 2, 0)) is None
    assert jobs.result(("smart", 2)) == 4


def test_forget_aborts_a_running_progress_job():
    jobs = JobRunner()
    started = threading.Event()
    seen = []

    def slow(on_progress=None):
        started.set()
        for i in range(200):
            time.sleep(0.01)
            on_progress(i + 1, 200)
            seen.append(i)
        return "finished"

    jobs.submit(("smart", 1), slow)
    started.wait(5)
    jobs.forget_except(("smart", 2))
    jobs.submit(("smart", 2), _plain, 3)
    assert _wait(jobs, ("smart", 2), timeout=5) == 6  # not stuck behind the old seed
    assert len(seen) < 200
    assert jobs.result(("smart", 1)) is None


def test_job_progress():
    jobs = JobRunner()
    gate = threading.Event()
    release = threading.Event()

    def staged(on_progress=None):
        on_progress(1, 4)
        gate.set()
        release.wait(5)
        on_progress(4, 4)
        return "ok"

    assert jobs.progress(("smart", 9)) == 0.0  # unknown key
    jobs.submit(("smart", 9), staged)
    gate.wait(5)
    assert jobs.progress(("smart", 9)) == 0.25
    assert jobs.result(("smart", 9)) is None  # still running
    release.set()
    assert _wait(jobs, ("smart", 9)) == "ok"
    assert jobs.progress(("smart", 9)) == 1.0


def test_failed_job_returns_none_and_keeps_error():
    jobs = JobRunner()

    def boom():
        raise RuntimeError("solver exploded")

    jobs.submit(("smart", 5), boom)
    _wait(jobs, ("smart", 5))
    assert jobs.result(("smart", 5)) is None
    assert isinstance(jobs.error(("smart", 5)), RuntimeError)


def test_put_stores_a_computed_result():
    jobs = JobRunner()
    jobs.put(("verdict", 1, 3), "v")
    assert jobs.result(("verdict", 1, 3)) == "v"
    jobs.submit(("verdict", 1, 3), _plain, 1)  # no-op: already known
    assert jobs.result(("verdict", 1, 3)) == "v"


def test_paused_holds_progress_jobs_at_their_next_progress_call():
    jobs = JobRunner()
    count = []

    def ticking(on_progress=None):
        for i in range(400):
            time.sleep(0.005)
            on_progress(i + 1, 400)
            count.append(i)
        return "ok"

    jobs.submit(("smart", 1), ticking)
    time.sleep(0.1)
    with jobs.paused():
        time.sleep(0.05)  # let the worker reach its next progress call
        frozen = len(count)
        time.sleep(0.2)
        assert len(count) <= frozen + 1
    assert _wait(jobs, ("smart", 1)) == "ok"


def test_forget_drops_only_keys_with_the_prefix_and_aborts_them():
    jobs = JobRunner()
    started = threading.Event()
    seen = []

    def slow(on_progress=None):
        started.set()
        for i in range(200):
            time.sleep(0.01)
            on_progress(i + 1, 200)
            seen.append(i)
        return "old settings"

    jobs.submit(("smart", 1), _plain, 1)
    _wait(jobs, ("smart", 1))
    jobs.submit(("lab_smart", "old"), slow)
    started.wait(5)
    jobs.submit(("lab_smart", "older"), _plain, 5)  # queued behind the running one
    jobs.forget(("lab_smart",))
    assert not jobs.has(("lab_smart", "old")) and not jobs.has(("lab_smart", "older"))
    jobs.submit(("lab_smart", "new"), _plain, 7)
    assert _wait(jobs, ("lab_smart", "new"), timeout=5) == 14  # not stuck behind the old run
    assert len(seen) < 200
    assert jobs.result(("smart", 1)) == 2  # other prefixes are kept


def test_queue_limit_raises_for_new_jobs():
    jobs = JobRunner(max_workers=1, max_queued=1)
    release = threading.Event()
    jobs.submit(("a",), release.wait)
    jobs.submit(("b",), lambda: 1)
    with pytest.raises(QueueFull):
        jobs.submit(("c",), lambda: 1)
    jobs.submit(("b",), lambda: 1)  # already known: no error
    release.set()


def test_two_jobs_run_together():
    jobs = JobRunner(max_workers=2)
    barrier = threading.Barrier(2, timeout=3)
    jobs.submit(("a",), barrier.wait)
    jobs.submit(("b",), barrier.wait)
    assert _wait(jobs, ("a",), timeout=4) is not None


def test_status_lifecycle_and_unknown():
    jobs = JobRunner()
    assert jobs.status(("x",)) == "unknown"
    jobs.submit(("x",), lambda: 1)
    _wait(jobs, ("x",), timeout=3)
    assert jobs.status(("x",)) == "done"


def test_cancel_forgets_the_job():
    jobs = JobRunner(max_workers=1)
    release = threading.Event()
    jobs.submit(("busy",), release.wait)
    jobs.submit(("queued",), lambda: 1)
    jobs.cancel(("queued",))
    assert jobs.status(("queued",)) == "unknown"
    release.set()


def test_failed_job_status():
    jobs = JobRunner()
    def boom():
        raise ValueError("no")
    jobs.submit(("x",), boom)
    _wait(jobs, ("x",), timeout=3)
    assert jobs.status(("x",)) == "failed"


def test_old_finished_jobs_expire():
    jobs = JobRunner(ttl_s=0.0)
    jobs.submit(("old",), lambda: 1)
    _wait(jobs, ("old",), timeout=3)
    jobs.submit(("new",), lambda: 2)
    assert jobs.status(("old",)) == "unknown"
