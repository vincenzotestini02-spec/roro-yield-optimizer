"""Calibrate and verify the advisor's three-answer rule on the reference ship (6 x 120 m).

    python -m benchmarks.decision_rule --calibrate --out benchmarks/results/decision_calibration.json
    python -m benchmarks.decision_rule --verify --accept-share 0.6 --reject-share 0.8 \\
        --out benchmarks/results/decision_rule.json

Calibration uses seeds 101-130 and K = 10; verification uses seeds 1-30 and K = 20, so the
thresholds are never tuned on the sailings they are judged on. FCFS and the smart planner run in a
process pool; nothing here needs the optimizer.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from multiprocessing import Pool

from benchmarks.demand_table import summarize
from roro_yield.advisor import smart_plan
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import objective
from roro_yield.simulator import ScenarioParams, generate_scenario

LEVELS = (40, 60, 90)
COMBOS = ((0.5, 0.8), (0.6, 0.8), (0.6, 0.9), (0.7, 0.9))
CALIBRATION_SEEDS = range(101, 131)
VERIFY_SEEDS = range(1, 31)
MAX_LOSS_AT_40 = -0.5  # %
MIN_GAIN = {60: 5.0, 90: 13.0}  # %


def criteria(levels: dict[int, dict]) -> dict[str, bool]:
    return {
        "loss_at_40_at_most_0_5pct": levels[40]["smart_vs_fcfs_pct"] >= MAX_LOSS_AT_40,
        "gain_at_60_at_least_5pct": levels[60]["smart_vs_fcfs_pct"] >= MIN_GAIN[60],
        "gain_at_90_at_least_13pct": levels[90]["smart_vs_fcfs_pct"] >= MIN_GAIN[90],
    }


def choose(results: dict[tuple[float, float], dict[int, dict]]) -> tuple[float, float]:
    """Best mean gain at 60 and 90 among the pairs that keep the loss at 40 within limits."""
    ok = [c for c, lv in results.items() if lv[40]["smart_vs_fcfs_pct"] >= MAX_LOSS_AT_40]
    if not ok:
        return max(results, key=lambda c: results[c][40]["smart_vs_fcfs_pct"])
    return max(ok, key=lambda c: (results[c][60]["smart_vs_fcfs_pct"] + results[c][90]["smart_vs_fcfs_pct"]) / 2)


def _play(args: tuple[int, int, int, float, float]) -> tuple:
    n, seed, k, accept_share, reject_share = args
    params = replace(ScenarioParams(), n_requests=n, seed=seed)
    s = generate_scenario(params)
    smart, _ = smart_plan(s, params, k=k, accept_share=accept_share, reject_share=reject_share)
    demand = sum(b.effective_length(s.vessel.lashing_gap_m) for b in s.bookings) / s.vessel.total_lane_m
    return (accept_share, reject_share, n, {"seed": seed, "fcfs": objective(s, solve_fcfs(s)),
                                             "smart": objective(s, smart), "optimal": 0.0,
                                             "demand_ratio": demand})


def run(combos, seeds, k: int, workers: int) -> dict[tuple[float, float], dict[int, dict]]:
    jobs = [(n, seed, k, a, r) for a, r in combos for n in LEVELS for seed in seeds]
    with Pool(workers) as pool:
        played = pool.map(_play, jobs, chunksize=1)
    rows: dict = {}
    for a, r, n, row in played:
        rows.setdefault((a, r), {}).setdefault(n, []).append(row)
    out = {c: {n: summarize(str(n), n, rows[c][n]) for n in LEVELS} for c in rows}
    for levels in out.values():
        for level in levels.values():
            level.pop("optimal")  # not computed here: these runs compare the smart planner with FCFS
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--accept-share", type=float)
    parser.add_argument("--reject-share", type=float)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if args.calibrate:
        results = run(COMBOS, CALIBRATION_SEEDS, 10, args.workers)
        chosen = choose(results)
        out = {"seeds": [CALIBRATION_SEEDS.start, CALIBRATION_SEEDS.stop - 1], "k": 10, "generated_at": stamp,
               "chosen": list(chosen),
               "combos": [{"accept_share": a, "reject_share": r, "levels": [results[(a, r)][n] for n in LEVELS]}
                          for a, r in COMBOS]}
    else:
        combo = (args.accept_share, args.reject_share)
        levels = run([combo], VERIFY_SEEDS, 20, args.workers)[combo]
        out = {"seeds": [VERIFY_SEEDS.start, VERIFY_SEEDS.stop - 1], "k": 20, "generated_at": stamp,
               "chosen": list(combo), "levels": [levels[n] for n in LEVELS], "criteria": criteria(levels),
               "vessel": "6 lanes x 120 m (reference)"}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out.get("criteria", out["chosen"])))


if __name__ == "__main__":
    main()
