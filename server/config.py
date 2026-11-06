"""Fixed settings of the v3 server."""

from __future__ import annotations

import os

from roro_yield.simulator import ScenarioParams

GAME_PARAMS = ScenarioParams(n_lanes=5, lane_length_m=120.0)
ADVISOR_K = int(os.environ.get("RORO_ADVISOR_K", 20))
MAX_WORKERS = 2
MAX_QUEUED_JOBS = 8
JOB_TTL_S = 3600
