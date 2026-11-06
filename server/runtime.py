"""Process-wide job runner and cache."""

from __future__ import annotations

from functools import lru_cache

from server.cache import SmartCache
from server.config import JOB_TTL_S, MAX_QUEUED_JOBS, MAX_WORKERS
from server.jobs import JobRunner


@lru_cache(maxsize=1)
def get_jobs() -> JobRunner:
    return JobRunner(max_workers=MAX_WORKERS, max_queued=MAX_QUEUED_JOBS, ttl_s=JOB_TTL_S)


@lru_cache(maxsize=1)
def get_smart_cache() -> SmartCache:
    return SmartCache()
