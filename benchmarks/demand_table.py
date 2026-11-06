"""Smart planner against FCFS and the optimizer at three demand levels, on the v3 deck.

    python -m benchmarks.demand_table --out benchmarks/results/demand_table.json --workers 8

The optimizer runs one sailing at a time after the pool ends: run next to many busy processes,
the MILP is starved of CPU and stops near the FCFS plan.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from multiprocessing import Pool

from roro_yield.advisor import smart_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import objective
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import generate_scenario
from server.config import GAME_PARAMS

LEVELS = (("low", 35), ("normal", 50), ("high", 60))
SEEDS = range(1, 31)
K = 20


def summarize(label: str, n_requests: int, rows: list[dict]) -> dict:
    gains = [r["smart"] - r["fcfs"] for r in rows]
    fcfs = statistics.mean(r["fcfs"] for r in rows)
    smart = statistics.mean(r["smart"] for r in rows)
    return {
        "label": label,
        "n_requests": n_requests,
        "demand_ratio": statistics.mean(r["demand_ratio"] for r in rows),
        "fcfs": fcfs,
        "smart": smart,
        "optimal": statistics.mean(r["optimal"] for r in rows),
        "smart_vs_fcfs_pct": 100 * (smart / fcfs - 1),
        "smart_vs_fcfs_se_eur": statistics.stdev(gains) / math.sqrt(len(gains)) if len(gains) > 1 else 0.0,
        "lost_to_fcfs": sum(g < 0 for g in gains),
        "n_sailings": len(rows),
    }


def _params(n_requests: int, seed: int):
    return replace(GAME_PARAMS, n_requests=n_requests, seed=seed)


def _smart(args: tuple[str, int, int, int]):
    label, n_requests, seed, k = args
    params = _params(n_requests, seed)
    return label, n_requests, seed, smart_plan(generate_scenario(params), params, k=k)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    jobs = [(label, n, seed, K) for label, n in LEVELS for seed in SEEDS]
    with Pool(args.workers) as pool:
        played = pool.map(_smart, jobs, chunksize=1)
    rows: dict[str, list[dict]] = {label: [] for label, _ in LEVELS}
    for label, n_requests, seed, smart in played:
        s = generate_scenario(_params(n_requests, seed))
        fcfs = solve_fcfs(s)
        best = solve_optimal(s, time_limit_s=5, candidates=(smart,))
        demand_m = sum(b.effective_length(s.vessel.lashing_gap_m) for b in s.bookings)
        rows[label].append({"seed": seed, "fcfs": objective(s, fcfs), "smart": objective(s, smart),
                            "optimal": objective(s, best), "demand_ratio": demand_m / s.vessel.total_lane_m})
    table = {
        "levels": [summarize(label, n, rows[label]) for label, n in LEVELS],
        "k": K,
        "seeds": [SEEDS.start, SEEDS.stop - 1],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2)


if __name__ == "__main__":
    main()
