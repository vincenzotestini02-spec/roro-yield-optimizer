"""The Lab: change the rules and compare the plans."""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, create_model

from roro_yield.fcfs import solve_fcfs
from roro_yield.manifest import manifest_csv
from roro_yield.models import Plan, Scenario
from roro_yield.optimizer import solve_optimal
from roro_yield.simulator import ScenarioParams, generate_scenario
from server import jobs_api
from server.config import ADVISOR_K, GAME_PARAMS
from server.presets import PRESET_NOTE, PRESETS
from server.reveal_api import plan_result, run_smart
from server.runtime import get_jobs

router = APIRouter(prefix="/api")
LONG_RUN_THRESHOLD = 1200  # requests x lanes above which the smart plan takes minutes on 1 vCPU

LIMITS: dict[str, tuple[float, float]] = {
    "n_requests": (30, 200),
    "contract_share": (0.0, 0.9),
    "spot_rate_multiplier": (0.7, 1.5),
    "contract_floor_share": (0.0, 0.8),
    "n_lanes": (1, 16),
    "lane_length_m": (70.0, 250.0),
    "max_dwt_t": (10.0, 5000.0),
    "reefer_plugs": (0, 40),
    "lashing_gap_m": (0.0, 1.5),
    "max_heel_deg": (0.5, 5.0),
    "max_trim_m": (0.1, 2.0),
    "ballast_tank_cap_t": (0.0, 600.0),
    "ballast_cost_per_t": (0.0, 30.0),
    "broken_stowage_pct": (0.0, 0.3),
    "displacement_t": (2000.0, 40000.0),
    "gm_m": (0.5, 4.0),
    "mtc_tm_per_cm": (50.0, 600.0),
    "seed": (1, 10_000),
}
INTEGER_FIELDS = {"n_requests", "n_lanes", "reefer_plugs", "seed"}

LabParams = create_model(
    "LabParams",
    __config__=ConfigDict(extra="forbid"),
    **{name: (int if name in INTEGER_FIELDS else float, Field(ge=low, le=high))
       for name, (low, high) in LIMITS.items()},
)


class ManifestRequest(BaseModel):
    params: LabParams
    plan_key: Literal["fcfs", "optimal", "smart"]


def _engine_params(params: BaseModel) -> ScenarioParams:
    return ScenarioParams(**params.model_dump())


def _plans(scenario) -> tuple[Plan, Plan]:
    return solve_fcfs(scenario), solve_optimal(scenario)


def _smart(scenario, params: ScenarioParams, k: int, on_progress: Callable | None = None) -> tuple[Plan, Plan]:
    smart = run_smart(scenario, params, k, on_progress=on_progress)
    return smart, solve_optimal(scenario, candidates=(smart,))


@router.get("/lab/defaults")
def lab_defaults() -> dict:
    return {"values": {name: getattr(GAME_PARAMS, name) for name in LIMITS},
            "limits": {name: list(limit) for name, limit in LIMITS.items()},
            "advisor_k": ADVISOR_K,
            "presets": PRESETS,
            "note": PRESET_NOTE}


@router.post("/lab/plans")
def lab_plans(body: LabParams) -> dict:
    params = _engine_params(body)
    scenario = generate_scenario(params)

    def output(result: tuple[Plan, Plan]) -> dict:
        return {"fcfs": plan_result(scenario, result[0]), "optimal": plan_result(scenario, result[1]),
                "smart_may_be_slow": params.n_requests * params.n_lanes > LONG_RUN_THRESHOLD}

    return {"job_id": jobs_api.submit(("lab", params), _plans, scenario, output=output)}


@router.post("/lab/smart")
def lab_smart(body: LabParams) -> dict:
    params = _engine_params(body)
    scenario = generate_scenario(params)

    def output(result: tuple[Plan, Plan]) -> dict:
        return {"smart": plan_result(scenario, result[0]), "best": plan_result(scenario, result[1])}

    key = ("lab_smart", params, ADVISOR_K)
    return {"job_id": jobs_api.submit(key, _smart, scenario, params, ADVISOR_K, output=output)}


def resolve_lab_plan(params: ScenarioParams, plan_key: str, rebuild: bool = False) -> tuple[Scenario, Plan] | None:
    """The finished plan for these Lab settings, or None if it has not been computed.

    With `rebuild`, FCFS and the optimizer are recomputed when the server no longer has them
    (restart, scale to zero, expiry). The smart plan takes minutes, so it is never rebuilt here.
    """
    jobs = get_jobs()
    smart = jobs.result(("lab_smart", params, ADVISOR_K))
    plans = jobs.result(("lab", params))
    plan = None
    if plan_key == "smart" and smart is not None:
        plan = smart[0]
    elif plan_key == "optimal" and smart is not None:
        plan = smart[1]
    elif plans is not None and plan_key != "smart":
        plan = plans[0] if plan_key == "fcfs" else plans[1]
    if plan is None and rebuild and plan_key != "smart":
        plan = _plans(generate_scenario(params))[0 if plan_key == "fcfs" else 1]
    return None if plan is None else (generate_scenario(params), plan)


@router.post("/manifest.csv")
def manifest(req: ManifestRequest) -> Response:
    found = resolve_lab_plan(_engine_params(req.params), req.plan_key)
    if found is None:
        raise HTTPException(409, "Run this plan first, then download its manifest.")
    return Response(manifest_csv(*found), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="manifest.csv"'})
