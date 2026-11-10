"""Experiment: K sampled futures against an expected-value rule (in the spirit of Main, 2024).

    python -m benchmarks.ev_test --out benchmarks/results/ev_test.json

The expected-value rule solves one LP pair over the union of the K futures, each future booking
capped at 1/K, instead of K LP pairs. Product code is not changed by this script.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import replace
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np

from roro_yield.advisor import _contract_m, _solve_value, advise, view_for
from roro_yield.deck import DeckState
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import objective
from roro_yield.models import Plan
from roro_yield.optimizer import build_model
from roro_yield.simulator import ScenarioParams, generate_scenario, sample_future

SEEDS = range(1, 11)
N_REQUESTS = 60
K = 20


def ev_gain(view, k: int = K) -> float | None:
    """Expected gain of loading the current unit under the expected-value rule; None if it cannot load."""
    current, deck = view.current, view.deck.copy()
    if deck.why_not(current) is not None:
        return None
    slot = deck.best_slot(current)
    rng = np.random.default_rng([view.rng_seed, view.index])
    n_remaining = view.n_total - view.index - 1
    union = []
    for f in range(k):
        future = sample_future(view.params, current.arrival_frac, n_remaining, rng)
        union += [replace(b, id=f"{b.id}_{f}") for b in future]
    requested = _contract_m(view.history) + _contract_m([current])
    floor = min(view.commitment_m, requested + _contract_m(union) / k)
    model = build_model(view.vessel, union, floor, view.penalty_per_m, relaxed=True, deck=deck, forced=(current, slot))
    for (bid, _, _), var in model.y.items():
        var.upBound = 1.0 / k
    values = []
    for loaded in (1, 0):
        model.forced.lowBound = model.forced.upBound = loaded
        values.append(_solve_value(model.prob))
    return values[0] - values[1]


def _sailing(seed: int) -> dict:
    params = replace(ScenarioParams(), n_requests=N_REQUESTS, seed=seed)
    s = generate_scenario(params)
    decks = {"sampled": DeckState(s.vessel), "ev": DeckState(s.vessel)}
    rejected = {"sampled": [], "ev": []}
    agree, total, t_sampled, t_ev = 0, 0, 0.0, 0.0
    for index, b in enumerate(s.bookings):
        start = time.perf_counter()
        v = advise(view_for(s, params, decks["sampled"], index), k=K, suggest_moves=False)
        t_sampled += time.perf_counter() - start
        start = time.perf_counter()
        gain = ev_gain(view_for(s, params, decks["ev"], index))
        t_ev += time.perf_counter() - start
        ev_accept = gain is not None and gain > 1e-9
        same_deck = decks["sampled"].placements == decks["ev"].placements
        if same_deck:
            total += 1
            agree += int(v.accept == ev_accept)
        for name, accept in (("sampled", v.accept), ("ev", ev_accept)):
            if accept and decks[name].why_not(b) is None:
                decks[name].place(b)
            else:
                rejected[name].append(b.id)
    plans = {name: Plan(name, decks[name].placements, rejected[name]) for name in decks}
    return {"seed": seed, "fcfs": objective(s, solve_fcfs(s)), "sampled": objective(s, plans["sampled"]),
            "ev": objective(s, plans["ev"]), "agree": agree, "compared": total,
            "seconds_sampled": t_sampled / len(s.bookings), "seconds_ev": t_ev / len(s.bookings)}


def summarize(rows: list[dict]) -> dict:
    return {
        "sailings": len(rows),
        "agreement": sum(r["agree"] for r in rows) / max(1, sum(r["compared"] for r in rows)),
        "score_sampled": statistics.mean(r["sampled"] for r in rows),
        "score_ev": statistics.mean(r["ev"] for r in rows),
        "score_fcfs": statistics.mean(r["fcfs"] for r in rows),
        "seconds_per_verdict_sampled": statistics.mean(r["seconds_sampled"] for r in rows),
        "seconds_per_verdict_ev": statistics.mean(r["seconds_ev"] for r in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    with Pool(args.workers) as pool:
        rows = pool.map(_sailing, SEEDS, chunksize=1)
    out = {"k": K, "n_requests": N_REQUESTS, "seeds": [SEEDS.start, SEEDS.stop - 1], "vessel": "6 lanes x 120 m",
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "summary": summarize(rows), "sailings": rows}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
