"""Download a plan of the game or the Lab as PDF or CSV."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from roro_yield.fcfs import solve_fcfs
from roro_yield.manifest import manifest_csv
from roro_yield.models import Plan, Scenario
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams
from server.config import ADVISOR_K
from server.exports import plan_pdf
from server.game_api import decisions_key, replay
from server.lab_api import LabParams, resolve_lab_plan
from server.planner_api import PlannerState
from server.runtime import get_jobs
from server.schemas import MAX_DECISIONS, Decision

router = APIRouter(prefix="/api/export")
NOT_READY = "This plan is not ready yet. Wait for it, then download."
SMART_GONE = "The smart plan is no longer on the server. Run the smart planner again, then download."
LAB_PLANS = {"fcfs", "optimal", "smart"}
GAME_PLANS = {"you", "fcfs", "smart", "best"}


class ExportRequest(BaseModel):
    source: Literal["lab", "game", "planner"]
    params: LabParams | None = None
    state: PlannerState | None = None
    seed: int | None = Field(default=None, ge=1, le=10_000)
    decisions: list[Decision] = Field(default_factory=list, max_length=MAX_DECISIONS)
    plan_key: Literal["fcfs", "optimal", "smart", "you", "best", "planner"]

    @model_validator(mode="after")
    def check_combination(self) -> "ExportRequest":
        if self.source == "lab" and (self.params is None or self.plan_key not in LAB_PLANS):
            raise ValueError("A Lab export needs the Lab settings and one of: fcfs, optimal, smart.")
        if self.source == "planner" and (self.state is None or self.plan_key != "planner"):
            raise ValueError("A planner export needs the planner state and plan_key planner.")
        if self.source == "game" and (self.seed is None or self.plan_key not in GAME_PLANS):
            raise ValueError("A game export needs the seed and one of: you, fcfs, smart, best.")
        return self


def resolve_game_plan(seed: int, decisions: list[Decision], plan_key: str) -> tuple[Scenario, Plan] | None:
    session = replay(seed, decisions)
    if not session.is_finished:
        raise HTTPException(409, "The game is not finished yet.")
    scenario = session.scenario
    jobs = get_jobs()
    if plan_key == "you":
        return scenario, session.to_plan()
    if plan_key == "fcfs":
        return scenario, solve_fcfs(scenario)
    smart_key = ("smart", seed, ADVISOR_K)
    smart = jobs.result(smart_key)
    if plan_key == "smart":
        if smart is None:
            raise HTTPException(409, NOT_READY if jobs.status(smart_key) in ("queued", "running") else SMART_GONE)
        return scenario, smart
    result = jobs.result(("best", seed, decisions_key(decisions)))
    if result is not None:
        return scenario, result[0]
    # The best plan is gone or was never asked for: rebuild it from the plans still at hand.
    you = session.to_plan()
    return scenario, solve_optimal(scenario, candidates=(you,) + (() if smart is None else (smart,)))


def resolve_planner_plan(state: PlannerState) -> tuple[Scenario, Plan, list[str]]:
    from server.planner_api import _placements, _scenario
    vessel, bookings = _scenario(state)
    placements = _placements(state)
    plan = Plan("Planner", placements, [b.id for b in bookings if b.id not in placements])
    assumptions = [f"Planner plan, {len(placements)} of {len(bookings)} accepted bookings loaded.",
                   f"Lost space (broken stowage): {state.vessel.broken_stowage_pct:.0%}."]
    if plan.rejected:
        assumptions.append(f"{len(plan.rejected)} accepted bookings are not on the deck and need a decision.")
    return Scenario(vessel, tuple(bookings), 0.0, 0.0), plan, assumptions


def _resolve(req: ExportRequest) -> tuple[Scenario, Plan, list[str]]:
    if req.source == "planner":
        return resolve_planner_plan(req.state)
    if req.source == "lab":
        params = ScenarioParams(**req.params.model_dump())
        found = resolve_lab_plan(params, req.plan_key, rebuild=True)
        if found is None:  # only the smart plan is never rebuilt
            status = get_jobs().status(("lab_smart", params, ADVISOR_K))
            raise HTTPException(409, NOT_READY if status in ("queued", "running") else SMART_GONE)
        assumptions = [f"Lab settings, seed {req.params.seed}, {req.params.n_requests} requests.",
                       f"Lost space (broken stowage): {req.params.broken_stowage_pct:.0%}."]
    else:
        found = resolve_game_plan(req.seed, req.decisions, req.plan_key)
        assumptions = [f"Game sailing, seed {req.seed}."]
    if found is None:
        raise HTTPException(409, NOT_READY)
    return found[0], found[1], assumptions


def _filename(req: ExportRequest, extension: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="roro-plan-{req.plan_key}.{extension}"'}


@router.post("/pdf")
def export_pdf(req: ExportRequest) -> Response:
    scenario, plan, assumptions = _resolve(req)
    title = f"RoRo deck plan: {plan.method}"
    return Response(plan_pdf(scenario, plan, title, assumptions), media_type="application/pdf",
                    headers=_filename(req, "pdf"))


@router.post("/csv")
def export_csv(req: ExportRequest) -> Response:
    scenario, plan, _ = _resolve(req)
    return Response(manifest_csv(scenario, plan), media_type="text/csv", headers=_filename(req, "csv"))
