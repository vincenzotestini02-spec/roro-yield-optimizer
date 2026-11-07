"""The reveal: the player's plan against FCFS, the smart planner and the best possible plan."""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from roro_yield.advisor import smart_plan
from roro_yield.explain import costly_decisions
from roro_yield.fcfs import solve_fcfs
from roro_yield.kpis import evaluate
from roro_yield.models import Plan, Scenario
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams
from server import jobs_api
from server.config import ADVISOR_K
from server.game_api import decisions_key, game_params, replay
from server.runtime import get_jobs, get_smart_cache
from server.schemas import GameRequest
from server.serialize import booking_out, deck_out, kpis_out, plan_deck

router = APIRouter(prefix="/api/reveal")


class BestRequest(GameRequest):
    smart_job: str


def plan_result(scenario: Scenario, plan: Plan) -> dict:
    rejected = [scenario.booking(i) for i in plan.rejected]
    return {
        "method": plan.method,
        "kpis": kpis_out(evaluate(scenario, plan)),
        "deck": deck_out(plan_deck(scenario, plan)),
        "rejected": [booking_out(b) for b in rejected],
        "sold_m": {
            segment: sum(b.length_m for b in map(scenario.booking, plan.placements) if b.segment == segment)
            for segment in ("contract", "spot")
        },
    }


def run_smart(scenario: Scenario, params: ScenarioParams, k: int, on_progress: Callable | None = None) -> Plan:
    """The smart plan for a sailing, reused across visitors."""
    cache = get_smart_cache()
    cached = cache.get(params, k)
    if cached is None:
        cached = smart_plan(scenario, params, k=k, on_progress=on_progress)
        cache.put(params, k, cached)
    return cached[0]


def _finished(req: GameRequest):
    session = replay(req.seed, req.decisions)
    if not session.is_finished:
        raise HTTPException(409, "The game is not finished yet.")
    return session


@router.post("")
def reveal(req: GameRequest) -> dict:
    session = _finished(req)
    scenario = session.scenario
    params = game_params(req.seed)
    smart_job = jobs_api.submit(("smart", req.seed, ADVISOR_K), run_smart, scenario, params, ADVISOR_K,
                                output=lambda plan: plan_result(scenario, plan))
    return {
        "you": plan_result(scenario, session.to_plan()),
        "fcfs": plan_result(scenario, solve_fcfs(scenario)),
        "smart_job": smart_job,
    }


def _best(scenario: Scenario, you: Plan, smart: Plan | None) -> tuple[Plan, list]:
    best = solve_optimal(scenario, candidates=(you,) + (() if smart is None else (smart,)))
    return best, costly_decisions(scenario, you, best)


@router.post("/best")
def reveal_best(req: BestRequest) -> dict:
    session = _finished(req)
    scenario = session.scenario
    key = jobs_api.key_of(req.smart_job)
    jobs = get_jobs()
    status = "unknown" if key is None else jobs.status(key)
    if status == "unknown":
        raise HTTPException(404, jobs_api.GONE_MESSAGE)
    if status not in ("done", "failed"):  # a failed smart run still leaves a best plan to show
        raise HTTPException(409, "The smart planner has not finished.")
    smart = jobs.result(key) if status == "done" else None
    best_key = ("best", req.seed, decisions_key(req.decisions))

    def output(result: tuple[Plan, list]) -> dict:
        best, costly = result
        return {"plan": plan_result(scenario, best), "costly": [asdict(d) for d in costly]}

    return {"job_id": jobs_api.submit(best_key, _best, scenario, session.to_plan(), smart, output=output)}
