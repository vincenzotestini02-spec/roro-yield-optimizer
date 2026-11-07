"""Long calculations: a POST starts a job, the browser polls its state here."""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Response

from server.runtime import get_jobs

router = APIRouter(prefix="/api/jobs")
BUSY_MESSAGE = "The server is busy. Try again in a moment."
FAILED_MESSAGE = "The calculation failed. Try again."
GONE_MESSAGE = "This calculation is no longer on the server. Start it again."

_keys: dict[str, tuple] = {}
_outputs: dict[str, Callable[[Any], Any]] = {}
_lock = threading.Lock()


def job_id(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode()).hexdigest()[:16]


def submit(key: tuple, fn: Callable, *args: Any, output: Callable[[Any], Any] = lambda x: x) -> str:
    """Start `fn` once per key. `output` turns its result into JSON-friendly data."""
    jobs = get_jobs()
    jobs.submit(key, fn, *args)
    identifier = job_id(key)
    with _lock:
        for old in [i for i, k in _keys.items() if jobs.status(k) == "unknown"]:  # expired or cancelled
            del _keys[old]
            _outputs.pop(old, None)
        _keys[identifier] = key
        _outputs[identifier] = output
    return identifier


def key_of(identifier: str) -> tuple | None:
    with _lock:
        return _keys.get(identifier)


@router.get("/{identifier}")
def read_job(identifier: str) -> dict:
    jobs = get_jobs()
    key = key_of(identifier)
    status = "unknown" if key is None else jobs.status(key)
    if status == "unknown":
        raise HTTPException(404, GONE_MESSAGE)
    done = status == "done"
    return {
        "status": status,
        "progress": jobs.progress(key),
        "result": _outputs[identifier](jobs.result(key)) if done else None,
        "error": FAILED_MESSAGE if status == "failed" else None,
    }


@router.delete("/{identifier}", status_code=204)
def cancel_job(identifier: str) -> Response:
    key = key_of(identifier)
    if key is not None:
        get_jobs().cancel(key)
        with _lock:
            _keys.pop(identifier, None)
            _outputs.pop(identifier, None)
    return Response(status_code=204)
