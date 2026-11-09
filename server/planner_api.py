"""The planner: plan accepted bookings, move a unit by hand, judge a new request.

Stateless: the browser sends vessel, bookings and the current plan with every call.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, create_model

from roro_yield.advisor import NEUTRAL_SEED, PolicyView, advise, advisor_rng_seed
from roro_yield.deck import DeckState
from roro_yield.demand import expected_remaining, requests_for_level
from roro_yield.kpis import evaluate
from roro_yield.models import Booking, Plan, Scenario, Slot, Vessel
from roro_yield.planning import OnBoardConflict, plan_accepted
from roro_yield.simulator import HANDLING_PER_TONNE, HANDLING_PER_UNIT, REEFER_FEE, ScenarioParams, generate_scenario
from server import jobs_api
from server.config import ADVISOR_K, GAME_PARAMS
from server.importer import PlannerBooking
from server.lab_api import LIMITS
from server.serialize import deck_out, kpis_out, parse_slot, verdict_out

router = APIRouter(prefix="/api/planner")

MAX_BOOKINGS = 500
PLANNER_LOST_SPACE = 0.15
VESSEL_FIELDS = ("n_lanes", "lane_length_m", "max_dwt_t", "reefer_plugs", "lashing_gap_m", "max_heel_deg",
                 "max_trim_m", "ballast_tank_cap_t", "ballast_cost_per_t", "broken_stowage_pct", "displacement_t",
                 "gm_m", "mtc_tm_per_cm")
INTEGER_FIELDS = {"n_lanes", "reefer_plugs"}

PlannerVessel = create_model(
    "PlannerVessel",
    __config__=ConfigDict(extra="forbid"),
    preset=(Literal["demo", "ropax", "shortsea", "custom"], "demo"),
    **{name: (int if name in INTEGER_FIELDS else float,
              Field(default=PLANNER_LOST_SPACE if name == "broken_stowage_pct" else getattr(GAME_PARAMS, name),
                    ge=LIMITS[name][0], le=LIMITS[name][1]))
       for name in VESSEL_FIELDS},
)


class PlannerState(BaseModel):
    vessel: PlannerVessel = Field(default_factory=PlannerVessel)
    bookings: list[PlannerBooking] = Field(max_length=MAX_BOOKINGS)
    placements: dict[str, str] = Field(default_factory=dict)


class MoveRequest(PlannerState):
    booking_id: str
    slot: str


class Demand(BaseModel):
    level: Literal["low", "normal", "high"] = "normal"
    contract_share: float = Field(default=0.45, ge=0, le=0.9)
    spot_rate_multiplier: float = Field(default=1.0, ge=0.7, le=1.5)
    window_days: int = Field(default=14, ge=1, le=60)
    hours_to_departure: float = Field(default=72, ge=0, le=60 * 24)


class AdviseRequest(PlannerState):
    request: PlannerBooking
    demand: Demand


def assumption_text(d: Demand) -> str:
    return f"Assumption: {d.level} demand, {d.contract_share:.0%} contract"


def _params(vessel: BaseModel, **extra) -> ScenarioParams:
    return replace(GAME_PARAMS, **{name: getattr(vessel, name) for name in VESSEL_FIELDS}, **extra)


def vessel_from(vessel: BaseModel) -> Vessel:
    return generate_scenario(_params(vessel, n_requests=30)).vessel


def engine_booking(b: PlannerBooking, arrival: int, arrival_frac: float = 0.0) -> Booking:
    priced = b.rate_per_m is not None
    fee = b.reefer_fee if b.reefer_fee is not None else (REEFER_FEE[b.segment] if priced else 0.0)
    return Booking(
        id=b.booking_id, arrival=arrival, segment=b.segment, customer=b.customer, unit_type=b.unit_type,
        length_m=b.length_m, weight_t=b.weight_t, is_reefer=b.is_reefer, rate_per_m=b.rate_per_m or 0.0,
        reefer_fee=fee, handling_cost=HANDLING_PER_UNIT + HANDLING_PER_TONNE * b.weight_t, arrival_frac=arrival_frac,
    )


def _placements(state: PlannerState) -> dict[str, Slot]:
    known = {b.booking_id for b in state.bookings}
    out = {}
    for booking_id, text in state.placements.items():
        if booking_id not in known:
            continue
        try:
            out[booking_id] = parse_slot(text)
        except ValueError:
            raise HTTPException(422, f"{text} is not a deck zone.") from None
    return out


def _scenario(state: PlannerState) -> tuple[Vessel, list[Booking]]:
    ids = [b.booking_id for b in state.bookings]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Booking ids must be unique.")
    return vessel_from(state.vessel), [engine_booking(b, i) for i, b in enumerate(state.bookings)]


def plan_out(state: PlannerState, vessel: Vessel, bookings: list[Booking], placements: dict[str, Slot],
             moved: list[str], excluded: list[tuple[str, str]] | None = None) -> dict:
    by_id = {b.id: b for b in bookings}
    deck = DeckState(vessel)
    for booking_id, slot in placements.items():
        deck.place(by_id[booking_id], slot)
    if excluded is None:
        missing = sorted((b for b in bookings if b.id not in placements), key=lambda b: (-b.length_m, b.id))
        excluded = [(b.id, deck.why_not(b) or "no zone can take it with the units already planned") for b in missing]
    plan = Plan("Planner", dict(placements), [b for b, _ in excluded])
    priced = {b.booking_id: b.rate_per_m is not None for b in state.bookings}
    return {
        "placements": {k: str(v) for k, v in placements.items()},
        "excluded": [{"booking_id": b, "reason": r} for b, r in excluded],
        "moved": moved,
        "deck": deck_out(deck),
        "kpis": kpis_out(evaluate(Scenario(vessel, tuple(bookings), 0.0, 0.0), plan)),
        "revenue_known": all(priced[k] for k in placements),
    }


def _run_plan(state: PlannerState) -> dict:
    vessel, bookings = _scenario(state)
    on_board = frozenset(b.booking_id for b in state.bookings if b.on_board)
    previous = _placements(state)
    try:
        result = plan_accepted(vessel, bookings, previous=previous, on_board=on_board)
    except OnBoardConflict as exc:
        raise HTTPException(422, f"{exc.booking_id} is on board, but {exc.reason}.") from None
    return plan_out(state, vessel, bookings, result.plan.placements, result.moved, result.excluded)


def _state_key(state: BaseModel) -> str:
    return hashlib.sha256(json.dumps(state.model_dump(), sort_keys=True).encode()).hexdigest()


@router.post("/plan")
def planner_plan(state: PlannerState) -> dict:
    vessel, bookings = _scenario(state)
    on_board = {b.booking_id for b in state.bookings if b.on_board}
    previous = _placements(state)
    # On-board conflicts are cheap to find: answer them now rather than as a failed job.
    try:
        plan_accepted(vessel, [b for b in bookings if b.id in on_board], previous=previous,
                      on_board=frozenset(on_board), time_limit_s=1)
    except OnBoardConflict as exc:
        raise HTTPException(422, f"{exc.booking_id} is on board, but {exc.reason}.") from None
    return {"job_id": jobs_api.submit(("planner", _state_key(state)), _run_plan, state)}


@router.post("/move")
def planner_move(req: MoveRequest) -> dict:
    vessel, bookings = _scenario(req)
    by_id = {b.id: b for b in bookings}
    planner = {b.booking_id: b for b in req.bookings}
    if req.booking_id not in by_id:
        raise HTTPException(422, f"{req.booking_id} is not in the bookings.")
    if planner[req.booking_id].on_board:
        raise HTTPException(422, "This unit is on board and cannot move.")
    try:
        slot = parse_slot(req.slot)
    except ValueError:
        raise HTTPException(422, f"{req.slot} is not a deck zone.") from None
    placements = {k: v for k, v in _placements(req).items() if k != req.booking_id}
    deck = DeckState(vessel)
    for booking_id, s in placements.items():
        deck.place(by_id[booking_id], s)
    unit = by_id[req.booking_id]
    if slot not in deck.remaining_m:
        raise HTTPException(422, f"{req.slot} is not a zone of this vessel.")
    if slot not in deck.feasible_slots(unit):
        raise HTTPException(422, deck.why_not(unit) or f"{req.booking_id} does not fit in {req.slot}.")
    placements[req.booking_id] = slot
    return plan_out(req, vessel, bookings, placements, moved=[req.booking_id])


def _advise(view: PolicyView, assumption: str) -> dict:
    return {**verdict_out(advise(view, k=ADVISOR_K)), "assumption": assumption}


@router.post("/advise")
def planner_advise(req: AdviseRequest) -> dict:
    vessel, bookings = _scenario(req)
    if req.request.rate_per_m is None:
        raise HTTPException(422, "A new request needs a price per metre.")
    if req.request.booking_id in {b.id for b in bookings}:
        raise HTTPException(422, f"{req.request.booking_id} is already a booking.")
    by_id = {b.id: b for b in bookings}
    deck = DeckState(vessel)
    for booking_id, slot in _placements(req).items():
        deck.place(by_id[booking_id], slot)
    d = req.demand
    frac = min(max(1 - d.hours_to_departure / (d.window_days * 24), 0.0), 1.0)
    usable = sum(vessel.zone_capacity_m(lane) * 4 for lane in vessel.lanes)
    n_level = requests_for_level(d.level, usable)
    params = _params(req.vessel, n_requests=max(30, n_level), contract_share=d.contract_share,
                     spot_rate_multiplier=d.spot_rate_multiplier, seed=NEUTRAL_SEED)
    current = engine_booking(req.request, len(bookings), arrival_frac=frac)
    view = PolicyView(params=params, vessel=vessel, commitment_m=0.0, penalty_per_m=0.0, deck=deck,
                      history=tuple(bookings), current=current, index=0,
                      n_total=1 + expected_remaining(n_level, frac, d.contract_share),
                      rng_seed=advisor_rng_seed(int(_state_key(req)[:8], 16)))
    key = ("planner-advice", _state_key(req))
    return {"job_id": jobs_api.submit(key, _advise, view, assumption_text(d))}
